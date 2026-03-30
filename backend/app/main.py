"""
Mini-NotebookLM 后端入口

启动方式: uv run uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import chat, documents, health, kb, tasks
from app.config import settings
from app.db.database import init_db
from app.db.qdrant_client import init_qdrant


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库和向量库"""
    settings.ensure_dirs()
    await init_db()
    init_qdrant()
    logger.info("Mini-NotebookLM 后端启动完成")
    yield
    logger.info("Mini-NotebookLM 后端关闭")


app = FastAPI(
    title="Mini-NotebookLM",
    description="面向大学生的多模态课程知识库与 AI 辅导系统",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────
app.include_router(health.router)
app.include_router(kb.router)
app.include_router(documents.router)
app.include_router(tasks.router)
app.include_router(chat.router)
