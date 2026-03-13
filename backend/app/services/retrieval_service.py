"""
Retrieval Service — 混合检索（向量召回 + 关键词召回 + RRF 融合）

流程：
  1. vector_search  — embed query → Qdrant 语义向量召回（按 kb 过滤 doc_id）
  2. keyword_search — SQLite FTS5/BM25 关键词召回
  3. hybrid_search  — RRF 融合双路结果，返回 top_k

RRF 公式：score(d) = Σ 1/(k + rank_i(d))，k=60

说明：
  - Qdrant payload 存储 doc_id，通过 SQLite 查 kb 下所有 doc_id 后过滤
  - FTS5 使用 unicode61 tokenizer，支持中英文
  - bm25() 返回负数，取反后作为排序分数
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

from qdrant_client.models import FieldCondition, Filter, MatchAny

from app.config import settings
from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from app.services.embedding_service import embed_texts

logger = logging.getLogger(__name__)

_RRF_K = 60          # RRF 平滑常数
_FTS_MAX_TOKENS = 10  # FTS5 查询最大词数


# ─────────────────────────────────────────────────────────────
# 统一检索结果结构
# ─────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    """检索结果统一结构（跨向量 / 关键词两路）"""
    child_chunk_id: str
    parent_chunk_id: str
    doc_id: str
    section_id: str
    chunk_type: str
    retrieval_text: str
    embedding_text: str
    header_path: list[str] = field(default_factory=list)
    page_span_start: int = 0
    page_span_end: int = 0
    bbox_norm1000: list[list[float]] = field(default_factory=list)
    bbox_page: list[list[float]] = field(default_factory=list)
    anchor_origin_pdf_path: str = ""
    qdrant_point_id: str = ""
    score: float = 0.0
    source: str = "unknown"   # "vector" | "keyword" | "hybrid"


# ─────────────────────────────────────────────────────────────
# 辅助：获取 kb 下的文档 ID
# ─────────────────────────────────────────────────────────────

async def _get_kb_doc_ids(kb_id: str) -> list[str]:
    """返回知识库下所有已完成索引的 doc_id 列表。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id FROM documents WHERE kb_id=? AND status IN ('indexed','needs_review','parsed')",
            (kb_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────
# 向量召回
# ─────────────────────────────────────────────────────────────

async def vector_search(
    query_text: str,
    kb_id: str,
    limit: int = 20,
) -> list[RetrievedChunk]:
    """
    语义向量召回：embed query → Qdrant query_points。

    Returns:
        RetrievedChunk 列表，按 Qdrant 相似度降序
    """
    doc_ids = await _get_kb_doc_ids(kb_id)
    if not doc_ids:
        logger.warning("向量召回: kb=%s 下无已索引文档", kb_id)
        return []

    vectors = await embed_texts([query_text], text_type="query")
    query_vec = vectors[0]

    client = get_qdrant()
    qfilter = Filter(
        must=[FieldCondition(key="doc_id", match=MatchAny(any=doc_ids))]
    )

    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vec,
        query_filter=qfilter,
        limit=limit,
        with_payload=True,
    ).points

    results = []
    for h in hits:
        p = h.payload or {}
        results.append(RetrievedChunk(
            child_chunk_id=p.get("child_chunk_id", ""),
            parent_chunk_id=p.get("parent_chunk_id", ""),
            doc_id=p.get("doc_id", ""),
            section_id=p.get("section_id", ""),
            chunk_type=p.get("chunk_type", "paragraph"),
            retrieval_text=p.get("retrieval_text", ""),
            embedding_text=p.get("embedding_text", ""),
            header_path=p.get("header_path", []),
            page_span_start=p.get("page_span_start", 0),
            page_span_end=p.get("page_span_end", 0),
            bbox_norm1000=_to_bbox_list(p.get("bbox_norm1000")),
            bbox_page=_to_bbox_list(p.get("bbox_page")),
            anchor_origin_pdf_path=str(p.get("anchor_origin_pdf_path") or ""),
            qdrant_point_id=str(h.id),
            score=float(h.score),
            source="vector",
        ))

    logger.info("向量召回: %d 条 (kb=%s)", len(results), kb_id)
    return results


# ─────────────────────────────────────────────────────────────
# 关键词召回（FTS5）
# ─────────────────────────────────────────────────────────────

def _build_fts_query(text: str) -> str:
    """将用户查询转为 FTS5 安全的 MATCH 字符串。"""
    # 去除 FTS5 特殊字符
    cleaned = re.sub(r'["""()^:*\-]', " ", text)
    tokens = [t for t in cleaned.split() if len(t) >= 1][:_FTS_MAX_TOKENS]
    if not tokens:
        return '""'
    # 每个 token 加引号，隐式 AND
    return " ".join(f'"{t}"' for t in tokens)


