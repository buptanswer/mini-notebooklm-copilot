"""
知识库管理 API
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from app.config import settings
from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# ── Request / Response ────────────────────────────────────

KBType = Literal["general", "course"]   # 通用 / 课程


class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    kb_type: KBType = "general"          # 课程知识库自动展示三个场景模块入口
    bound_folder_path: str = ""          # 绑定的本地文件夹路径，空字符串表示传统上传模式


class KBUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    kb_type: KBType | None = None
    bound_folder_path: str | None = None


class KBInfo(BaseModel):
    kb_id: str
    name: str
    description: str
    kb_type: str = "general"
    bound_folder_path: str = ""
    created_at: str
    updated_at: str
    file_count: int
    status: str


class KBListResponse(BaseModel):
    items: list[KBInfo]


_KB_SELECT = """
    SELECT kb_id, name, description,
           COALESCE(kb_type,'general') AS kb_type,
           COALESCE(bound_folder_path,'') AS bound_folder_path,
           created_at, updated_at, file_count, status
    FROM knowledge_bases
"""


# ── Routes ────────────────────────────────────────────────

@router.post("", response_model=KBInfo)
async def create_knowledge_base(req: KBCreateRequest):
    kb_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO knowledge_bases
               (kb_id, name, description, kb_type, bound_folder_path, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (kb_id, req.name, req.description, req.kb_type, req.bound_folder_path, now, now),
        )
        await db.commit()
        return KBInfo(
            kb_id=kb_id,
            name=req.name,
            description=req.description,
            kb_type=req.kb_type,
            bound_folder_path=req.bound_folder_path,
            created_at=now,
            updated_at=now,
            file_count=0,
            status="active",
        )
    finally:
        await db.close()


@router.get("", response_model=KBListResponse)
async def list_knowledge_bases():
    db = await get_db()
    try:
        cursor = await db.execute(_KB_SELECT + "ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        items = [KBInfo(**dict(r)) for r in rows]
        return KBListResponse(items=items)
    finally:
        await db.close()


@router.get("/{kb_id}", response_model=KBInfo)
async def get_knowledge_base(kb_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(_KB_SELECT + "WHERE kb_id=?", (kb_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return KBInfo(**dict(row))
    finally:
        await db.close()


@router.patch("/{kb_id}", response_model=KBInfo)
async def update_knowledge_base(kb_id: str, req: KBUpdateRequest):
    """更新知识库名称、描述或类型（PATCH，只更新传入的字段）。"""
    db = await get_db()
    try:
        cursor = await db.execute(_KB_SELECT + "WHERE kb_id=?", (kb_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="知识库不存在")
        current = dict(row)

        new_name = req.name if req.name is not None else current["name"]
        new_desc = req.description if req.description is not None else current["description"]
        new_type = req.kb_type if req.kb_type is not None else current["kb_type"]
        new_folder = req.bound_folder_path if req.bound_folder_path is not None else current["bound_folder_path"]
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "UPDATE knowledge_bases SET name=?, description=?, kb_type=?, bound_folder_path=?, updated_at=? WHERE kb_id=?",
            (new_name, new_desc, new_type, new_folder, now, kb_id),
        )
        await db.commit()
        current.update(name=new_name, description=new_desc, kb_type=new_type,
                       bound_folder_path=new_folder, updated_at=now)
        return KBInfo(**current)
    finally:
        await db.close()


async def _delete_doc_data(doc_id: str) -> None:
    """清除单个文档的 Qdrant 向量、SQLite 记录和本地文件（用于 KB 级联删除）。"""
    import logging
    _logger = logging.getLogger(__name__)

    # 1. Qdrant 向量
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
        _logger.warning("Qdrant 删除失败（继续）: %s", exc)

    # 2. SQLite（按 FK 顺序）
    db = await get_db()
    try:
        await db.execute("DELETE FROM child_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM parent_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM assets WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM tasks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
        await db.commit()
    finally:
        await db.close()

    # 3. 本地文件
    for parent_dir in [settings.upload_dir, settings.mineru_zip_dir, settings.rag_output_dir]:
        try:
            target = parent_dir / doc_id
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        except Exception:
            pass


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="知识库不存在")

        cur = await db.execute("SELECT doc_id FROM documents WHERE kb_id=?", (kb_id,))
        doc_ids = [row[0] for row in await cur.fetchall()]

        for doc_id in doc_ids:
            await _delete_doc_data(doc_id)

        # 删除该 KB 关联的场景数据
        await db.execute("DELETE FROM review_notes WHERE kb_id=?", (kb_id,))
        await db.execute("DELETE FROM course_info_cards WHERE kb_id=?", (kb_id,))
        await db.execute("DELETE FROM exam_questions WHERE kb_id=?", (kb_id,))
        await db.execute(
            "DELETE FROM exam_submissions WHERE kb_id=?", (kb_id,)
        )
        await db.execute("DELETE FROM exam_papers WHERE kb_id=?", (kb_id,))

        # 级联删除多轮对话
        cur2 = await db.execute("SELECT conversation_id FROM conversations WHERE kb_id=?", (kb_id,))
        conv_ids = [r[0] for r in await cur2.fetchall()]
        for cid in conv_ids:
            await db.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        await db.execute("DELETE FROM conversations WHERE kb_id=?", (kb_id,))

        kb_upload_dir = settings.upload_dir / kb_id
        if kb_upload_dir.exists():
            shutil.rmtree(kb_upload_dir, ignore_errors=True)

        await db.execute("DELETE FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        await db.commit()
        return {"detail": "已删除", "cascaded_docs": len(doc_ids)}
    finally:
        await db.close()


@router.post("/{kb_id}/sync-folder")
async def sync_folder(kb_id: str):
    """触发一次文件夹同步，返回 diff 结果（新增/消失/未变化数量）。"""
    from app.services import folder_sync_service
    diff = await folder_sync_service.scan_and_sync(kb_id)
    return diff
