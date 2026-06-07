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

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from app.models.models_chunk import ChildChunk, ParentChunk
from app.models.models_ir import IRBlock
from app.services.cn_tokenizer import segment as _cn_segment

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

    # 重解析幂等：先清掉该文档旧的 chunk/asset/向量，避免新旧 uuid 并存产生重复命中
    await _purge_doc(doc_id)

    # 生成 Qdrant point_id（UUID 字符串）
    point_ids = [str(uuid.uuid4()) for _ in child_chunks]

    # child_chunk_id → 图片资产本地路径（多模态问答命中图片时传原图用）
    asset_paths_map = _build_asset_paths_map(child_chunks, blocks)

    await _upsert_qdrant(child_chunks, vectors, point_ids, asset_paths_map)
    await _write_sqlite(parent_chunks, child_chunks, point_ids, blocks, doc_id, asset_paths_map)

    logger.info(
        "index_chunks 完成: %d parent, %d child → doc_id=%s",
        len(parent_chunks), len(child_chunks), doc_id,
    )


# ─────────────────────────────────────────────────────────────
# 重解析清理（幂等）
# ─────────────────────────────────────────────────────────────

async def _purge_doc(doc_id: str) -> None:
    """
    清掉文档旧的 chunk/asset（SQLite）与向量（Qdrant）。

    index_chunks 用新 uuid INSERT OR REPLACE，重解析时旧 uuid 的行/点不会被覆盖，
    会与新数据并存导致同一文档重复命中。重解析前先按 doc_id 清空，保证幂等。
    （child_chunks 删除由 FTS 触发器同步 child_chunks_fts。）
    """
    from app.config import settings

    try:
        client = get_qdrant()
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
            ),
        )
    except Exception as exc:
        logger.warning("清理旧向量失败（继续）: %s", exc)

    db = await get_db()
    try:
        await db.execute("DELETE FROM child_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM parent_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM assets WHERE doc_id=?", (doc_id,))
        # 父块自定义索引随文档重建：清定义行（其物化虚拟子块已随 child_chunks DELETE 移除，
        # 对应 Qdrant 点已由上面按 doc_id 的 FilterSelector 一并删除）。
        await db.execute("DELETE FROM parent_extra_indexes WHERE doc_id=?", (doc_id,))
        await db.commit()
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────
# Qdrant
# ─────────────────────────────────────────────────────────────

def _build_asset_paths_map(
    child_chunks: list[ChildChunk],
    blocks: list[IRBlock],
) -> dict[str, list[str]]:
    """child_chunk_id → 其来源块的图片资产本地路径列表（image / chart_image）。"""
    img_by_block: dict[str, list[str]] = {}
    for blk in blocks:
        paths = [a.path for a in blk.assets if a.asset_type in ("image", "chart_image") and a.path]
        if paths:
            img_by_block[blk.block_id] = paths

    out: dict[str, list[str]] = {}
    for cc in child_chunks:
        paths: list[str] = []
        for bid in cc.source_block_ids:
            paths.extend(img_by_block.get(bid, []))
        if paths:
            out[cc.child_chunk_id] = paths
    return out


async def _upsert_qdrant(
    child_chunks: list[ChildChunk],
    vectors: list[list[float]],
    point_ids: list[str],
    asset_paths_map: dict[str, list[str]],
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
                "asset_paths": asset_paths_map.get(cc.child_chunk_id, []),
                "index_kind": cc.index_kind,
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
    asset_paths_map: dict[str, list[str]],
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
                pc.text_for_generation,         # full（Small-to-Big 上下文 / 解析透视）
            )
            for pc in parent_chunks
        ]
        await db.executemany(
            """INSERT OR REPLACE INTO parent_chunks
               (parent_chunk_id, doc_id, section_id, header_path, title,
                page_span_start, page_span_end, block_ids, text_preview, text_full)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
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
                json.dumps(asset_paths_map.get(cc.child_chunk_id, []), ensure_ascii=False),
                cc.index_kind,
                _cn_segment(cc.embedding_text),   # fts_text：jieba 分词供中文 BM25
            )
            for cc, pid in zip(child_chunks, point_ids)
        ]
        await db.executemany(
            """INSERT OR REPLACE INTO child_chunks
               (child_chunk_id, parent_chunk_id, doc_id, section_id, chunk_type,
                header_path, embedding_text, retrieval_text,
                page_span_start, page_span_end,
                bbox_norm1000, bbox_page, anchor_origin_pdf_path,
                qdrant_point_id, asset_paths, index_kind, fts_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
