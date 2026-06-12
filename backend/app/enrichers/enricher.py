"""
Enricher Service — 多模态富化（图片描述 / 表格摘要）

使用多模态视觉模型（型号由 settings.vlm_model 控制，默认 qwen3.7-plus）
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
    CodeEnrichment,
    EquationEnrichment,
    ImageEnrichment,
    IRBlock,
    IRBlockEnriched,
    TableEnrichment,
)
from app.services.http_retry import retry_async

logger = logging.getLogger(__name__)

_BATCH_CONCURRENCY = 3       # 并发调用数
_API_TIMEOUT = 60.0
_IMAGE_DESC_PROMPT = (
    "请用中文理解并描述这张图片，作为它在知识库中的可检索文本，要求："
    "①一句话说明这是什么（照片/示意图/流程图/界面截图/图表等）及主旨；"
    "②如果图中有文字、标题、标注、公式或数据，请准确转写出来（这部分是检索关键）；"
    "③如果是图表，说明图表类型并提炼关键数据、对比或趋势。"
    "信息完整即可，不必刻意简短，但避免空洞冗余；纯图形无文字时只需如实描述画面。"
)
_TABLE_SUMMARY_PROMPT = (
    "请用一段简洁的中文总结下面这个表格的内容和要点，控制在100字以内。"
    "如果表格包含数字数据，请提炼关键趋势或对比信息。"
)
_CODE_ENRICH_PROMPT = (
    "请分析以下代码块，用中文输出两部分：\n"
    "1. [功能说明]：用1-2句话概括这段代码的核心功能和用途。\n"
    "2. [核心代码]：提取这段代码中最关键的部分（函数定义/核心逻辑/关键类名），"
    "剔除无关的 import 语句和冗长的 boilerplate 代码，保留能体现功能特征的标识符。\n\n"
    "代码：\n{code}"
)
_EQUATION_ENRICH_PROMPT = (
    "请用中文解释以下数学公式，包括：公式名称、各符号的含义、用途。"
    "控制在100字以内。\n\n"
    "公式：{equation}"
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
    code_indices = [(i, b) for i, b in enumerate(blocks) if b.type == "code" and b.text.strip()]
    equation_indices = [(i, b) for i, b in enumerate(blocks) if b.type == "equation" and b.text.strip()]

    if not image_indices and not table_indices and not code_indices and not equation_indices:
        logger.info("无可富化的块，跳过")
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

    async def enrich_code(idx: int, blk: IRBlock) -> tuple[int, Optional[BlockEnrichment]]:
        async with sem:
            enrichment = await _enrich_code_block(blk)
            return idx, enrichment

    async def enrich_equation(idx: int, blk: IRBlock) -> tuple[int, Optional[BlockEnrichment]]:
        async with sem:
            enrichment = await _enrich_equation_block(blk)
            return idx, enrichment

    tasks = []
    for idx, blk in image_indices:
        tasks.append(enrich_image(idx, blk))
    for idx, blk in table_indices:
        tasks.append(enrich_table(idx, blk))
    for idx, blk in code_indices:
        tasks.append(enrich_code(idx, blk))
    for idx, blk in equation_indices:
        tasks.append(enrich_equation(idx, blk))

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
        "富化完成: %d images, %d tables, %d code, %d equations → %d ok",
        len(image_indices), len(table_indices), len(code_indices), len(equation_indices), img_ok,
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
# 代码块富化（LLM 文本模型）
# ─────────────────────────────────────────────────────────────

async def _enrich_code_block(blk: IRBlock) -> Optional[BlockEnrichment]:
    """对单个 code 块用 LLM 生成功能说明 + 提取核心代码。"""
    code_text = blk.text.strip()
    if not code_text:
        return BlockEnrichment(
            code=CodeEnrichment(code_summary="", core_code=""),
            enrichment_status="skipped",
        )
    try:
        prompt = _CODE_ENRICH_PROMPT.format(code=code_text[:3000])
        result = await _call_text_enrich(prompt)
    except Exception as exc:
        logger.warning("代码富化失败 %s: %s", blk.block_id, exc)
        return BlockEnrichment(
            code=CodeEnrichment(code_summary="", core_code=code_text[:500]),
            enrichment_status="partial_failed",
        )

    summary, core = _parse_code_result(result, code_text)
    emb_parts = []
    if summary:
        emb_parts.append(f"[代码功能说明]: {summary}")
    if core:
        emb_parts.append(f"[核心代码]: {core}")
    return BlockEnrichment(
        code=CodeEnrichment(
            code_summary=summary,
            core_code=core,
            embedding_text="\n".join(emb_parts),
        ),
        enrichment_status="ok",
    )


def _parse_code_result(result: str, fallback_code: str) -> tuple[str, str]:
    """解析 LLM 输出的代码富化结果，提取功能说明和核心代码。"""
    summary = ""
    core = ""
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[功能说明]") or stripped.startswith("1."):
            summary = stripped.split("]", 1)[-1].strip().lstrip(":").strip() if "]" in stripped else stripped.split(".", 1)[-1].strip()
        elif stripped.startswith("[核心代码]") or stripped.startswith("2."):
            core_part = stripped.split("]", 1)[-1].strip() if "]" in stripped else stripped.split(".", 1)[-1].strip()
            core = core_part if core_part else core
    # Fallback: use summary as description, truncated code as core
    if not summary and not core:
        summary = result[:200]
        core = fallback_code[:500]
    return summary, core


# ─────────────────────────────────────────────────────────────
# 公式块富化（LLM 文本模型）
# ─────────────────────────────────────────────────────────────

async def _enrich_equation_block(blk: IRBlock) -> Optional[BlockEnrichment]:
    """对单个 equation 块用 LLM 生成自然语言解释。"""
    eq_text = blk.text.strip()
    if not eq_text:
        return BlockEnrichment(
            equation=EquationEnrichment(equation_context_text="", embedding_text=""),
            enrichment_status="skipped",
        )
    try:
        prompt = _EQUATION_ENRICH_PROMPT.format(equation=eq_text[:1000])
        result = await _call_text_enrich(prompt)
    except Exception as exc:
        logger.warning("公式富化失败 %s: %s", blk.block_id, exc)
        return BlockEnrichment(
            equation=EquationEnrichment(
                equation_context_text="",
                embedding_text=f"[数学公式]: {eq_text}",
            ),
            enrichment_status="partial_failed",
        )

    explanation = result.strip()[:300]
    embedding_text = f"[数学公式]: {eq_text}\n[公式含义]: {explanation}"
    return BlockEnrichment(
        equation=EquationEnrichment(
            equation_context_text=explanation,
            embedding_text=embedding_text,
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
        # 关闭思考：图片描述不需要思维链，关掉可省 thinking token、更快。
        # （实测 qwen3.7-plus 非流式即便开思考也能正常返回、不强制 stream；故此处纯为优化。）
        "enable_thinking": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.dashscope_base_url}/chat/completions"

    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    body = await retry_async(_call, what="VLM API")
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
        # 同上：关闭思考纯为优化（省 token / 更快），表格摘要不需要思维链。
        "enable_thinking": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.dashscope_base_url}/chat/completions"

    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    body = await retry_async(_call, what="VLM API")
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content.strip()


async def _call_text_enrich(prompt: str) -> str:
    """调用 QA 文本模型做代码/公式富化（不消耗 VLM 配额）。"""
    payload = {
        "model": settings.qa_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.effective_qa_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.effective_qa_base_url}/chat/completions"

    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    body = await retry_async(_call, what="LLM enrich API")
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content.strip()
