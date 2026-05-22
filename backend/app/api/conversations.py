"""
多轮对话 API

路由前缀：/api/conversations
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import conversation_service

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
    """流式发送消息并获取 AI 回复（SSE）。"""
    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    return StreamingResponse(
        conversation_service.stream_completion(
            conversation_id,
            req.content,
            user_metadata=req.metadata,
            extra_system_for_this_turn=req.extra_system,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{conversation_id}/fork")
async def fork_conversation(conversation_id: str, req: ForkRequest):
    new_conv_id = await conversation_service.fork_conversation(
        source_conversation_id=conversation_id,
        fork_after_message_id=req.fork_after_message_id,
        new_title=req.new_title,
    )
    conv = await conversation_service.get_conversation(new_conv_id)
    msgs = await conversation_service.list_messages(new_conv_id)
    return {**conv, "messages": msgs}
