"""
课后复习 API（模块七）

路由前缀：/api/review
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import conversation_service, lecture_review_service

logger = logging.getLogger(__name__)
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
    conversation_id: str | None = None
    date: str | None = None
    content: str
    metadata: dict = {}
    enable_thinking: bool | None = None
    enable_rag: bool = False

class ExportRequest(BaseModel):
    conversation_id: str | None = None
    date: str | None = None
    format: str = "pdf"


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
    如果 conversation_id 为 None，则基于 date 自动创建会话并灌入已存讲义。
    """
    conv_id = req.conversation_id
    if not conv_id:
        if not req.date:
            raise HTTPException(status_code=400, detail="未提供 conversation_id 时必须提供 date")
        
        # 获取课程名
        from app.db.database import get_db
        db = await get_db()
        try:
            cur = await db.execute("SELECT name FROM knowledge_bases WHERE kb_id=?", (kb_id,))
            row = await cur.fetchone()
            course_name = dict(row)["name"] if row else ""
        finally:
            await db.close()

        # 创建新会话
        conv_id = await conversation_service.create_conversation(
            kb_id=kb_id,
            scenario="lecture_review",
            title=f"{course_name} {req.date} 课后复习",
            metadata={"date": req.date, "course_name": course_name},
            enable_thinking=req.enable_thinking or False,
        )
        
        # 灌入已存讲义
        notes = await lecture_review_service.load_existing_notes(kb_id, req.date)
        for n in notes:
            await conversation_service.append_message(
                conv_id, "assistant", n["content_md"],
                metadata={"kind": "section", "section_num": n["section_num"]}
            )
    else:
        conv = await conversation_service.get_conversation(conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
        if conv.get("kb_id") != kb_id:
            raise HTTPException(status_code=403, detail="会话不属于该知识库")
        # 若前端切换了思维链状态，同步更新会话设置
        if req.enable_thinking is not None and conv.get("enable_thinking") != req.enable_thinking:
            await conversation_service.update_conversation(
                conv_id, enable_thinking=req.enable_thinking
            )

    # 注入 followup system 提示（仅首次 followup 时，如会话无 system message）
    from app.prompts import load_prompt
    msgs = await conversation_service.list_messages(conv_id)
    has_system = any(m["role"] == "system" for m in msgs)
    extra_system = None
    if not has_system:
        extra_system = load_prompt("lecture_review_followup_system")

    async def _stream():
        yield conversation_service.sse_line(
            {"type": "conversation", "conversation_id": conv_id}
        )
        async for chunk in conversation_service.stream_turn(
            conv_id,
            user_content=req.content,
            user_metadata=req.metadata,
            extra_system_for_this_turn=extra_system,
            rag_mode=req.enable_rag,
            enable_thinking=req.enable_thinking,
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
        },
    )


@router.post("/{kb_id}/export")
async def export_notes(kb_id: str, req: ExportRequest):
    """
    将生成的课后复习讲义导出为 PDF 或 Markdown 文件。
    使用本地 pandoc 命令进行编译转换。
    """
    import os
    import tempfile
    import subprocess
    import uuid
    from pathlib import Path
    from fastapi.responses import FileResponse
    from app.db.database import get_db

    # 1. 拼接 Markdown 内容
    md_content = ""
    title = ""
    if req.conversation_id:
        conv = await conversation_service.get_conversation(req.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
        meta = conv.get("metadata") or {}
        date = meta.get("date", "")
        course_name = meta.get("course_name", "")
        title = f"{course_name} {date} 课后复习讲义"

        msgs = await conversation_service.list_messages(req.conversation_id)
        sections = []
        for m in msgs:
            if m["role"] == "assistant":
                sec_num = (m.get("metadata") or {}).get("section_num")
                if sec_num is not None:
                    sections.append((sec_num, m["content"]))
        sections.sort(key=lambda x: x[0])
        md_content = f"# {title}\n\n" + "\n\n".join([f"## 第 {sec_num} 节课堂要点\n\n{content}" for sec_num, content in sections])
    elif req.date:
        notes = await lecture_review_service.load_existing_notes(kb_id, req.date)
        if not notes:
            raise HTTPException(status_code=404, detail="未找到已保存的讲义")
        db = await get_db()
        try:
            cur = await db.execute("SELECT name FROM knowledge_bases WHERE kb_id=?", (kb_id,))
            row = await cur.fetchone()
            course_name = dict(row)["name"] if row else ""
        finally:
            await db.close()
        title = f"{course_name} {req.date} 课后复习讲义"
        md_content = f"# {title}\n\n" + "\n\n".join([f"## 第 {n['section_num']} 节课堂要点\n\n{n['content_md']}" for n in notes])
    else:
        raise HTTPException(status_code=400, detail="必须提供 conversation_id 或 date")

    # 2. 导出 Markdown
    if req.format == "md":
        temp_dir = tempfile.gettempdir()
        md_file = Path(temp_dir) / f"{uuid.uuid4()}.md"
        md_file.write_text(md_content, encoding="utf-8")
        return FileResponse(
            str(md_file),
            media_type="text/markdown",
            filename=f"{title}.md"
        )

    # 3. 导出 PDF (调用本地 pandoc 命令)
    temp_dir = tempfile.gettempdir()
    md_file = Path(temp_dir) / f"{uuid.uuid4()}.md"
    pdf_file = Path(temp_dir) / f"{uuid.uuid4()}.pdf"
    md_file.write_text(md_content, encoding="utf-8")

    try:
        # 优先使用 xelatex 并设置中文字体
        cmd = [
            "pandoc",
            str(md_file),
            "-o",
            str(pdf_file),
            "--pdf-engine=xelatex",
            "-V", "mainfont=Microsoft YaHei",
            "-V", "sansfont=Microsoft YaHei",
            "-V", "monoFrame=Microsoft YaHei",
            "-V", "CJKmainfont=Microsoft YaHei",
        ]
        logger.info("Running pandoc cmd: %s", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="ignore")
        if res.returncode != 0:
            logger.warning("Pandoc PDF generation failed with xelatex: %s. Trying wkhtmltopdf...", res.stderr)
            cmd_wk = [
                "pandoc",
                str(md_file),
                "-o",
                str(pdf_file),
                "--pdf-engine=wkhtmltopdf",
            ]
            res_wk = subprocess.run(cmd_wk, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="ignore")
            if res_wk.returncode != 0:
                raise RuntimeError(
                    f"Pandoc PDF export failed.\nXeLaTeX error: {res.stderr}\nwkhtmltopdf error: {res_wk.stderr}"
                )

        return FileResponse(
            str(pdf_file),
            media_type="application/pdf",
            filename=f"{title}.pdf"
        )
    except Exception as e:
        logger.exception("Pandoc export error")
        raise HTTPException(
            status_code=500,
            detail=f"PDF 导出失败。请确保系统已安装 pandoc 且具备 xelatex 或 wkhtmltopdf 引擎。\n错误详情: {str(e)}"
        )
    finally:
        if md_file.exists():
            try: md_file.unlink()
            except: pass
