"""
Enricher Service — 多模态富化（图片描述 / 表格摘要）

使用 Qwen-VL 视觉多模态模型（型号由 settings.vlm_model 控制，默认 qwen-vl-plus）
为图片生成描述、为表格生成摘要，富化后的数据写入 IRBlockEnriched，
提升检索阶段的召回质量。

流程：
  1. 收集所有 image / table 类型的 IRBlock
  2. 对每个图片：读取文件 → base64 → VLM 模型生成描述
  3. 对每个表格：提取 HTML → VLM 模型生成摘要
  4. 组装 IRBlockEnriched，附加 enrichment 字段
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import settings
from app.models.models_ir import (
    BlockEnrichment,
    ImageEnrichment,
    IRBlock,
    IRBlockEnriched,
    NeighborContext,
    TableEnrichment,
)

logger = logging.getLogger(__name__)

_BATCH_CONCURRENCY = 3       # 并发调用数
_API_TIMEOUT = 60.0
_IMAGE_DESC_PROMPT = (
    "请用一段简洁的中文描述这张图片的内容，包括其中的关键信息、图表类型（如有）、"
    "数据要点（如有）。描述控制在100字以内。"
)
_TABLE_SUMMARY_PROMPT = (
    "请用一段简洁的中文总结下面这个表格的内容和要点，控制在100字以内。"
    "如果表格包含数字数据，请提炼关键趋势或对比信息。"
)


async def enrich_blocks(
    blocks: list[IRBlock],
    base_dir: str = "",
) -> list[IRBlockEnriched]:
    """
    对 IRBlock 列表进行多模态富化。

    Args:
        blocks: 归一化后的 IRBlock 列表
        base_dir: 资源文件根目录（zip解压根目录），用于解析图片的相对路径

    Returns:
        富化后的 IRBlockEnriched 列表，顺序与输入一致
    """
    if not blocks:
        return []

    # 找出需要富化的块
    image_indices = [(i, b) for i, b in enumerate(blocks) if b.type == "image"]
    table_indices = [(i, b) for i, b in enumerate(blocks) if b.type == "table"]

    if not image_indices and not table_indices:
        logger.info("无可富化的多模态块，跳过")
        return [_to_enriched(b, None) for b in blocks]

    sem = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def enrich_image(idx: int, blk: IRBlock) -> tuple[int, Optional[BlockEnrichment]]:
        async with sem:
            enrichment = await _enrich_image_block(blk, base_dir)
            return idx, enrichment

    async def enrich_table(idx: int, blk: IRBlock) -> tuple[int, Optional[BlockEnrichment]]:
        async with sem:
            enrichment = await _enrich_table_block(blk)
            return idx, enrichment

    tasks = []
    for idx, blk in image_indices:
        tasks.append(enrich_image(idx, blk))
    for idx, blk in table_indices:
        tasks.append(enrich_table(idx, blk))

    # 并行执行，收集结果
    results: dict[int, Optional[BlockEnrichment]] = {}
    if tasks:
        gathered = await asyncio.gather(*tasks)
        for idx, enrichment in gathered:
            results[idx] = enrichment

    # 组装富化块
    enriched: list[IRBlockEnriched] = []
    for i, blk in enumerate(blocks):
        enriched.append(_to_enriched(blk, results.get(i)))

    img_ok = sum(1 for r in results.values() if r and r.enrichment_status == "ok")
    logger.info(
        "富化完成: %d images, %d tables → %d ok",
        len(image_indices), len(table_indices), img_ok,
    )
    return enriched


def _to_enriched(blk: IRBlock, enrichment: BlockEnrichment | None) -> IRBlockEnriched:
    """将 IRBlock 转为 IRBlockEnriched。"""
    return IRBlockEnriched(
        **blk.model_dump(),
        enrichment=enrichment,
    )


# ─────────────────────────────────────────────────────────────
# 图片富化
# ─────────────────────────────────────────────────────────────

async def _enrich_image_block(
    blk: IRBlock,
    base_dir: str,
) -> Optional[BlockEnrichment]:
    """对单个 image 块调用 Vision API 生成描述。"""
    image_path = _resolve_image_path(blk, base_dir)
    if not image_path:
        logger.warning("图片块 %s 无有效路径，跳过富化", blk.block_id)
        return BlockEnrichment(
            image=ImageEnrichment(image_vlm_description=""),
            enrichment_status="skipped",
        )

    try:
        description = await _call_vision_api(image_path, _IMAGE_DESC_PROMPT)
    except Exception as exc:
        logger.warning("图片富化失败 %s: %s", blk.block_id, exc)
        return BlockEnrichment(
            image=ImageEnrichment(image_vlm_description=""),
            enrichment_status="partial_failed",
        )

    embedding_text_parts = [blk.text] if blk.text else []
    if description:
        embedding_text_parts.append(description)

    return BlockEnrichment(
        image=ImageEnrichment(
            image_caption_text=blk.text,
            image_vlm_description=description,
            embedding_text="\n".join(embedding_text_parts),
        ),
        enrichment_status="ok",
    )


def _resolve_image_path(blk: IRBlock, base_dir: str) -> str | None:
    """从 block 的 assets 中解析图片的本地路径。"""
    for asset in blk.assets:
        if asset.asset_type == "image" and asset.path:
            p = Path(asset.path)
            if p.is_absolute() and p.exists():
                return str(p)
            if base_dir:
                candidate = Path(base_dir) / asset.path
                if candidate.exists():
                    return str(candidate)
                # 尝试去掉 images/ 前缀再拼
                rel = asset.path
                if rel.startswith("images/"):
                    candidate2 = Path(base_dir) / rel[7:]
                    if candidate2.exists():
                        return str(candidate2)
            # 返回原始路径，让 API 调用失败时处理
            return asset.path
    return None


# ─────────────────────────────────────────────────────────────
# 表格富化
# ─────────────────────────────────────────────────────────────

async def _enrich_table_block(blk: IRBlock) -> Optional[BlockEnrichment]:
    """对单个 table 块生成文本摘要。"""
    html = blk.metadata.table_html or ""
    caption = blk.text or ""

    if not html and not caption:
        logger.warning("表格块 %s 无 HTML 和 caption，跳过富化", blk.block_id)
        return BlockEnrichment(
            table=TableEnrichment(table_summary=""),
            enrichment_status="skipped",
        )

    content = html if html else caption

    try:
        summary = await _call_text_summary(content, _TABLE_SUMMARY_PROMPT)
    except Exception as exc:
        logger.warning("表格富化失败 %s: %s", blk.block_id, exc)
        return BlockEnrichment(
            table=TableEnrichment(table_summary="", table_html_available=bool(html)),
            enrichment_status="partial_failed",
        )

    embedding_text_parts = []
    if caption:
        embedding_text_parts.append(caption)
    if summary:
        embedding_text_parts.append(summary)

    return BlockEnrichment(
        table=TableEnrichment(
            table_caption_text=caption,
            table_summary=summary,
            table_html_available=bool(html),
            embedding_text="\n".join(embedding_text_parts),
        ),
        enrichment_status="ok",
    )


# ─────────────────────────────────────────────────────────────
# API 调用
# ─────────────────────────────────────────────────────────────

async def _call_vision_api(image_path: str, prompt: str) -> str:
    """调用 VLM 视觉模型分析图片，返回文字描述。"""
    if not Path(image_path).exists():
        logger.warning("图片文件不存在: %s", image_path)
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # 读取图片并 base64 编码
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    mime_type = mime_map.get(ext, "image/jpeg")

    payload = {
        "model": settings.vlm_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_data}"}},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.dashscope_base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content.strip()


async def _call_text_summary(text: str, prompt: str) -> str:
    """调用 VLM 模型生成纯文本摘要。"""
    # 截断过长 HTML
    if len(text) > 3000:
        text = text[:3000]

    payload = {
        "model": settings.vlm_model,
        "messages": [
            {"role": "user", "content": f"{prompt}\n\n{text}"},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.dashscope_base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content.strip()
