"""
Index Service — 将 Child Chunks + 向量批量写入 Qdrant 和 SQLite

职责：
1. 把 (ChildChunk, vector) 批量 upsert 到 Qdrant collection "child_chunks"
2. 把 ParentChunk 写入 SQLite parent_chunks 表
3. 把 ChildChunk 写入 SQLite child_chunks 表（含 qdrant_point_id）
4. 把块里的 Asset 写入 SQLite assets 表

Qdrant payload 字段（用于混合检索过滤）：
  child_chunk_id, parent_chunk_id, doc_id, section_id,
    chunk_type, header_path, page_span_start, page_span_end,
    bbox_norm1000, bbox_page, anchor_origin_pdf_path

SQLite 写入均使用 INSERT OR REPLACE（幂等，支持重跑）
"""

from __future__ import annotations

import json
import logging
import uuid

from qdrant_client.models import PointStruct

from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from app.models.models_chunk import ChildChunk, ParentChunk
from app.models.models_ir import IRBlock

logger = logging.getLogger(__name__)

_QDRANT_BATCH = 100  # Qdrant 单次 upsert 批量


async def index_chunks(
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
    vectors: list[list[float]],
    blocks: list[IRBlock],
    doc_id: str,
) -> None:
    """
    主入口：写入 Qdrant + SQLite。

    Args:
        parent_chunks: ParentChunk 列表
        child_chunks:  ChildChunk 列表（顺序与 vectors 对应）
        vectors:       每个 ChildChunk 的 embedding 向量
        blocks:        IRBlock 列表（用于写入 assets 表）
        doc_id:        文档 ID
    """
    if len(child_chunks) != len(vectors):
        raise ValueError(
            f"child_chunks ({len(child_chunks)}) 与 vectors ({len(vectors)}) 数量不匹配"
        )

    # 生成 Qdrant point_id（UUID 字符串）
    point_ids = [str(uuid.uuid4()) for _ in child_chunks]

    await _upsert_qdrant(child_chunks, vectors, point_ids)
    await _write_sqlite(parent_chunks, child_chunks, point_ids, blocks, doc_id)

    logger.info(
        "index_chunks 完成: %d parent, %d child → doc_id=%s",
        len(parent_chunks), len(child_chunks), doc_id,
    )


# ─────────────────────────────────────────────────────────────
# Qdrant
# ─────────────────────────────────────────────────────────────

async def _upsert_qdrant(
    child_chunks: list[ChildChunk],
    vectors: list[list[float]],
    point_ids: list[str],
) -> None:
    """批量 upsert 到 Qdrant。"""
    from app.config import settings

    client = get_qdrant()
    collection = settings.qdrant_collection

    points: list[PointStruct] = []
    for cc, vec, pid in zip(child_chunks, vectors, point_ids):
        points.append(PointStruct(
            id=pid,
            vector=vec,
            payload={
                "child_chunk_id": cc.child_chunk_id,
                "parent_chunk_id": cc.parent_chunk_id,
                "doc_id": cc.doc_id,
                "section_id": cc.section_id,
                "chunk_type": cc.chunk_type,
                "header_path": cc.header_path,
                "embedding_text": cc.embedding_text,
                "retrieval_text": cc.retrieval_text,
                "page_span_start": cc.page_span[0] if cc.page_span else 0,
                "page_span_end": cc.page_span[-1] if cc.page_span else 0,
                "bbox_norm1000": cc.bbox_norm1000,
                "bbox_page": cc.bbox_page,
                "anchor_origin_pdf_path": cc.anchor_origin_pdf_path,
            },
        ))

    # 分批 upsert
    for batch_start in range(0, len(points), _QDRANT_BATCH):
        batch = points[batch_start: batch_start + _QDRANT_BATCH]
        client.upsert(collection_name=collection, points=batch)
        logger.debug("Qdrant upsert batch [%d:%d]", batch_start, batch_start + len(batch))

    logger.info("Qdrant upserted %d points → collection=%s", len(points), collection)


# ─────────────────────────────────────────────────────────────
# SQLite
# ─────────────────────────────────────────────────────────────

async def _write_sqlite(
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
    point_ids: list[str],
    blocks: list[IRBlock],
    doc_id: str,
) -> None:
    """写入 parent_chunks / child_chunks / assets 表（INSERT OR REPLACE）。"""
    db = await get_db()
    try:
        # ── parent_chunks ──────────────────────────────────────
        parent_rows = [
            (
                pc.parent_chunk_id,
                pc.doc_id,
                pc.section_id,
                json.dumps(pc.header_path, ensure_ascii=False),
                pc.title,
                pc.page_span[0] if pc.page_span else 0,
                pc.page_span[-1] if pc.page_span else 0,
                json.dumps(pc.block_ids, ensure_ascii=False),
                pc.text_for_generation[:200],  # preview
            )
            for pc in parent_chunks
        ]
        await db.executemany(
            """INSERT OR REPLACE INTO parent_chunks
               (parent_chunk_id, doc_id, section_id, header_path, title,
                page_span_start, page_span_end, block_ids, text_preview)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            parent_rows,
        )

        # ── child_chunks ───────────────────────────────────────
        child_rows = [
            (
                cc.child_chunk_id,
                cc.parent_chunk_id,
                cc.doc_id,
                cc.section_id,
                cc.chunk_type,
                json.dumps(cc.header_path, ensure_ascii=False),
                cc.embedding_text,
                cc.retrieval_text,
                cc.page_span[0] if cc.page_span else 0,
                cc.page_span[-1] if cc.page_span else 0,
                json.dumps(cc.bbox_norm1000, ensure_ascii=False),
                json.dumps(cc.bbox_page, ensure_ascii=False),
                cc.anchor_origin_pdf_path,
                pid,
            )
            for cc, pid in zip(child_chunks, point_ids)
        ]
        await db.executemany(
            """INSERT OR REPLACE INTO child_chunks
               (child_chunk_id, parent_chunk_id, doc_id, section_id, chunk_type,
                header_path, embedding_text, retrieval_text,
                page_span_start, page_span_end,
                bbox_norm1000, bbox_page, anchor_origin_pdf_path,
                qdrant_point_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            child_rows,
        )

        # ── assets ────────────────────────────────────────────
        asset_rows = [
            (
                asset.asset_id,
                doc_id,
                asset.asset_type,
                asset.path,
                asset.usage,
                asset.mime or "",
                blk.block_id,
            )
            for blk in blocks
            for asset in blk.assets
        ]
        if asset_rows:
            await db.executemany(
                """INSERT OR REPLACE INTO assets
                   (asset_id, doc_id, asset_type, path, usage, mime, block_id)
                   VALUES (?,?,?,?,?,?,?)""",
                asset_rows,
            )

        await db.commit()
        logger.info(
            "SQLite 写入完成: %d parent, %d child, %d assets",
            len(parent_rows), len(child_rows), len(asset_rows),
        )
    finally:
        await db.close()
