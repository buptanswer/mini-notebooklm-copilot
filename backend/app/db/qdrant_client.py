"""
Qdrant 向量数据库客户端初始化

职责：
- 初始化本地 Qdrant 存储（使用文件系统模式，无需单独启动服务）
- 创建 child_chunks collection
- 提供全局客户端实例
"""

from __future__ import annotations

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import settings

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    """获取/初始化 Qdrant 客户端（本地文件存储模式）"""
    global _client
    if _client is None:
        settings.ensure_dirs()
        _client = QdrantClient(path=str(settings.qdrant_path))
        logger.info("Qdrant 客户端初始化完成 (path={})", settings.qdrant_path)
    return _client


def init_qdrant() -> None:
    """确保 collection 存在"""
    client = get_qdrant()
    collections = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "Qdrant collection '{}' 创建完成 (dim={})",
            settings.qdrant_collection,
            settings.embedding_dim,
        )
    else:
        logger.info("Qdrant collection '{}' 已存在", settings.qdrant_collection)