async def keyword_search(
    query_text: str,
    kb_id: str,
    limit: int = 20,
) -> list[RetrievedChunk]:
    """
    FTS5 关键词召回（BM25 排序）。

    Returns:
        RetrievedChunk 列表，按 BM25 分数降序
    """
    doc_ids = await _get_kb_doc_ids(kb_id)
    if not doc_ids:
        return []

    fts_query = _build_fts_query(query_text)
    placeholders = ",".join("?" * len(doc_ids))

    sql = f"""
        SELECT c.child_chunk_id, c.parent_chunk_id, c.doc_id, c.section_id,
               c.chunk_type, c.retrieval_text, c.embedding_text, c.header_path,
             c.page_span_start, c.page_span_end,
             c.bbox_norm1000, c.bbox_page, c.anchor_origin_pdf_path,
             c.qdrant_point_id,
               bm25(child_chunks_fts) AS bm25_score
        FROM child_chunks_fts
        JOIN child_chunks c ON c.rowid = child_chunks_fts.rowid
        WHERE child_chunks_fts MATCH ? AND c.doc_id IN ({placeholders})
        ORDER BY bm25(child_chunks_fts)
        LIMIT ?
    """

    db = await get_db()
    try:
        cur = await db.execute(sql, [fts_query] + doc_ids + [limit])
        rows = await cur.fetchall()
    except Exception as exc:
        logger.warning("FTS5 查询失败 query=%r: %s", fts_query, exc)
        return []
    finally:
        await db.close()

    results = []
    for r in rows:
        r = dict(r)
        hp = r.get("header_path", "[]")
        try:
            header_path = json.loads(hp) if isinstance(hp, str) else hp
        except Exception:
            header_path = []

        bm25_raw = float(r.get("bm25_score") or 0.0)
        # SQLite bm25() 返回负数，绝对值越大越相关
        score = abs(bm25_raw)

        results.append(RetrievedChunk(
            child_chunk_id=r["child_chunk_id"],
            parent_chunk_id=r["parent_chunk_id"],
            doc_id=r["doc_id"],
            section_id=r["section_id"],
            chunk_type=r["chunk_type"],
            retrieval_text=r.get("retrieval_text", ""),
            embedding_text=r.get("embedding_text", ""),
            header_path=header_path,
            page_span_start=r.get("page_span_start", 0),
            page_span_end=r.get("page_span_end", 0),
            bbox_norm1000=_to_bbox_list(r.get("bbox_norm1000")),
            bbox_page=_to_bbox_list(r.get("bbox_page")),
            anchor_origin_pdf_path=str(r.get("anchor_origin_pdf_path") or ""),
            qdrant_point_id=r.get("qdrant_point_id", ""),
            score=score,
            source="keyword",
        ))

    logger.info("关键词召回: %d 条 (kb=%s)", len(results), kb_id)
    return results


# ─────────────────────────────────────────────────────────────
# RRF 融合
# ─────────────────────────────────────────────────────────────

def rrf_merge(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = _RRF_K,
) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion。

    Args:
        ranked_lists: 每个子列表是 [(chunk_id, score), ...] 已按相关性降序
        k: 平滑常数（默认 60）

    Returns:
        [(chunk_id, rrf_score), ...] 降序
    """
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank, (chunk_id, _) in enumerate(ranked_list):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ─────────────────────────────────────────────────────────────
# 混合检索主入口
# ─────────────────────────────────────────────────────────────

async def hybrid_search(
    query_text: str,
    kb_id: str,
    vector_limit: int = 20,
    keyword_limit: int = 20,
    top_k: int = 15,
) -> list[RetrievedChunk]:
    """
    混合检索主入口：并行双路召回 → RRF → top_k。

    Returns:
        融合后 top_k 个 RetrievedChunk，score 已替换为 RRF 分数
    """
    vec_results, kw_results = await asyncio.gather(
        vector_search(query_text, kb_id, limit=vector_limit),
        keyword_search(query_text, kb_id, limit=keyword_limit),
    )

    # 建立 chunk_id → chunk 映射（向量结果优先保留完整 payload）
    chunk_map: dict[str, RetrievedChunk] = {}
    for c in vec_results:
        chunk_map[c.child_chunk_id] = c
    for c in kw_results:
        if c.child_chunk_id not in chunk_map:
            chunk_map[c.child_chunk_id] = c

    # 两路列表 → RRF
    vec_ranked = [(c.child_chunk_id, c.score) for c in vec_results]
    kw_ranked = [(c.child_chunk_id, c.score) for c in kw_results]
    merged = rrf_merge([vec_ranked, kw_ranked])

    results = []
    for chunk_id, rrf_score in merged[:top_k]:
        c = chunk_map.get(chunk_id)
        if c:
            c.score = rrf_score
            c.source = "hybrid"
            results.append(c)

    logger.info(
        "混合召回: vec=%d kw=%d → 融合 %d 条 (kb=%s)",
        len(vec_results), len(kw_results), len(results), kb_id,
    )
    return results


# ─────────────────────────────────────────────────────────────
# Parent Chunk 补全
# ─────────────────────────────────────────────────────────────

async def fetch_parent_chunks(
    parent_chunk_ids: list[str],
) -> dict[str, dict]:
    """
    批量从 SQLite 获取 parent_chunks 记录。

    Returns:
        {parent_chunk_id: {title, header_path, text_preview, page_span_start, page_span_end}}
    """
    if not parent_chunk_ids:
        return {}

    placeholders = ",".join("?" * len(parent_chunk_ids))
    db = await get_db()
    try:
        cur = await db.execute(
            f"""SELECT parent_chunk_id, title, header_path,
                       text_preview, page_span_start, page_span_end, doc_id
                FROM parent_chunks WHERE parent_chunk_id IN ({placeholders})""",
            parent_chunk_ids,
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    result = {}
    for r in rows:
        r = dict(r)
        try:
            r["header_path"] = json.loads(r.get("header_path", "[]"))
        except Exception:
            r["header_path"] = []
        result[r["parent_chunk_id"]] = r
    return result


def _to_bbox_list(value: object) -> list[list[float]]:
    """兼容 Qdrant payload / SQLite JSON 字段，统一转为 bbox 列表。"""
    if not value:
        return []

    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return []

    if not isinstance(parsed, list):
        return []

    boxes: list[list[float]] = []
    for item in parsed:
        if isinstance(item, list) and len(item) >= 4:
            try:
                boxes.append([float(item[0]), float(item[1]), float(item[2]), float(item[3])])
            except Exception:
                continue
    return boxes
