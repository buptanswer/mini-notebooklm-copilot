"""
文档管理 API（上传、解析触发、状态查询、删除）
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.db.database import get_db

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── Response Models ───────────────────────────────────────

class DocInfo(BaseModel):
    doc_id: str
    kb_id: str
    filename: str
    relative_path: str = ""
    source_format: str
    file_size: int
    page_count: int
    status: str            # uploaded / parsing / needs_review / indexed / failed / text_only / missing
    warnings: str = ""    # 解析警告（needs_review 时有内容）
    origin_pdf_path: str = ""  # 用于 PDF 预览
    folder_category: str = ""  # recording / slides / homework / notice / review_note / ''
    bound_file_path: str = ""  # 绑定文件夹模式下的文件绝对路径
    created_at: str
    updated_at: str


class DocListResponse(BaseModel):
    items: list[DocInfo]


# ── Helpers ───────────────────────────────────────────────

_SUPPORTED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".png", ".jpg", ".jpeg",
                          ".txt", ".md"}
_DOC_SELECT = """
    SELECT doc_id, kb_id, filename,
           COALESCE(relative_path, filename) AS relative_path,
           source_format, file_size, page_count,
           status, COALESCE(warnings,'') AS warnings,
           COALESCE(origin_pdf_path,'') AS origin_pdf_path,
           COALESCE(folder_category,'') AS folder_category,
           COALESCE(bound_file_path,'') AS bound_file_path,
           created_at, updated_at
    FROM documents
