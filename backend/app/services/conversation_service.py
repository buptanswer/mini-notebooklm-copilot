"""
多轮对话服务：会话 CRUD、消息持久化、Fork、流式生成。

支持场景：lecture_review / course_info / general
Fork 语义：在指定 message 处截断，复制历史到新会话，主线不受影响。
流式生成与 qa_service.stream_llm_completion 共用底层 LLM 调用。
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)


# ──────────── 会话 CRUD ────────────

async def create_conversation(
    kb_id: str,
    scenario: str,
    title: str = "",
    metadata: dict | None = None,
    enable_thinking: bool = False,
) -> str:
    """创建并返回 conversation_id。"""
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO conversations
               (conversation_id, kb_id, scenario, title, metadata, enable_thinking, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (conv_id, kb_id, scenario, title,
             json.dumps(metadata or {}, ensure_ascii=False),
             1 if enable_thinking else 0, now, now),
        )
        await db.commit()
    finally:
        await db.close()
    return conv_id


async def get_conversation(conversation_id: str) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM conversations WHERE conversation_id=?", (conversation_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r["metadata"] = json.loads(r.get("metadata") or "{}")
        r["enable_thinking"] = bool(r.get("enable_thinking", 0))
        return r
    finally:
        await db.close()


async def list_conversations(
    kb_id: str,
    scenario: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = await get_db()
    try:
        if scenario:
            cur = await db.execute(
                "SELECT * FROM conversations WHERE kb_id=? AND scenario=? ORDER BY updated_at DESC LIMIT ?",
                (kb_id, scenario, limit),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM conversations WHERE kb_id=? ORDER BY updated_at DESC LIMIT ?",
                (kb_id, limit),
            )
        rows = await cur.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["metadata"] = json.loads(r.get("metadata") or "{}")
            r["enable_thinking"] = bool(r.get("enable_thinking", 0))
            result.append(r)
        return result
    finally:
        await db.close()


async def update_conversation(
    conversation_id: str,
    *,
    title: str | None = None,
    enable_thinking: bool | None = None,
    metadata: dict | None = None,
) -> None:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT title, enable_thinking, metadata FROM conversations WHERE conversation_id=?",
            (conversation_id,),
        )
        row = await cur.fetchone()
        if not row:
            return
        r = dict(row)
        new_title = title if title is not None else r["title"]
        new_thinking = (1 if enable_thinking else 0) if enable_thinking is not None else r["enable_thinking"]
        new_meta = json.dumps(metadata, ensure_ascii=False) if metadata is not None else r["metadata"]
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE conversations SET title=?, enable_thinking=?, metadata=?, updated_at=? WHERE conversation_id=?",
            (new_title, new_thinking, new_meta, now, conversation_id),
        )
        await db.commit()
    finally:
        await db.close()


async def delete_conversation(conversation_id: str, cascade_children: bool = False) -> None:
    db = await get_db()
    try:
        if cascade_children:
            cur = await db.execute(
                "SELECT conversation_id FROM conversations WHERE parent_conversation_id=?",
                (conversation_id,),
            )
            child_ids = [r[0] for r in await cur.fetchall()]
            for cid in child_ids:
                await db.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
                await db.execute("DELETE FROM conversations WHERE conversation_id=?", (cid,))
        await db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
        await db.execute("DELETE FROM conversations WHERE conversation_id=?", (conversation_id,))
        await db.commit()
    finally:
        await db.close()


# ──────────── 消息 CRUD ────────────

async def append_message(
    conversation_id: str,
    role: str,
    content: str,
    *,
    thinking: str = "",
    citations: list | None = None,
    metadata: dict | None = None,
    message_id: str | None = None,
) -> str:
    """追加消息并返回 message_id；自动计算 sequence_num。message_id 可预先指定。"""
    msg_id = message_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COALESCE(MAX(sequence_num), -1) FROM messages WHERE conversation_id=?",
            (conversation_id,),
        )
        row = await cur.fetchone()
        next_seq = (row[0] if row else -1) + 1

        await db.execute(
            """INSERT INTO messages
               (message_id, conversation_id, role, content, thinking, sequence_num,
                citations, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (msg_id, conversation_id, role, content, thinking, next_seq,
             json.dumps(citations or [], ensure_ascii=False),
             json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        await db.execute(
            "UPDATE conversations SET updated_at=? WHERE conversation_id=?",
            (now, conversation_id),
        )
        await db.commit()
    finally:
        await db.close()
    return msg_id


async def list_messages(conversation_id: str) -> list[dict]:
    """按 sequence_num 升序返回该会话的所有消息。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY sequence_num ASC",
            (conversation_id,),
        )
        rows = await cur.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["citations"] = json.loads(r.get("citations") or "[]")
            r["metadata"] = json.loads(r.get("metadata") or "{}")
            result.append(r)
        return result
    finally:
        await db.close()


# ──────────── Fork ────────────

async def fork_conversation(
    source_conversation_id: str,
    fork_after_message_id: str,
    new_title: str = "",
) -> str:
    """
    在指定 message 处 fork 出新会话：
    复制截断后的消息历史到新会话，主线不受影响。
    """
    source = await get_conversation(source_conversation_id)
    if not source:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="源会话不存在")

    all_msgs = await list_messages(source_conversation_id)
    # 截断到 fork_after_message_id（含）
    truncated = []
    for m in all_msgs:
        truncated.append(m)
        if m["message_id"] == fork_after_message_id:
            break

    new_conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO conversations
               (conversation_id, kb_id, scenario, title, parent_conversation_id,
                fork_from_message_id, metadata, enable_thinking, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (new_conv_id, source["kb_id"], source["scenario"],
             new_title or f"[Fork] {source['title']}",
             source_conversation_id, fork_after_message_id,
             json.dumps(source["metadata"], ensure_ascii=False),
             1 if source["enable_thinking"] else 0, now, now),
        )
        for i, m in enumerate(truncated):
            new_msg_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO messages
                   (message_id, conversation_id, role, content, thinking, sequence_num,
                    citations, metadata, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (new_msg_id, new_conv_id, m["role"], m["content"], m.get("thinking", ""),
                 i, json.dumps(m.get("citations", []), ensure_ascii=False),
                 json.dumps(m.get("metadata", {}), ensure_ascii=False), now),
            )
        await db.commit()
    finally:
        await db.close()
    return new_conv_id


# ──────────── 流式生成（统一原语）────────────

def sse_line(data: dict) -> str:
    """Serialize one SSE event line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_turn(
    conversation_id: str,
    *,
    user_content: str,
    hidden_user: bool = False,
    user_metadata: dict | None = None,
    assistant_metadata: dict | None = None,
    extra_system_for_this_turn: str | None = None,
    rag_mode: bool = False,
    top_k: int = 5,
    enable_thinking: bool | None = None,
) -> AsyncIterator[str]:
    """
    统一的"一轮"流式原语：追加 user message →（可选 RAG）→ 流式生成 assistant → 落库。
    发出统一 SSE 词汇（**不含** conversation / done，由调用方负责）：
      message_start {role, message_id, metadata}
      citations     {citations}        # 仅 rag_mode 且检索到内容
      thinking      {content}
      delta         {content}
      message_end   {message_id}
      error         {message}

    hidden_user=True：user message 标记 metadata.hidden（讲义生成的长 prompt+录音），
      不发 message_start、前端不渲染，但仍进入 LLM 上下文。
    assistant_metadata：写入 assistant message 的 metadata（如 {"kind":"section","section_num":N}）。
    """
    from app.services.qa_service import stream_llm_completion

    conv = await get_conversation(conversation_id)
    if not conv:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="会话不存在")

    # 1. 写入 user message
    umeta = dict(user_metadata or {})
    if hidden_user:
        umeta["hidden"] = True
    user_msg_id = await append_message(
        conversation_id, "user", user_content, metadata=umeta
    )
    if not hidden_user:
        yield sse_line({"type": "message_start", "role": "user",
                        "message_id": user_msg_id, "metadata": umeta})

    # 2. 可选 RAG 检索
    citations: list | None = None
    sources: list | None = None
    has_image: bool = False
    if rag_mode:
        citations, sources, has_image = await _fetch_rag_context(
            user_content, conv["kb_id"], top_k
        )
    use_multimodal = has_image and settings.qa_enable_multimodal

    # 3. 组装 OpenAI messages（含隐藏 user，供模型看到完整上下文）
    msgs = await list_messages(conversation_id)
    openai_msgs: list[dict] = []
    if extra_system_for_this_turn:
        openai_msgs.append({"role": "system", "content": extra_system_for_this_turn})
    for m in msgs:
        if m["role"] in ("system", "user", "assistant"):
            openai_msgs.append({"role": m["role"], "content": m["content"]})

    # 4. RAG 注入到最后一条 user message（Small-to-Big 父块上下文；命中图片则按原位组装多模态 content）
    if sources:
        from app.services.qa_service import build_multimodal_content_from_sources
        for i in range(len(openai_msgs) - 1, -1, -1):
            if openai_msgs[i]["role"] == "user":
                user_q = openai_msgs[i]["content"]
                openai_msgs[i]["content"] = (
                    build_multimodal_content_from_sources(_RAG_INTRO, sources, user_q)
                    if use_multimodal
                    else _build_rag_content(user_q, sources)
                )
                break

    # 5. assistant message_start（预生成 id，便于前端绑定 / fork）
    asst_msg_id = str(uuid.uuid4())
    ameta = dict(assistant_metadata or {})
    yield sse_line({"type": "message_start", "role": "assistant",
                    "message_id": asst_msg_id, "metadata": ameta})
    if citations:
        yield sse_line({"type": "citations", "citations": citations})

    # 6. 流式调用 LLM
    acc_content: list[str] = []
    acc_thinking: list[str] = []
    use_thinking = conv["enable_thinking"] if enable_thinking is None else enable_thinking
    async for evt in stream_llm_completion(
        openai_msgs, enable_thinking=use_thinking, multimodal=use_multimodal,
    ):
        if evt["type"] == "thinking":
            acc_thinking.append(evt["content"])
            yield sse_line({"type": "thinking", "content": evt["content"]})
        elif evt["type"] == "delta":
            acc_content.append(evt["content"])
            yield sse_line({"type": "delta", "content": evt["content"]})
        elif evt["type"] == "error":
            yield sse_line({"type": "error", "message": evt["message"]})

    # 7. 落库 assistant message（用预生成 id）
    await append_message(
        conversation_id, "assistant",
        content="".join(acc_content),
        thinking="".join(acc_thinking),
        citations=citations or [],
        metadata=ameta,
        message_id=asst_msg_id,
    )
    yield sse_line({"type": "message_end", "message_id": asst_msg_id})


async def _fetch_rag_context(
    query: str, kb_id: str, top_k: int
) -> tuple[list | None, list | None, bool]:
    """
    全链路检索（query_planner 规划 → 双路 → RRF → 重排，见 retrieval_trace）。
    返回 (citations, sources, has_image)；失败降级 (None, None, False)。
      - citations：每个命中子块的元数据（UI 来源面板 + bbox 高亮，截断展示）。
      - sources：**Small-to-Big** 注入上下文——每条 = 命中子块所在**父块**按块序还原
        （图=VLM描述/原图、表=HTML，均在原位；见 qa_context.render_qa_sources），
        与 citations 一一对应，保持 [来源N] 编号对齐；多模态时每条带有序 segments。
      - has_image：是否有可注入的原图片段（决定走多模态问答）。
    """
    try:
        from app.services.qa_context import render_qa_sources, sources_have_images
        from app.services.retrieval_trace import run_retrieval_pipeline

        result = await run_retrieval_pipeline(query, kb_id, top_k=top_k, build_trace=False)
        reranked = result.chunks
        parent_map = result.parent_map
        if not reranked:
            return None, None, False

        # citations：前端来源面板 + bbox 高亮（截断展示，与 sources 按 [来源N] 同序对齐）
        citations: list[dict] = []
        for i, c in enumerate(reranked, 1):
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
                "retrieval_text": (c.retrieval_text or "")[:300],
                "score": round(c.score, 4),
            })

        # sources：Small-to-Big 上下文，位置保真还原父块（图=描述/原图、表=HTML，均在原位）
        sources = await render_qa_sources(
            reranked, parent_map, multimodal=settings.qa_enable_multimodal
        )
        has_image = sources_have_images(sources)
        return citations, sources, has_image
    except Exception:
        logger.warning("RAG 检索失败，降级为纯对话模式", exc_info=True)
        return None, None, False


_RAG_INTRO = "以下是从知识库检索、并扩展到命中内容所在小节的参考资料：\n"


def _build_rag_content(user_content: str, sources: list) -> str:
    """把 Small-to-Big 的父块上下文拼成提示词（格式与多模态路一致，[来源N] 与引用对齐）。"""
    lines = [_RAG_INTRO]
    for i, s in enumerate(sources, 1):
        hp = " > ".join(s.get("header_path") or []) or "（无标题）"
        ps = s.get("page_span_start", 0)
        pe = s.get("page_span_end", 0)
        page_info = f"第{ps + 1}页" if ps == pe else f"第{ps + 1}-{pe + 1}页"
        lines.append(f"[来源{i}] {page_info} · {hp}\n{s.get('text', '')}\n")
    lines.append(f"\n【我的问题】\n{user_content}")
    return "\n".join(lines)
