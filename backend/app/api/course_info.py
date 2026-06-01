"""
课程管家 API（模块九）

路由前缀：/api/course-info
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import conversation_service, course_info_service

router = APIRouter(prefix="/api/course-info", tags=["course-info"])


class ChatRequest(BaseModel):
    content: str
    conversation_id: str | None = None   # None 时自动创建新会话
    enable_thinking: bool = False


@router.post("/{kb_id}/generate")
async def generate_card(kb_id: str):
    """触发课程信息卡片生成（同步等待，约 10-30s）。"""
    try:
        card = await course_info_service.generate_card(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return card


@router.get("/{kb_id}")
async def get_card(kb_id: str):
    """获取已生成的课程信息卡片，未生成返回 404。"""
    card = await course_info_service.get_card(kb_id)
    if not card:
        raise HTTPException(status_code=404, detail="课程信息卡片尚未生成，请先调用 /generate")
    return card


@router.get("/{kb_id}/upcoming-deadlines")
async def upcoming_deadlines(kb_id: str, within_days: int = 7):
    """返回未来 within_days 天内的截止日，按 days_left 升序。"""
    dls = await course_info_service.upcoming_deadlines(kb_id, within_days)
    return {"deadlines": dls}


@router.delete("/{kb_id}")
async def delete_card(kb_id: str):
    """删除卡片（让用户重新生成）。"""
    from app.db.database import get_db
    db = await get_db()
    try:
        await db.execute("DELETE FROM course_info_cards WHERE kb_id=?", (kb_id,))
        await db.commit()
    finally:
        await db.close()
    return {"detail": "已删除"}


@router.post("/{kb_id}/chat")
async def chat(kb_id: str, req: ChatRequest):
    """针对课程信息的多轮问答（SSE）。"""
    card = await course_info_service.get_card(kb_id)
    if not card:
        raise HTTPException(status_code=404, detail="请先生成课程信息卡片")

    # 获取或创建会话
    conv_id = req.conversation_id
    if not conv_id:
        conv_id = await conversation_service.create_conversation(
            kb_id=kb_id,
            scenario="course_info",
            title="课程管家对话",
            enable_thinking=req.enable_thinking,
        )
    else:
        conv = await conversation_service.get_conversation(conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
        # 若前端切换了思维链状态，同步更新会话设置
        if conv.get("enable_thinking") != req.enable_thinking:
            await conversation_service.update_conversation(
                conv_id, enable_thinking=req.enable_thinking
            )

    # 首次注入系统提示（只有会话无 system message 时注入）
    import json

    from app.prompts import load_prompt
    msgs = await conversation_service.list_messages(conv_id)
    has_system = any(m["role"] == "system" for m in msgs)

    extra_system = None
    if not has_system:
        card_json = json.dumps({
            "course_name": card.get("course_name"),
            "instructor": card.get("instructor"),
            "contact": card.get("contact"),
            "assessment": card.get("assessment"),
            "deadlines": card.get("deadlines"),
            "important_notes": card.get("important_notes"),
        }, ensure_ascii=False, indent=2)
        extra_system = load_prompt("course_info_chat_system", card_json=card_json)

    async def _stream():
        yield conversation_service.sse_line(
            {"type": "conversation", "conversation_id": conv_id}
        )
        async for chunk in conversation_service.stream_turn(
            conv_id,
            user_content=req.content,
            extra_system_for_this_turn=extra_system,
        ):
            yield chunk
        yield conversation_service.sse_line(
            {"type": "done", "conversation_id": conv_id}
        )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )
