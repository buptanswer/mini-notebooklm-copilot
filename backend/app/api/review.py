"""
课后复习 API（模块七）

路由前缀：/api/review
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import conversation_service, lecture_review_service

router = APIRouter(prefix="/api/review", tags=["review"])


class GenerateRequest(BaseModel):
    date: str
    course_name: str | None = None
    time_descriptor: str = ""
    user_identity: str = ""
    enable_thinking: bool = False


class SaveNotesRequest(BaseModel):
    conversation_id: str


class FollowupRequest(BaseModel):
    conversation_id: str
    content: str
    metadata: dict = {}


@router.get("/{kb_id}/dates")
async def list_dates(kb_id: str):
    """列出 KB 中有录音的日期列表。"""
    dates = await lecture_review_service.list_dates(kb_id)
    return {"dates": dates}


@router.get("/{kb_id}/sections")
async def list_sections(kb_id: str, date: str):
    """列出指定日期的录音节次信息。"""
    sections = await lecture_review_service.list_sections(kb_id, date)
    return {"sections": sections}


@router.post("/{kb_id}/generate")
async def generate_notes(kb_id: str, req: GenerateRequest):
    """
    流式生成课后复习讲义（SSE）。
    先检查必要条件后才开流，避免前端拿到 500 错误流。
    """
    # 预检：日期下有录音
    sections = await lecture_review_service.list_sections(kb_id, req.date)
    if not sections:
        raise HTTPException(status_code=404, detail=f"日期 {req.date} 下没有录音文件，请先同步文件夹")

    return StreamingResponse(
        lecture_review_service.generate_notes_streaming(
            kb_id,
            req.date,
            course_name=req.course_name,
            time_descriptor=req.time_descriptor,
            user_identity=req.user_identity,
            enable_thinking=req.enable_thinking,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{kb_id}/save-notes")
async def save_notes(kb_id: str, req: SaveNotesRequest):
    """将指定会话中的讲义保存到磁盘（写回绑定文件夹）。"""
    try:
        saved = await lecture_review_service.save_notes_to_disk(kb_id, req.conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": saved}


@router.get("/{kb_id}/notes")
async def load_notes(kb_id: str, date: str):
    """读取指定日期已保存到磁盘的复习讲义内容。"""
    notes = await lecture_review_service.load_existing_notes(kb_id, date)
    return {"notes": notes}


@router.get("/{kb_id}/conversations")
async def list_conversations(kb_id: str):
    """列出本 KB 的 lecture_review 历史会话。"""
    convs = await conversation_service.list_conversations(kb_id, scenario="lecture_review")
    return {"conversations": convs}


@router.post("/{kb_id}/followup")
async def followup(kb_id: str, req: FollowupRequest):
    """
    在已有 lecture_review 会话内继续追问（SSE，统一词汇）。
    使用 conversation_service.stream_turn 保持完整上下文。
    """
    conv = await conversation_service.get_conversation(req.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conv.get("kb_id") != kb_id:
        raise HTTPException(status_code=403, detail="会话不属于该知识库")

    # 注入 followup system 提示（仅首次 followup 时，如会话无 system message）
    from app.prompts import load_prompt
    msgs = await conversation_service.list_messages(req.conversation_id)
    has_system = any(m["role"] == "system" for m in msgs)
    extra_system = None
    if not has_system:
        extra_system = load_prompt("lecture_review_followup_system")

    async def _stream():
        yield conversation_service.sse_line(
            {"type": "conversation", "conversation_id": req.conversation_id}
        )
        async for chunk in conversation_service.stream_turn(
            req.conversation_id,
            user_content=req.content,
            user_metadata=req.metadata,
            extra_system_for_this_turn=extra_system,
        ):
            yield chunk
        yield conversation_service.sse_line(
            {"type": "done", "conversation_id": req.conversation_id}
        )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
