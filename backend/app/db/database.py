"""
SQLite 数据库初始化与连接管理

职责：
- 知识库空间管理
- 文档记录
- 任务状态
- 文件路径
- Parent/Child 映射
- 资产索引
- FTS5 全文检索（关键词/BM25）
"""

from __future__ import annotations

import aiosqlite
from loguru import logger

from app.config import settings

# ── DDL ───────────────────────────────────────────────────

_DDL = """
-- ═══════════════ 知识库空间 ═══════════════
CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id           TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    file_count      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active'
);

-- ═══════════════ 文档记录 ═══════════════
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,
    kb_id           TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    filename        TEXT NOT NULL,
    relative_path   TEXT DEFAULT '',                -- 逻辑目录路径（用于文件夹上传展示）
    source_format   TEXT NOT NULL,                  -- pdf/docx/pptx/jpg/png...
    file_size       INTEGER DEFAULT 0,
    upload_path     TEXT DEFAULT '',                 -- 原始上传路径
    mineru_zip_path TEXT DEFAULT '',                 -- MinerU 返回 zip 路径
    origin_pdf_path TEXT DEFAULT '',                 -- *_origin.pdf 路径
    ir_path         TEXT DEFAULT '',                 -- document_ir.json 路径
    ir_enriched_path TEXT DEFAULT '',                -- document_ir_enriched.json 路径
    parent_chunks_path TEXT DEFAULT '',              -- parent_chunks.jsonl 路径
    child_chunks_path  TEXT DEFAULT '',              -- child_chunks.jsonl 路径
    page_count      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'uploaded',         -- uploaded/parsing/parsed/failed
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 异步任务 ═══════════════
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
    task_type       TEXT NOT NULL,                   -- parse/normalize/chunk/embed/enrich
    status          TEXT NOT NULL DEFAULT 'pending', -- pending/running/done/failed
    progress        REAL DEFAULT 0.0,                -- 0.0 ~ 1.0
    error_msg       TEXT DEFAULT '',
    mineru_task_id  TEXT DEFAULT '',                  -- MinerU 远程任务 ID
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ Parent Chunk 索引 ═══════════════
CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
    section_id      TEXT NOT NULL,
    header_path     TEXT DEFAULT '[]',               -- JSON array
    title           TEXT DEFAULT '',
    page_span_start INTEGER DEFAULT 0,
    page_span_end   INTEGER DEFAULT 0,
    block_ids       TEXT DEFAULT '[]',               -- JSON array
    text_preview    TEXT DEFAULT ''                   -- 前 200 字供预览
);

-- ═══════════════ Child Chunk 索引 ═══════════════
CREATE TABLE IF NOT EXISTS child_chunks (
    child_chunk_id  TEXT PRIMARY KEY,
    parent_chunk_id TEXT NOT NULL REFERENCES parent_chunks(parent_chunk_id),
    doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
    section_id      TEXT NOT NULL,
    chunk_type      TEXT NOT NULL,
    header_path     TEXT DEFAULT '[]',
    embedding_text  TEXT DEFAULT '',
    retrieval_text  TEXT DEFAULT '',
    page_span_start INTEGER DEFAULT 0,
    page_span_end   INTEGER DEFAULT 0,
    bbox_norm1000   TEXT DEFAULT '[]',              -- JSON: [[x0,y0,x1,y1], ...]
    bbox_page       TEXT DEFAULT '[]',              -- JSON: [[x0,y0,x1,y1], ...]
    anchor_origin_pdf_path TEXT DEFAULT '',
    qdrant_point_id TEXT DEFAULT ''                   -- Qdrant 点 ID
);

-- ═══════════════ 资产索引 ═══════════════
CREATE TABLE IF NOT EXISTS assets (
    asset_id        TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
    asset_type      TEXT NOT NULL,                   -- image/table_image/equation_image
    path            TEXT NOT NULL,
    usage           TEXT DEFAULT 'primary',
    mime            TEXT DEFAULT '',
    block_id        TEXT DEFAULT ''
);

-- ═══════════════ FTS5 全文索引 ═══════════════
CREATE VIRTUAL TABLE IF NOT EXISTS child_chunks_fts USING fts5(
    child_chunk_id,
    doc_id,
    embedding_text,
    content=child_chunks,
    content_rowid=rowid,
    tokenize='unicode61'
);

-- 触发器：child_chunks 插入时自动更新 FTS
CREATE TRIGGER IF NOT EXISTS child_chunks_ai AFTER INSERT ON child_chunks BEGIN
    INSERT INTO child_chunks_fts(rowid, child_chunk_id, doc_id, embedding_text)
    VALUES (new.rowid, new.child_chunk_id, new.doc_id, new.embedding_text);
END;

-- 触发器：child_chunks 删除时自动更新 FTS
CREATE TRIGGER IF NOT EXISTS child_chunks_ad AFTER DELETE ON child_chunks BEGIN
    INSERT INTO child_chunks_fts(child_chunks_fts, rowid, child_chunk_id, doc_id, embedding_text)
    VALUES ('delete', old.rowid, old.child_chunk_id, old.doc_id, old.embedding_text);
END;

-- ═══════════════ 索引 ═══════════════
CREATE INDEX IF NOT EXISTS idx_documents_kb ON documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_tasks_doc ON tasks(doc_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_doc ON parent_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_doc ON child_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_parent ON child_chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_assets_doc ON assets(doc_id);
"""


async def get_db() -> aiosqlite.Connection:
    """获取一个 SQLite 异步连接"""
    settings.ensure_dirs()
    db = await aiosqlite.connect(str(settings.sqlite_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """初始化数据库 — 创建表和索引，同时做懒迁移"""
    db = await get_db()
    try:
        await db.executescript(_DDL)
        # 懒迁移：为已存在的旧数据库添加新列（ADD COLUMN 若列已存在会报错，忽略即可）
        for sql in [
            "ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'uploaded'",
            "ALTER TABLE documents ADD COLUMN warnings TEXT DEFAULT ''",
            "ALTER TABLE documents ADD COLUMN relative_path TEXT DEFAULT ''",
            "ALTER TABLE child_chunks ADD COLUMN bbox_norm1000 TEXT DEFAULT '[]'",
            "ALTER TABLE child_chunks ADD COLUMN bbox_page TEXT DEFAULT '[]'",
            "ALTER TABLE child_chunks ADD COLUMN anchor_origin_pdf_path TEXT DEFAULT ''",
        ]:
            try:
                await db.execute(sql)
            except Exception:
                pass  # 列已存在，忽略
        await db.commit()
        logger.info("SQLite 数据库初始化完成: {}", settings.sqlite_path)
    finally:
        await db.close()
