"""
多轮对话服务：会话 CRUD、消息持久化、Fork、流式生成。

支持场景：lecture_review / course_info / general
Fork 语义：在指定 message 处截断，复制历史到新会话，主线不受影响。
流式生成与 qa_service.stream_llm_completion 共用底层 LLM 调用。
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.db.database import get_db


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
) -> str:
    """追加消息并返回 message_id；自动计算 sequence_num。"""
    msg_id = str(uuid.uuid4())
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


# ──────────── 流式生成 ────────────

async def stream_completion(
    conversation_id: str,
    user_content: str,
    *,
    user_metadata: dict | None = None,
    extra_system_for_this_turn: str | None = None,
    inject_context_chunks: list | None = None,
) -> AsyncIterator[str]:
    """
    向会话追加 user message，流式生成 assistant 回复，落库后发 end 事件。
    yield SSE 字符串（含结尾 \\n\\n）。
    """
    from app.services.qa_service import stream_llm_completion

    conv = await get_conversation(conversation_id)
    if not conv:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="会话不存在")

    # 1. 写入 user message
    user_msg_id = await append_message(
        conversation_id, "user", user_content, metadata=user_metadata or {}
    )
    yield _sse({"type": "user_message_appended", "message_id": user_msg_id})

    # 2. 组装 OpenAI messages 数组
    msgs = await list_messages(conversation_id)
    openai_msgs: list[dict] = []

    # 插入 extra_system（仅本轮）
    if extra_system_for_this_turn:
        openai_msgs.append({"role": "system", "content": extra_system_for_this_turn})

    for m in msgs:
        if m["role"] == "system":
            openai_msgs.append({"role": "system", "content": m["content"]})
        elif m["role"] == "user":
            openai_msgs.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            openai_msgs.append({"role": "assistant", "content": m["content"]})

    # 3. 如有 RAG 注入，改写最后一条 user message
    if inject_context_chunks:
        for i in range(len(openai_msgs) - 1, -1, -1):
            if openai_msgs[i]["role"] == "user":
                openai_msgs[i]["content"] = _build_rag_content(
                    openai_msgs[i]["content"], inject_context_chunks
                )
                break

    # 4. 流式调用 LLM
    accumulated_content: list[str] = []
    accumulated_thinking: list[str] = []

    async for evt in stream_llm_completion(openai_msgs, enable_thinking=conv["enable_thinking"]):
        if evt["type"] == "thinking":
            accumulated_thinking.append(evt["content"])
            yield _sse({"type": "thinking", "content": evt["content"]})
        elif evt["type"] == "delta":
            accumulated_content.append(evt["content"])
            yield _sse({"type": "delta", "content": evt["content"]})
        elif evt["type"] == "error":
            yield _sse({"type": "error", "message": evt["message"]})

    # 5. 落库 assistant message
    assistant_msg_id = await append_message(
        conversation_id, "assistant",
        content="".join(accumulated_content),
        thinking="".join(accumulated_thinking),
        citations=inject_context_chunks or [],
    )
    yield _sse({"type": "assistant_message_appended", "message_id": assistant_msg_id})
    yield _sse({"type": "end"})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_rag_content(user_content: str, chunks: list) -> str:
    lines = ["以下是相关参考资料：\n"]
    for i, c in enumerate(chunks, 1):
        text = c.get("retrieval_text") or c.get("content") or ""
        lines.append(f"[来源{i}]\n{text}\n")
    lines.append(f"\n【问题】\n{user_content}")
    return "\n".join(lines)
