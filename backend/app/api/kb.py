"""
知识库管理 API
"""

from __future__ import annotations

import uuid
from datetime import datetime

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_db

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
    now = datetime.utcnow().isoformat()
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


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    db = await get_db()
    try:
        # 检查是否存在
        cursor = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="知识库不存在")
        await db.execute("DELETE FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        await db.commit()
        return {"detail": "已删除"}
    finally:
        await db.close()
