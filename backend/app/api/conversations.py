"""
多轮对话 API

路由前缀：/api/conversations
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ── 请求/响应模型 ─────────────────────────────────────────

class CreateConvRequest(BaseModel):
    kb_id: str
    scenario: str
    title: str = ""
    metadata: dict = {}
    enable_thinking: bool = False


class UpdateConvRequest(BaseModel):
    title: str | None = None
    enable_thinking: bool | None = None
    metadata: dict | None = None


class SendMessageRequest(BaseModel):
    content: str
    metadata: dict = {}
    extra_system: str | None = None    # 本轮额外 system 提示（课程管家首次注入卡片用）
    rag_mode: bool = False             # 启用混合检索 RAG（对话问答模式）
    top_k: int = Field(default=5, ge=1, le=20)


class ForkRequest(BaseModel):
    fork_after_message_id: str
    new_title: str = ""


# ── 端点 ──────────────────────────────────────────────────

@router.post("")
async def create_conversation(req: CreateConvRequest):
    conv_id = await conversation_service.create_conversation(
        kb_id=req.kb_id,
        scenario=req.scenario,
        title=req.title,
        metadata=req.metadata,
        enable_thinking=req.enable_thinking,
    )
    conv = await conversation_service.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=500, detail="会话创建后读取失败")
    return {**conv, "messages": []}


@router.get("")
async def list_conversations(kb_id: str, scenario: str | None = None, limit: int = 50):
    return await conversation_service.list_conversations(kb_id, scenario=scenario, limit=limit)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await conversation_service.list_messages(conversation_id)
    return {**conv, "messages": msgs}


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, req: UpdateConvRequest):
    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await conversation_service.update_conversation(
        conversation_id,
        title=req.title,
        enable_thinking=req.enable_thinking,
        metadata=req.metadata,
    )
    return await conversation_service.get_conversation(conversation_id)


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, cascade: bool = False):
    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    await conversation_service.delete_conversation(conversation_id, cascade_children=cascade)
    return {"detail": "已删除", "conversation_id": conversation_id}


@router.post("/{conversation_id}/send")
async def send_message(conversation_id: str, req: SendMessageRequest):
    """流式发送消息并获取 AI 回复（SSE）。支持 rag_mode 混合检索增强。"""
    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    citations: list | None = None
    inject_chunks: list | None = None

    if req.rag_mode:
        citations, inject_chunks = await _fetch_rag_context(
            req.content, conv["kb_id"], req.top_k
        )

    async def _stream():
        if citations:
            yield f"data: {json.dumps({'type': 'citations', 'citations': citations}, ensure_ascii=False)}\n\n"
        async for chunk in conversation_service.stream_completion(
            conversation_id,
            req.content,
            user_metadata=req.metadata,
            extra_system_for_this_turn=req.extra_system,
            inject_context_chunks=inject_chunks,
        ):
            yield chunk

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _fetch_rag_context(
    query: str, kb_id: str, top_k: int
) -> tuple[list | None, list | None]:
    """混合检索 + 重排，返回 (citations, inject_chunks)；失败时降级返回 (None, None)。"""
    try:
        from app.services.retrieval_service import hybrid_search, fetch_parent_chunks
        from app.services.rerank_service import rerank

        hybrid_results = await hybrid_search(
            query, kb_id, vector_limit=20, keyword_limit=20, top_k=15
        )
        if not hybrid_results:
            return None, None

        reranked = await rerank(query, hybrid_results, top_n=top_k)
        parent_ids = list({c.parent_chunk_id for c in reranked})
        parent_map = await fetch_parent_chunks(parent_ids)

        citations = []
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
        return citations, citations
    except Exception:
        logger.warning("RAG 检索失败，降级为纯对话模式", exc_info=True)
        return None, None


@router.post("/{conversation_id}/fork")
async def fork_conversation(conversation_id: str, req: ForkRequest):
    new_conv_id = await conversation_service.fork_conversation(
        source_conversation_id=conversation_id,
        fork_after_message_id=req.fork_after_message_id,
        new_title=req.new_title,
    )
    conv = await conversation_service.get_conversation(new_conv_id)
    if conv is None:
        raise HTTPException(status_code=500, detail="Fork 会话后读取失败")
    msgs = await conversation_service.list_messages(new_conv_id)
    return {**conv, "messages": msgs}
