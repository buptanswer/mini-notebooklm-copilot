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

import base64
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from app.config import settings
from app.services.retrieval_service import RetrievedChunk

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 多模态图片附件（命中图片类切片时把原图传给视觉模型）
# ─────────────────────────────────────────────────────────────

_IMAGE_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
}
_MAX_IMAGE_BYTES = 4_000_000   # 单图上限，过大跳过避免请求体爆掉


def image_to_data_url(path: str) -> str | None:
    """读取本地图片 → base64 data URL；不存在/过大/异常返回 None。"""
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > _MAX_IMAGE_BYTES:
            return None
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        mime = _IMAGE_MIME.get(p.suffix.lower().lstrip("."), "image/jpeg")
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def collect_image_paths(chunks: list[RetrievedChunk], limit: int) -> list[str]:
    """从命中切片收集去重、存在于磁盘的图片本地路径（限量；limit<=0 表示不取图）。"""
    if limit <= 0:
        return []
    out: list[str] = []
    for c in chunks:
        for p in c.asset_paths:
            if p and p not in out and Path(p).is_file():
                out.append(p)
                if len(out) >= limit:
                    return out
    return out


def build_multimodal_user_content(text: str, image_paths: list[str]) -> list[dict]:
    """把「文本 + 若干图片」组装成多模态 user message 的 content 数组（图片统一追加在文本后）。

    用于不带位置信息的简单场景（旧 /chat 直答端点）。主对话用
    build_multimodal_content_from_sources（图片插到父块原位）。
    """
    parts: list[dict] = [{"type": "text", "text": text}]
    for i, p in enumerate(image_paths, 1):
        url = image_to_data_url(p)
        if url:
            parts.append({"type": "text", "text": f"（下图为命中内容中的图片 {i}）"})
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def build_multimodal_content_from_sources(
    intro: str, sources: list[dict], question: str
) -> list[dict]:
    """从 render_qa_sources 的 sources 构建多模态 user content：**图片插到其在父块中的原位**。

    每条来源：先 [来源N] 头，再按 segments 顺序输出 text / image 片段（text→image→text 交错），
    模型即可知道图片夹在哪两段文字之间；无 segments（回退）则注入该来源纯文本。
    """
    parts: list[dict] = [{"type": "text", "text": intro}]
    for i, s in enumerate(sources, 1):
        hp = " > ".join(s.get("header_path") or []) or "（无标题）"
        ps, pe = s.get("page_span_start", 0), s.get("page_span_end", 0)
        page = f"第{ps + 1}页" if ps == pe else f"第{ps + 1}-{pe + 1}页"
        parts.append({"type": "text", "text": f"\n[来源{i}] {page} · {hp}"})
        segs = s.get("segments")
        if segs:
            for seg in segs:
                if seg.get("type") == "text" and (seg.get("text") or "").strip():
                    parts.append({"type": "text", "text": seg["text"]})
                elif seg.get("type") == "image":
                    url = image_to_data_url(seg.get("path", ""))
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            parts.append({"type": "text", "text": s.get("text", "")})
    parts.append({"type": "text", "text": f"\n【我的问题】\n{question}"})
    return parts


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
        # Small-to-Big：命中子块 → 优先喂其所在父块全文（回退 preview / 子块文本）
        text = (
            (parent.get("text_full") or "").strip()
            or (parent.get("text_preview") or "").strip()
            or c.retrieval_text
            or "（内容为空）"
        )[:2000]

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
    user_text = (
        f"以下是从知识库中检索到的 {source_count} 条相关文档片段，请基于这些内容回答我的问题。\n\n"
        f"【参考资料】\n{context_text}\n\n"
        f"【我的问题】\n{query}"
    )

    # 命中图片类切片时，把原图一并传给视觉模型（多模态问答）
    image_paths = (
        collect_image_paths(chunks, settings.qa_multimodal_max_images)
        if settings.qa_enable_multimodal else []
    )
    use_multimodal = bool(image_paths)
    user_content: object = (
        build_multimodal_user_content(user_text, image_paths) if use_multimodal else user_text
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # ── 3. 调用 QA 模型（SSE 流式；命中图片走多模态视觉模型）──────────
    async for evt in stream_llm_completion(
        messages, enable_thinking=enable_thinking, multimodal=use_multimodal,
    ):
        if evt["type"] == "thinking":
            yield f"data: {json.dumps({'type': 'thinking', 'content': evt['content']}, ensure_ascii=False)}\n\n"
        elif evt["type"] == "delta":
            yield f"data: {json.dumps({'type': 'delta', 'content': evt['content']}, ensure_ascii=False)}\n\n"
        elif evt["type"] == "error":
            yield f"data: {json.dumps({'type': 'error', 'message': evt['message']}, ensure_ascii=False)}\n\n"

    # ── 4. 结束标志 ────────────────────────────────────────────
    yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────────────────────
# 底层 LLM 流式调用（共用基础，不含 SSE 包装）
# ─────────────────────────────────────────────────────────────

async def stream_llm_completion(
    messages: list[dict],
    *,
    enable_thinking: bool = False,
    model: str | None = None,
    multimodal: bool = False,
) -> AsyncIterator[dict]:
    """
    底层流式 LLM 调用。yield 标准化 dict 事件（无 SSE 包装）：
      {"type": "thinking", "content": "..."}
      {"type": "delta",    "content": "..."}
      {"type": "error",    "message": "..."}
      {"type": "end"}
    conversation_service 与 stream_answer 共用此函数。

    multimodal=True：消息含图片（content 为多模态数组），强制走 DashScope 的视觉模型
      （qa_multimodal_model，默认 qwen-vl-max），与可切换的文本 QA Provider 解耦；
      视觉模型不返回 reasoning_content，故关闭 thinking。
    """
    if multimodal:
        use_model = model or settings.qa_multimodal_model
        base_url = settings.dashscope_base_url.rstrip("/")
        api_key = settings.dashscope_api_key
        enable_thinking = False
    else:
        use_model = model or settings.qa_model
        base_url = settings.effective_qa_base_url
        api_key = settings.effective_qa_api_key

    payload: dict = {
        "model": use_model,
        "messages": messages,
        "stream": True,
    }
    if enable_thinking:
        payload["enable_thinking"] = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = f"{base_url}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    err_msg = f"QA API 错误: HTTP {resp.status_code} — {body.decode()[:300]}"
                    logger.error(err_msg)
                    yield {"type": "error", "message": err_msg}
                    yield {"type": "end"}
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
                    thinking = delta.get("reasoning_content")
                    if thinking:
                        yield {"type": "thinking", "content": thinking}
                    content = delta.get("content")
                    if content:
                        yield {"type": "delta", "content": content}

    except httpx.TimeoutException:
        logger.warning("LLM 请求超时")
        yield {"type": "error", "message": "请求超时（>120s），请稍后重试或缩短上下文"}
    except Exception:
        logger.exception("LLM 流式生成异常")
        yield {"type": "error", "message": "内部错误，请稍后重试"}

    yield {"type": "end"}


async def call_llm_json(
    messages: list[dict],
    *,
    model: str | None = None,
) -> str:
    """
    非流式 LLM 调用，返回完整响应文本。
    用于结构化 JSON 抽取场景（课程管家信息抽取等）。
    """
    payload: dict = {
        "model": model or settings.qa_model,
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.effective_qa_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.effective_qa_base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
