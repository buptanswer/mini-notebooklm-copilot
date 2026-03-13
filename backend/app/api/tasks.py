"""
任务状态查询 API
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskInfo(BaseModel):
    task_id: str
    doc_id: str
    task_type: str
    status: str
    progress: float
    error_msg: str
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    items: list[TaskInfo]


@router.get("", response_model=TaskListResponse, summary="列出所有最近任务")
async def list_all_tasks(limit: int = 50):
    """返回最近的任务列表（按更新时间降序），用于任务中心页面。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT task_id, doc_id, task_type, status, progress, error_msg, created_at, updated_at FROM tasks ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return TaskListResponse(items=[TaskInfo(**dict(r)) for r in rows])
    finally:
        await db.close()


@router.get("/doc/{doc_id}", response_model=TaskListResponse)
async def list_tasks_by_doc(doc_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT task_id, doc_id, task_type, status, progress, error_msg, created_at, updated_at FROM tasks WHERE doc_id=? ORDER BY created_at DESC",
            (doc_id,),
        )
        rows = await cursor.fetchall()
        return TaskListResponse(items=[TaskInfo(**dict(r)) for r in rows])
    finally:
        await db.close()


@router.get("/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT task_id, doc_id, task_type, status, progress, error_msg, created_at, updated_at FROM tasks WHERE task_id=?",
            (task_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        return TaskInfo(**dict(row))
    finally:
        await db.close()
