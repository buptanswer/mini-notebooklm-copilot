"""
QA Service — 使用 qwen3.5-plus 进行多模态问答（OpenAI-compatible, SSE 流式）

事件序列（每次 yield 一个完整 SSE 行）：
  1. {"type": "citations", "citations": [...]}      — 来源元数据（立即发送）
  2. {"type": "thinking",  "content": "..."}        — 思考过程（enable_thinking=True 时）
  3. {"type": "delta",     "content": "..."}        — 回答增量
  4. {"type": "end"}                                — 流结束

说明：
  - 使用 child_chunk.retrieval_text 作为上下文正文（parent_map 补充 header/page 元数据）
  - 不设置 System Message（遵循 qwen3 最佳实践，将所有指令置于 User Message）
  - enable_thinking 默认 False 以控制延迟
  - httpx 流式读取 DashScope SSE，逐块转发
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.services.retrieval_service import RetrievedChunk

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 上下文构建
# ─────────────────────────────────────────────────────────────

def _build_context_text(
    chunks: list[RetrievedChunk],
    parent_map: dict[str, dict],
) -> str:
    """
    构建 Prompt 中的上下文文本块：

    [来源1] (第X-Y页) Chapter > Section
    {retrieval_text}
    ---
    ...

    - parent_map 提供更精确的 header_path 和页码范围（来自 parent_chunks 表）。
    - 如果没有对应 parent metadata，直接使用 chunk 自身字段。
    """
    parts: list[str] = []
    for i, c in enumerate(chunks, 1):
        parent = parent_map.get(c.parent_chunk_id, {})

        # 优先用 parent header，再用 child header
        hp: list[str] = (
            parent.get("header_path")
            or c.header_path
            or []
        )
        # 优先用 parent 页码（覆盖范围更大），再用 child 页码
        page_start: int = parent.get("page_span_start", c.page_span_start)
        page_end: int = parent.get("page_span_end", c.page_span_end)

        # 页码显示（1-indexed）
        if page_start == page_end:
            page_info = f"第{page_start + 1}页"
        else:
            page_info = f"第{page_start + 1}-{page_end + 1}页"

        path_str = " > ".join(hp) if hp else "（无标题）"
        text = c.retrieval_text or "（内容为空）"

        parts.append(f"[来源{i}] ({page_info}) {path_str}\n{text}")

    return "\n---\n".join(parts)


# ─────────────────────────────────────────────────────────────
# 流式问答
# ─────────────────────────────────────────────────────────────

async def stream_answer(
    query: str,
    chunks: list[RetrievedChunk],
    parent_map: dict[str, dict],
    *,
    enable_thinking: bool = False,
) -> AsyncIterator[str]:
    """
    流式问答生成器。每次 yield 一个 SSE 事件字符串（含结尾 \\n\\n）。

    Args:
        query:          用户问题
        chunks:         重排后的 RetrievedChunk 列表（已降序）
        parent_map:     {parent_chunk_id: {...}} 来自 fetch_parent_chunks
        enable_thinking: 是否开启 qwen3 深度思考模式（默认 False）
    """
    # ── 1. 立即发送引用来源 ────────────────────────────────────
    citations = []
    for i, c in enumerate(chunks, 1):
        parent = parent_map.get(c.parent_chunk_id, {})
        hp = parent.get("header_path") or c.header_path or []
        citations.append({
            "index": i,
            "child_chunk_id": c.child_chunk_id,
            "parent_chunk_id": c.parent_chunk_id,
            "doc_id": c.doc_id,
            "header_path": hp,
            "page_span_start": parent.get("page_span_start", c.page_span_start),
            "page_span_end": parent.get("page_span_end", c.page_span_end),
            "bbox_norm1000": c.bbox_norm1000,
            "bbox_page": c.bbox_page,
            "anchor_origin_pdf_path": c.anchor_origin_pdf_path,
            "retrieval_text": c.retrieval_text[:300],   # 截断避免响应过大
            "score": round(c.score, 4),
        })
    yield f"data: {json.dumps({'type': 'citations', 'citations': citations}, ensure_ascii=False)}\n\n"

    # ── 2. 构建 User Message ──────────────────────────────────
    context_text = _build_context_text(chunks, parent_map)
    source_count = len(chunks)
    user_content = (
        f"请根据以下{source_count}段参考资料回答问题。\n\n"
        f"【参考资料】\n{context_text}\n\n"
        f"【问题】\n{query}\n\n"
        f"要求：\n"
        f"1. 直接基于参考资料内容作答，在适当位置标注来源，如[来源1]、[来源2]。\n"
        f"2. 若参考资料不足以回答，请说明【参考资料中未找到相关信息】。\n"
        f"3. 回答语言与问题一致（中文问题用中文回答）。"
    )

    messages = [{"role": "user", "content": user_content}]

    # ── 3. 调用 qwen3.5-plus（SSE 流式）────────────────────────
    payload = {
        "model": settings.qa_model,
        "messages": messages,
        "stream": True,
        "enable_thinking": enable_thinking,
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = f"{settings.dashscope_base_url}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    err_msg = f"QA API 错误: HTTP {resp.status_code} — {body.decode()[:300]}"
                    logger.error(err_msg)
                    yield f"data: {json.dumps({'type': 'error', 'message': err_msg}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk_obj.get("choices", [{}])[0].get("delta", {})

                    # 思考内容（enable_thinking=True 时才会出现）
                    thinking = delta.get("reasoning_content")
                    if thinking:
                        yield (
                            f"data: {json.dumps({'type': 'thinking', 'content': thinking}, ensure_ascii=False)}\n\n"
                        )

                    # 回答正文
                    content = delta.get("content")
                    if content:
                        yield (
                            f"data: {json.dumps({'type': 'delta', 'content': content}, ensure_ascii=False)}\n\n"
                        )

    except httpx.TimeoutException:
        err = "请求超时（>120s），请稍后重试或缩短上下文"
        logger.warning("QA 请求超时: %s", query[:80])
        yield f"data: {json.dumps({'type': 'error', 'message': err}, ensure_ascii=False)}\n\n"
    except Exception:
        logger.exception("QA 流式生成异常")
        yield f"data: {json.dumps({'type': 'error', 'message': '内部错误，请稍后重试'}, ensure_ascii=False)}\n\n"

    # ── 4. 结束标志 ────────────────────────────────────────────
    yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"
