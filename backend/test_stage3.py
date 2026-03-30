"""
Stage 3 集成测试

测试内容（使用 Stage 2 已产出的 document_ir.json，不再调用 MinerU）：
  1. 从 document_ir.json 重建 blocks / pages / sections
  2. build_parent_chunks  → 验证数量与字段
  3. build_child_chunks   → 验证数量与字段
  4. embed_texts          → 验证向量维度（1024）
  5. index_chunks         → 验证 Qdrant upsert + SQLite 写入
  6. write_chunks         → 验证 JSONL 文件写出
  7. Qdrant 相似度检索    → 验证向量可命中

运行方式：
  cd backend
    uv run python test_stage3.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_stage3")

# ── 导入 ──────────────────────────────────────────────────────────────────────
from app.config import settings
from app.db.database import init_db, get_db
from app.db.qdrant_client import init_qdrant, get_qdrant
from app.models.models_ir import DocumentIR
from app.chunkers.parent_chunker import build_parent_chunks
from app.chunkers.child_chunker import build_child_chunks
from app.services.embedding_service import embed_texts
from app.services.index_service import index_chunks
from app.writers.chunk_writer import write_chunks

settings.ensure_dirs()

# 使用 sample-pdf 这份 IR（内容最丰富）
SAMPLE_DOC_ID = "test-sample-pdf"
IR_PATH = (
    Path(__file__).parent.parent
    / "data" / "rag_output" / SAMPLE_DOC_ID / "document_ir.json"
)
TEST_KB_ID = "test-kb-stage3"


# ─────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────

def _load_ir(path: Path) -> DocumentIR:
    logger.info("加载 IR: %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return DocumentIR.model_validate(data)


async def _ensure_fixtures(doc_id: str) -> None:
    """确保 SQLite 中存在 KB 和 Document 记录（外键前置）。"""
    db = await get_db()
    try:
        # knowledge_base
        await db.execute(
            "INSERT OR IGNORE INTO knowledge_bases (kb_id, name) VALUES (?, ?)",
            (TEST_KB_ID, "Stage3 Test KB"),
        )
        # document
        await db.execute(
            """INSERT OR IGNORE INTO documents
               (doc_id, kb_id, filename, source_format, status)
               VALUES (?, ?, ?, ?, ?)""",
            (doc_id, TEST_KB_ID, f"{doc_id}.pdf", "pdf", "parsing"),
        )
        await db.commit()
        logger.info("Fixtures 准备完毕: kb=%s, doc=%s", TEST_KB_ID, doc_id)
    finally:
        await db.close()


def _assert(condition: bool, msg: str) -> None:
    if not condition:
        logger.error("FAIL  %s", msg)
        sys.exit(1)
    logger.info("PASS  %s", msg)


# ─────────────────────────────────────────────────────────────
# 主测试
# ─────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("═══════════════════════════════════════════════════")
    logger.info("  Stage 3 集成测试")
    logger.info("═══════════════════════════════════════════════════")

    # ── 前置检查 ──────────────────────────────────────────────
    if not IR_PATH.exists():
        logger.error("IR 文件不存在: %s（请先运行 test_stage2.py）", IR_PATH)
        sys.exit(1)
    if not settings.dashscope_api_key:
        logger.error("ALIBABA_CLOUD_ACCESS_KEY_SECRET 未配置")
        sys.exit(1)
    logger.info("DashScope API key: %s…（前8位）", settings.dashscope_api_key[:8])

    # ── 初始化 ────────────────────────────────────────────────
    logger.info("--- 初始化 SQLite + Qdrant ---")
    await init_db()
    init_qdrant()
    await _ensure_fixtures(SAMPLE_DOC_ID)

    # ── 1. 加载 IR ────────────────────────────────────────────
    logger.info("--- [1] 加载 document_ir.json ---")
    ir = _load_ir(IR_PATH)
    blocks  = ir.blocks
    pages   = ir.pages
    sections = ir.sections
    doc_id  = ir.source.doc_id

    logger.info(
        "IR 加载成功: doc_id=%s, %d 页, %d 块, %d sections",
        doc_id, len(pages), len(blocks), len(sections),
    )
    _assert(len(blocks) > 0, f"blocks 非空（got {len(blocks)}）")
    _assert(len(sections) > 0, f"sections 非空（got {len(sections)}）")

    # ── 2. Parent Chunking ────────────────────────────────────
    logger.info("--- [2] build_parent_chunks ---")
    parent_chunks = build_parent_chunks(sections, blocks, pages, doc_id)
    logger.info("  → %d 个 ParentChunk", len(parent_chunks))

    _assert(len(parent_chunks) > 0, f"parent_chunks 非空（got {len(parent_chunks)}）")
    pc0 = parent_chunks[0]
    _assert(bool(pc0.parent_chunk_id), "parent_chunk_id 非空")
    _assert(pc0.doc_id == doc_id, f"doc_id 一致（got {pc0.doc_id}）")
    _assert(len(pc0.block_ids) >= 0, "block_ids 字段存在")
    logger.info(
        "  示例 parent[0]: title=%r, page_span=%s, text_preview=%r…",
        pc0.title,
        pc0.page_span,
        pc0.text_for_generation[:60],
    )

    # ── 3. Child Chunking ─────────────────────────────────────
    logger.info("--- [3] build_child_chunks ---")
    child_chunks = build_child_chunks(parent_chunks, blocks, pages, doc_id)
    logger.info("  → %d 个 ChildChunk", len(child_chunks))

    _assert(len(child_chunks) > 0, f"child_chunks 非空（got {len(child_chunks)}）")
    cc0 = child_chunks[0]
    _assert(bool(cc0.child_chunk_id), "child_chunk_id 非空")
    _assert(bool(cc0.embedding_text), "embedding_text 非空")
    _assert(bool(cc0.retrieval_text), "retrieval_text 非空")
    logger.info(
        "  示例 child[0]: type=%s, embedding_text=%r…",
        cc0.chunk_type,
        cc0.embedding_text[:80],
    )

    # chunk 比例合理性检查
    ratio = len(child_chunks) / len(parent_chunks)
    logger.info("  child/parent 比例: %.1f（一般应 > 1）", ratio)
    _assert(ratio >= 1.0, f"child >= parent（ratio={ratio:.1f}）")

    # ── 4. Embedding ──────────────────────────────────────────
    logger.info("--- [4] embed_texts（调用 text-embedding-v4）---")
    # 只嵌入前 50 个以节约 API 调用次数（完整测试可去掉切片）
    TEST_LIMIT = min(50, len(child_chunks))
    test_chunks = child_chunks[:TEST_LIMIT]
    embedding_texts = [cc.embedding_text for cc in test_chunks]

    logger.info("  向量化 %d 条 ChildChunk …", len(embedding_texts))
    vectors = await embed_texts(embedding_texts, text_type="document")

    _assert(len(vectors) == len(embedding_texts), "向量数量与输入匹配")
    _assert(len(vectors[0]) == settings.embedding_dim,
            f"向量维度 == {settings.embedding_dim}（got {len(vectors[0])}）")
    logger.info("  → 向量维度: %d，第一条前5维: %s", len(vectors[0]), vectors[0][:5])

    # ── 5. Index（Qdrant + SQLite）────────────────────────────
    logger.info("--- [5] index_chunks ---")
    # 用 test_chunks 及其对应的 parent_chunks（只含涉及到的 parent）
    used_pc_ids = {cc.parent_chunk_id for cc in test_chunks}
    test_parents = [pc for pc in parent_chunks if pc.parent_chunk_id in used_pc_ids]

    await index_chunks(
        parent_chunks=test_parents,
        child_chunks=test_chunks,
        vectors=vectors,
        blocks=blocks,
        doc_id=doc_id,
    )

    # 验证 SQLite
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) FROM parent_chunks WHERE doc_id=?", (doc_id,)
        )
        pc_count = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM child_chunks WHERE doc_id=?", (doc_id,)
        )
        cc_count = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM assets WHERE doc_id=?", (doc_id,)
        )
        asset_count = (await cur.fetchone())[0]
    finally:
        await db.close()

    logger.info(
        "  SQLite: %d parent_chunks, %d child_chunks, %d assets",
        pc_count, cc_count, asset_count,
    )
    _assert(pc_count > 0, f"SQLite parent_chunks 已写入（{pc_count} 行）")
    _assert(cc_count > 0, f"SQLite child_chunks 已写入（{cc_count} 行）")

    # 验证 Qdrant
    client = get_qdrant()
    coll_info = client.get_collection(settings.qdrant_collection)
    qdrant_count = coll_info.points_count
    logger.info("  Qdrant collection=%s, points=%d", settings.qdrant_collection, qdrant_count)
    _assert(qdrant_count > 0, f"Qdrant 已有向量点（{qdrant_count} pts）")

    # ── 6. Write JSONL ────────────────────────────────────────
    logger.info("--- [6] write_chunks ---")
    parent_path, child_path = write_chunks(doc_id, test_parents, test_chunks)

    _assert(parent_path.exists(), f"parent_chunks.jsonl 已写出 ({parent_path})")
    _assert(child_path.exists(), f"child_chunks.jsonl 已写出 ({child_path})")

    # 验证行数
    with open(parent_path, encoding="utf-8") as f:
        parent_lines = sum(1 for _ in f)
    with open(child_path, encoding="utf-8") as f:
        child_lines = sum(1 for _ in f)

    logger.info(
        "  parent_chunks.jsonl: %d 行，child_chunks.jsonl: %d 行",
        parent_lines, child_lines,
    )
    _assert(parent_lines == len(test_parents),
            f"parent JSONL 行数 == {len(test_parents)}（got {parent_lines}）")
    _assert(child_lines == len(test_chunks),
            f"child JSONL 行数 == {len(test_chunks)}（got {child_lines}）")

    # 验证每行是合法 JSON
    with open(child_path, encoding="utf-8") as f:
        first_line = f.readline().strip()
    parsed = json.loads(first_line)
    _assert("child_chunk_id" in parsed, "child JSONL 行含 child_chunk_id")
    _assert("embedding_text" in parsed, "child JSONL 行含 embedding_text")

    # ── 7. Qdrant 向量检索验证 ────────────────────────────────
    logger.info("--- [7] Qdrant 向量检索（query 向量）---")
    query_text = "本文档的主要内容是什么？"
    logger.info("  查询: %r", query_text)
    query_vectors = await embed_texts([query_text], text_type="query")
    query_vec = query_vectors[0]

    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vec,
        limit=3,
    ).points
    _assert(len(hits) > 0, f"Qdrant 检索返回结果（got {len(hits)} hits）")
    logger.info("  Top-%d 检索结果:", len(hits))
    for i, h in enumerate(hits, 1):
        logger.info(
            "    [%d] score=%.4f  chunk_type=%s  text=%.60s…",
            i,
            h.score,
            h.payload.get("chunk_type", "?"),
            h.payload.get("retrieval_text", ""),
        )

    # ── 全部通过 ──────────────────────────────────────────────
    logger.info("")
    logger.info("═══════════════════════════════════════════════════")
    logger.info("  ✓  Stage 3 全部测试通过！")
    logger.info("     parent_chunks : %d 个", len(parent_chunks))
    logger.info("     child_chunks  : %d 个（测试取前 %d 个）", len(child_chunks), TEST_LIMIT)
    logger.info("     Qdrant points : %d", qdrant_count)
    logger.info("     SQLite rows   : %d parent, %d child", pc_count, cc_count)
    logger.info("     JSONL         : %s", parent_path)
    logger.info("                     %s", child_path)
    logger.info("═══════════════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
