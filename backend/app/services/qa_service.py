"""
QA Service — 多 Provider 流式问答（OpenAI-compatible, SSE）

支持任意 OpenAI 兼容 Provider（DashScope、DeepSeek、OpenAI 等），
通过 settings.effective_qa_base_url 和 settings.effective_qa_api_key 切换。

事件序列（每次 yield 一个完整 SSE 行）：
  1. {"type": "citations", "citations": [...]}      — 来源元数据（立即发送）
  2. {"type": "thinking",  "content": "..."}        — 思考过程（仅 thinking 模型）
  3. {"type": "delta",     "content": "..."}        — 回答增量
  4. {"type": "end"}                                — 流结束

enable_thinking 说明：
  - 仅在 settings.qa_enable_thinking=True 且模型支持时才附加该参数
  - DashScope qwen3 系列：支持 enable_thinking
  - DeepSeek deepseek-reasoner：无需此参数，模型自动返回 reasoning_content
  - DeepSeek deepseek-chat / OpenAI gpt-4o：不支持，会被自动过滤
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
# 系统提示词
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一个专业的知识库问答助手。你的任务是根据用户提供的知识库文档片段，准确、全面地回答用户的问题。

## 核心原则

1. **忠实于来源**：答案必须严格基于提供的参考资料，不要凭空捏造内容。
2. **引用标注**：在回答中适当位置标注来源编号，如 [来源1]、[来源2]，方便用户核查。
3. **综合多源**：若多个来源共同支持某个结论，可综合引用，如 [来源1][来源3]。
4. **诚实说明不足**：若参考资料不足以完整回答问题，明确说明"参考资料中未找到相关信息"，不要猜测或补充训练数据中的知识（除非用户明确要求）。
5. **语言一致**：回答语言与问题语言一致（中文问题用中文回答）。

## 格式要求

- 对于复杂问题，使用结构化格式（标题、列表、分段）提升可读性。
- 对于简单问题，直接简洁作答。
- 涉及数字、公式、表格内容时，保持精确，不要随意四舍五入或简化。
- 如有多个步骤或要点，用有序列表或无序列表组织。"""


# ─────────────────────────────────────────────────────────────
# 上下文构建
# ─────────────────────────────────────────────────────────────

def _build_context_text(
    chunks: list[RetrievedChunk],
    parent_map: dict[str, dict],
) -> str:
    """
    构建 Prompt 中的上下文文本块，格式：

    [来源1] 文档片段 · 第X-Y页 · Chapter > Section
    {retrieval_text}
    ---
    ...

    策略：
    - 优先用 parent 的 header_path（章节路径更完整）
    - 优先用 parent 的页码范围（覆盖范围更大）
    - retrieval_text 是已经包含 header_path 前缀的检索文本
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
        # retrieval_text 包含 header_path 前缀（如"第一章 > 1.2 方法\n正文..."）
        text = c.retrieval_text or "（内容为空）"

        parts.append(f"[来源{i}] {page_info} · {path_str}\n{text}")

    return "\n---\n".join(parts)


# ─────────────────────────────────────────────────────────────
# 流式问答
# ─────────────────────────────────────────────────────────────

async def stream_answer(
    query: str,
    chunks: list[RetrievedChunk],
    parent_map: dict[str, dict],
    *,
    enable_thinking: bool | None = None,
) -> AsyncIterator[str]:
    """
    流式问答生成器。每次 yield 一个 SSE 事件字符串（含结尾 \\n\\n）。

    Args:
        query:          用户问题
        chunks:         重排后的 RetrievedChunk 列表（已降序）
        parent_map:     {parent_chunk_id: {...}} 来自 fetch_parent_chunks
        enable_thinking: 是否开启思维链（None 时读取 settings.qa_enable_thinking）
    """
    if enable_thinking is None:
        enable_thinking = settings.qa_enable_thinking
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

    # ── 2. 构建消息列表（系统提示 + 用户消息）───────────────────
    context_text = _build_context_text(chunks, parent_map)
    source_count = len(chunks)
    user_content = (
        f"以下是从知识库中检索到的 {source_count} 条相关文档片段，请基于这些内容回答我的问题。\n\n"
        f"【参考资料】\n{context_text}\n\n"
        f"【我的问题】\n{query}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # ── 3. 调用 QA 模型（SSE 流式，支持多 Provider）──────────
    payload: dict = {
        "model": settings.qa_model,
        "messages": messages,
        "stream": True,
    }
    # enable_thinking 仅在显式开启时附加（部分 Provider 不识别该参数会报错）
    if enable_thinking:
        payload["enable_thinking"] = True

    headers = {
        "Authorization": f"Bearer {settings.effective_qa_api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = f"{settings.effective_qa_base_url}/chat/completions"

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