"""


def _detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": "pdf", ".ppt": "pptx", ".pptx": "pptx",
        ".doc": "docx", ".docx": "docx",
        ".png": "png", ".jpg": "jpg", ".jpeg": "jpeg",
        ".txt": "txt", ".md": "md",
    }
    return mapping.get(ext, "unknown")


def _sanitize_relative_path(relative_path: str) -> str:
    """规范化逻辑路径，防止路径穿越。"""
    normalized = relative_path.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail="relative_path 非法")
    return "/".join(parts)


# ── 上传文件 ──────────────────────────────────────────────

@router.post("/{kb_id}/upload", response_model=DocInfo)
async def upload_document(
    kb_id: str,
    file: UploadFile,
    relative_path: str | None = Form(default=None),
):
    """上传文件到指定知识库（仅保存，不自动解析，需单独调用 /parse）。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    display_name = Path(file.filename).name
    ext = Path(display_name).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    logical_path = _sanitize_relative_path(relative_path or display_name)
    if not logical_path:
        logical_path = display_name

    doc_id = str(uuid.uuid4())
    settings.ensure_dirs()
    doc_dir = settings.upload_dir / kb_id / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    upload_path = doc_dir / display_name

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = upload_path.stat().st_size
    source_format = _detect_format(display_name)
    # .txt/.md 无需 MinerU，直接标记为可用
    initial_status = "text_only" if source_format in ("txt", "md") else "uploaded"
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    try:
        cursor = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="知识库不存在")

        await db.execute(
            """INSERT INTO documents
               (doc_id, kb_id, filename, relative_path, source_format, file_size, upload_path,
                status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, kb_id, display_name, logical_path, source_format, file_size, str(upload_path),
             initial_status, now, now),
        )
        await db.execute(
            "UPDATE knowledge_bases SET file_count = file_count + 1, updated_at = ? WHERE kb_id = ?",
            (now, kb_id),
        )
        await db.commit()

        return DocInfo(
            doc_id=doc_id, kb_id=kb_id, filename=display_name,
            relative_path=logical_path,
            source_format=source_format, file_size=file_size, page_count=0,
            status=initial_status, created_at=now, updated_at=now,
        )
    finally:
        await db.close()


# ── 查询文档 ──────────────────────────────────────────────

@router.get("/{kb_id}", response_model=DocListResponse)
async def list_documents(kb_id: str):
    db = await get_db()
    try:
        cur = await db.execute(
            _DOC_SELECT + "WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
        )
        rows = await cur.fetchall()
        return DocListResponse(items=[DocInfo(**dict(r)) for r in rows])
    finally:
        await db.close()


@router.get("/{kb_id}/{doc_id}", response_model=DocInfo)
async def get_document(kb_id: str, doc_id: str):
    """获取单个文档（含 status，可用于轮询解析状态）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            _DOC_SELECT + "WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocInfo(**dict(row))
    finally:
        await db.close()


# ── 触发解析 ──────────────────────────────────────────────

@router.post("/{kb_id}/{doc_id}/parse", summary="触发文档解析流水线")
async def trigger_parse(kb_id: str, doc_id: str, bg: BackgroundTasks):
    """
    异步触发解析流水线（MinerU → IR → Chunk → Embed → Index）。
    文档必须是 uploaded / failed / needs_review 状态才能重新触发。
    """
    from app.services.pipeline_service import run_parse_pipeline

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, filename, source_format, upload_path, bound_file_path, status FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
        if r["source_format"] in ("txt", "md"):
            raise HTTPException(status_code=400, detail="txt/md 文件无需解析（已直接可用）")
        if r["status"] not in ("uploaded", "failed", "needs_review"):
            raise HTTPException(
                status_code=409,
                detail=f"当前状态 '{r['status']}' 无法重新解析",
            )
        # 兼容文件夹同步模式：upload_path 为空时使用 bound_file_path
        effective_path_str = r["upload_path"] or r["bound_file_path"] or ""
        if not effective_path_str or not Path(effective_path_str).exists():
            raise HTTPException(status_code=400, detail="原始文件不存在，请检查文件是否在磁盘上")
    finally:
        await db.close()

    bg.add_task(
        run_parse_pipeline,
        doc_id=r["doc_id"],
        kb_id=r["kb_id"],
        upload_path=Path(effective_path_str),
        filename=r["filename"],
        source_format=r["source_format"],
    )
    return {"detail": "解析任务已启动", "doc_id": doc_id}


# ── 删除文档 ──────────────────────────────────────────────

@router.delete("/{kb_id}/{doc_id}", summary="删除文档及其所有数据")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档：清除 Qdrant 向量、SQLite 所有相关记录、本地文件。"""
    from app.db.qdrant_client import get_qdrant
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, upload_path FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)

        # 1. 清除 Qdrant 向量（失败不阻断删除）
        try:
            client = get_qdrant()
            client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    )
                ),
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Qdrant 删除失败（继续）: %s", exc)

        # 2. 清除 SQLite（按 FK 顺序）
        await db.execute("DELETE FROM child_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM parent_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM assets WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM tasks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
        await db.execute(
            "UPDATE knowledge_bases SET file_count = MAX(0, file_count - 1), updated_at=? WHERE kb_id=?",
            (datetime.now(timezone.utc).isoformat(), kb_id),
        )
        await db.commit()
    finally:
        await db.close()

    # 3. 删除本地文件（失败不影响请求）
    try:
        p = Path(r["upload_path"])
        if p.parent.exists():
            shutil.rmtree(p.parent, ignore_errors=True)
    except Exception:
        pass

    return {"detail": "已删除", "doc_id": doc_id}


# ── 获取原始 PDF ──────────────────────────────────────────

@router.get("/{kb_id}/{doc_id}/origin-pdf", summary="获取 origin.pdf 文件")
async def get_origin_pdf(kb_id: str, doc_id: str):
    """返回 *_origin.pdf 文件，前端 iframe 嵌入 + #page=N 跳转。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT origin_pdf_path FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        path_str = (dict(row).get("origin_pdf_path") or "").strip()
    finally:
        await db.close()

    if not path_str or not Path(path_str).exists():
        raise HTTPException(status_code=404, detail="origin.pdf 尚未生成（请先完成文档解析）")

    return FileResponse(
        path=path_str,
        media_type="application/pdf",
        filename=f"{doc_id}_origin.pdf",
        headers={"Content-Disposition": "inline"},
    )


# ── 读取 txt/md 原文 ──────────────────────────────────────

@router.get("/{kb_id}/{doc_id}/raw-text", summary="读取 txt/md 文件原文")
async def get_raw_text(kb_id: str, doc_id: str):
    """返回 txt/md 文件的纯文本内容（UTF-8）。仅限 source_format in (txt, md)。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT source_format, upload_path, bound_file_path FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
    finally:
        await db.close()

    if r["source_format"] not in ("txt", "md"):
        raise HTTPException(status_code=400, detail="仅支持 txt/md 格式文件")

    # 优先用 bound_file_path（文件夹绑定），否则用 upload_path
    path_str = (r.get("bound_file_path") or "").strip() or (r.get("upload_path") or "").strip()
    if not path_str or not Path(path_str).exists():
        raise HTTPException(status_code=404, detail="文件不存在于磁盘，请重新同步")

    text = Path(path_str).read_text(encoding="utf-8", errors="replace")
    return {"doc_id": doc_id, "text": text, "path": path_str}
