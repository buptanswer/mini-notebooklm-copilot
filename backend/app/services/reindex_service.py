"""Reindex Service —— 不重新解析 MinerU，仅按新「父块粒度」重切片 + 重嵌入 + 重入库。

用途：文档级「父块粒度」可调（几级标题=1父块，默认 L1）。用户改某文档粒度后，复用已持久化的
enriched IR（含 LLM 重建层级 + VLM 图/表描述），重新走 切片→向量化→入库，**无需再调 MinerU / VLM**
（省钱省时；只重嵌入，成本极低）。

复现 pipeline 的关键步骤：把图/表块的 `text` 回流为 `enrichment.*.embedding_text`（caption+VLM描述/摘要），
保证重切片产出的子块 retrieval_text 与初次解析一致（图按描述检索、原位）。

代价：父块边界变化会使该文档已建的「自定义索引」失效——index_chunks._purge_doc 会一并清掉
（parent_extra_indexes + 物化虚拟子块），需用户重建。这是粒度变更的固有代价（前端会提示）。
"""

from __future__ import annotations

import json
import logging
from typing import cast

from app.chunkers.child_chunker import build_child_chunks
from app.chunkers.parent_chunker import build_parent_chunks
from app.config import settings
from app.db.database import get_db
from app.models.models_ir import DocumentIREnriched, IRBlock
from app.services.embedding_service import embed_texts
from app.services.index_service import index_chunks
from app.writers.chunk_writer import write_chunks

logger = logging.getLogger(__name__)


class ReindexError(Exception):
    """重切片/重索引失败（IR 缺失、状态不符、粒度非法等）。"""


async def _doc_row(doc_id: str) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, status, COALESCE(ir_enriched_path,'') AS e, "
            "COALESCE(ir_path,'') AS b, COALESCE(parent_heading_level,0) AS lvl "
            "FROM documents WHERE doc_id=?",
            (doc_id,),
        )
        row = await cur.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


async def get_effective_parent_level(doc_id: str) -> int:
    """文档生效的父块粒度：per-doc 设置（>0）优先，否则全局默认。"""
    row = await _doc_row(doc_id)
    lvl = int(row["lvl"]) if row else 0
    return lvl if lvl and lvl > 0 else settings.parent_chunk_heading_level


def _reapply_reflow(blocks: list) -> None:
    """复现 pipeline 的图/表 text 回流：block.text = enrichment.*.embedding_text。"""
    for b in blocks:
        enr = getattr(b, "enrichment", None)
        if not enr or enr.enrichment_status != "ok":
            continue
        if enr.image and enr.image.embedding_text:
            b.text = enr.image.embedding_text
        elif enr.table and enr.table.embedding_text:
            b.text = enr.table.embedding_text


async def rechunk_and_reindex(doc_id: str, parent_level: int) -> dict:
    """按新粒度从 enriched IR 重切片 + 重嵌入 + 重入库；返回计数。"""
    if parent_level < 1:
        raise ReindexError("父块粒度必须 ≥ 1（几级标题=1 父块）")
    row = await _doc_row(doc_id)
    if not row:
        raise ReindexError("文档不存在")
    if row["status"] not in ("indexed", "needs_review"):
        raise ReindexError(f"文档状态为 {row['status']}，需先完成解析索引才能重切片")
    ir_path = row["e"] or row["b"]
    if not ir_path:
        raise ReindexError("找不到该文档的 IR 文件，无法重切片（请改用重新解析）")

    try:
        with open(ir_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ir = DocumentIREnriched.model_validate(data)
    except Exception as exc:
        raise ReindexError(f"读取/解析 IR 失败：{exc}") from exc

    blocks = list(ir.blocks)
    _reapply_reflow(blocks)
    blocks_base = cast("list[IRBlock]", blocks)

    parents = build_parent_chunks(ir.sections, blocks_base, ir.pages, doc_id, parent_level=parent_level)
    children = build_child_chunks(parents, blocks_base, ir.pages, doc_id)
    if not children:
        raise ReindexError("重切片后无子块（粒度过粗或文档无正文？）")

    vectors = await embed_texts([c.embedding_text for c in children], text_type="document")
    await index_chunks(parents, children, vectors, blocks_base, doc_id)  # 含 _purge_doc 幂等
    ppath, cpath = write_chunks(doc_id, parents, children)

    db = await get_db()
    try:
        await db.execute(
            "UPDATE documents SET parent_chunks_path=?, child_chunks_path=?, "
            "parent_heading_level=?, updated_at=datetime('now') WHERE doc_id=?",
            (str(ppath), str(cpath), parent_level, doc_id),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info("reindex doc=%s level=%d → %d 父块 / %d 子块", doc_id, parent_level, len(parents), len(children))
    return {
        "doc_id": doc_id,
        "parent_level": parent_level,
        "parents": len(parents),
        "children": len(children),
    }
