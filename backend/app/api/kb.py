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

from app.config import settings
from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# ── Request / Response ────────────────────────────────────

class KBCreateRequest(BaseModel):
    name: str
    description: str = ""


class KBInfo(BaseModel):
    kb_id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    file_count: int
    status: str


class KBListResponse(BaseModel):
    items: list[KBInfo]


# ── Routes ────────────────────────────────────────────────

@router.post("", response_model=KBInfo)
async def create_knowledge_base(req: KBCreateRequest):
    kb_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO knowledge_bases (kb_id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
            (kb_id, req.name, req.description, now, now),
        )
        await db.commit()
        return KBInfo(
            kb_id=kb_id,
            name=req.name,
            description=req.description,
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
        cursor = await db.execute(
            "SELECT kb_id, name, description, created_at, updated_at, file_count, status FROM knowledge_bases ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        items = [KBInfo(**dict(r)) for r in rows]
        return KBListResponse(items=items)
    finally:
        await db.close()


@router.get("/{kb_id}", response_model=KBInfo)
async def get_knowledge_base(kb_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT kb_id, name, description, created_at, updated_at, file_count, status FROM knowledge_bases WHERE kb_id=?",
            (kb_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return KBInfo(**dict(row))
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
        # 检查是否存在
        cursor = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="知识库不存在")

        # 级联删除：获取该 KB 下所有文档，逐个清理
        cur = await db.execute("SELECT doc_id FROM documents WHERE kb_id=?", (kb_id,))
        doc_ids = [row[0] for row in await cur.fetchall()]

        for doc_id in doc_ids:
            await _delete_doc_data(doc_id)

        # 清理未关联文档的孤立上传目录（upload_dir/kb_id/）
        kb_upload_dir = settings.upload_dir / kb_id
        if kb_upload_dir.exists():
            shutil.rmtree(kb_upload_dir, ignore_errors=True)

        # 删除 KB 记录本身
        await db.execute("DELETE FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        await db.commit()
        return {"detail": "已删除", "cascaded_docs": len(doc_ids)}
    finally:
        await db.close()
