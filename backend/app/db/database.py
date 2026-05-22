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
    kb_type         TEXT DEFAULT 'general',           -- general（通用）/ course（课程）
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    file_count      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    bound_folder_path TEXT DEFAULT ''               -- 绑定的本地文件夹路径，空字符串表示未绑定
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
    status          TEXT DEFAULT 'uploaded',         -- uploaded/parsing/indexed/needs_review/failed/text_only/missing
    warnings        TEXT DEFAULT '',                 -- 解析警告信息（MinerU 异常字段等）
    bound_file_path TEXT DEFAULT '',                 -- 文件夹绑定模式下的真实文件绝对路径
    folder_category TEXT DEFAULT '',                 -- 目录分类：recording/slides/homework/notice/review_note/''
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 异步任务 ═══════════════
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
    task_type       TEXT NOT NULL,                   -- parse/normalize/chunk/embed/enrich
    status          TEXT NOT NULL DEFAULT 'created', -- created/running/done/failed
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
    asset_type      TEXT NOT NULL,                   -- image/chart_image/table_image/equation_image
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

-- ═══════════════ 场景层：复习笔记（模块七）═══════════════
-- 课后复盘生成的结构化笔记，写回知识库，供后续检索与备考复用
CREATE TABLE IF NOT EXISTS review_notes (
    note_id         TEXT PRIMARY KEY,
    kb_id           TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    title           TEXT DEFAULT '',                 -- 笔记标题（通常是"第N章复习笔记"）
    content         TEXT DEFAULT '',                 -- Markdown 格式笔记正文
    source_doc_ids  TEXT DEFAULT '[]',               -- JSON array，关联的原始文档 ID
    conversation_id TEXT DEFAULT '',                 -- 关联的对话 ID（供溯源）
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 场景层：题库（模块八）═══════════════
-- 从练习材料中 AI 结构化提取的题目
CREATE TABLE IF NOT EXISTS exam_questions (
    question_id     TEXT PRIMARY KEY,
    kb_id           TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    doc_id          TEXT DEFAULT '',                 -- 来源文档 ID
    question_type   TEXT DEFAULT 'unknown',          -- choice/fill/short_answer/essay/calculation
    difficulty      TEXT DEFAULT 'medium',           -- easy/medium/hard
    stem            TEXT DEFAULT '',                 -- 题干
    options         TEXT DEFAULT '{}',               -- JSON object {A:..., B:..., C:..., D:...}
    answer          TEXT DEFAULT '',                 -- 标准答案
    explanation     TEXT DEFAULT '',                 -- 解析
    knowledge_tags  TEXT DEFAULT '[]',               -- JSON array，知识点标签
    page_ref        INTEGER DEFAULT 0,               -- 来源页码
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 场景层：试卷记录（模块八）═══════════════
-- AI 智能组卷的结果记录
CREATE TABLE IF NOT EXISTS exam_papers (
    paper_id        TEXT PRIMARY KEY,
    kb_id           TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    title           TEXT DEFAULT '模拟试卷',
    question_ids    TEXT DEFAULT '[]',               -- JSON array，题目 ID 有序列表
    params          TEXT DEFAULT '{}',               -- JSON：出题参数（题型分布/难度/题量等）
    content_md      TEXT DEFAULT '',                 -- 生成的试卷 Markdown（无答案版）
    answer_key_md   TEXT DEFAULT '',                 -- 答案与解析 Markdown
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 场景层：答卷批改记录（模块八）═══════════════
CREATE TABLE IF NOT EXISTS exam_submissions (
    submission_id   TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES exam_papers(paper_id),
    kb_id           TEXT NOT NULL,
    image_path      TEXT DEFAULT '',                 -- 答卷图片本地路径
    ocr_text        TEXT DEFAULT '',                 -- OCR 识别出的文本
    score           REAL DEFAULT 0.0,                -- 总分
    feedback_md     TEXT DEFAULT '',                 -- AI 逐题点评与知识漏洞分析 Markdown
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 场景层：课程信息卡片（模块九）═══════════════
-- 从碎片通知中 AI 提取的结构化课程信息
CREATE TABLE IF NOT EXISTS course_info_cards (
    card_id         TEXT PRIMARY KEY,
    kb_id           TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    course_name     TEXT DEFAULT '',
    instructor      TEXT DEFAULT '',                 -- 任课老师
    contact         TEXT DEFAULT '',                 -- 联系方式/答疑时间
    assessment      TEXT DEFAULT '{}',               -- JSON：考核方式{exam_ratio, hw_ratio, attendance_ratio}
    deadlines       TEXT DEFAULT '[]',               -- JSON array：[{name, date, description}, ...]
    important_notes TEXT DEFAULT '',                 -- 重要通知（Markdown）
    source_doc_ids  TEXT DEFAULT '[]',               -- JSON array，提取来源文档
    deadlines_normalized TEXT DEFAULT '[]',          -- 规范化截止日列表（含days_left），便于前7天过滤
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 多轮对话：会话（v1.2.0）═══════════════
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id        TEXT PRIMARY KEY,
    kb_id                  TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    scenario               TEXT NOT NULL,           -- 'lecture_review' | 'course_info' | 'general'
    title                  TEXT DEFAULT '',
    parent_conversation_id TEXT DEFAULT '',         -- fork 时记录父对话 id
    fork_from_message_id   TEXT DEFAULT '',         -- fork 自哪条消息
    metadata               TEXT DEFAULT '{}',       -- JSON：场景相关元数据
    enable_thinking        INTEGER DEFAULT 0,       -- 0/1：本对话是否开启思维链
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 多轮对话：消息（v1.2.0）═══════════════
CREATE TABLE IF NOT EXISTS messages (
    message_id        TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL REFERENCES conversations(conversation_id),
    role              TEXT NOT NULL,                -- 'system' | 'user' | 'assistant'
    content           TEXT DEFAULT '',
    thinking          TEXT DEFAULT '',              -- 思维链文本（仅 assistant 且开 thinking 时）
    sequence_num      INTEGER NOT NULL,             -- 在 conversation 内的顺序号（从 0 开始）
    citations         TEXT DEFAULT '[]',            -- JSON：本轮引用的 chunk，仅 course_info/general
    metadata          TEXT DEFAULT '{}',            -- JSON：role 特定元数据，如 section_num
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════ 索引 ═══════════════
CREATE INDEX IF NOT EXISTS idx_documents_kb ON documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_tasks_doc ON tasks(doc_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_doc ON parent_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_doc ON child_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_parent ON child_chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_assets_doc ON assets(doc_id);
CREATE INDEX IF NOT EXISTS idx_review_notes_kb ON review_notes(kb_id);
CREATE INDEX IF NOT EXISTS idx_exam_questions_kb ON exam_questions(kb_id);
CREATE INDEX IF NOT EXISTS idx_exam_papers_kb ON exam_papers(kb_id);
CREATE INDEX IF NOT EXISTS idx_exam_submissions_paper ON exam_submissions(paper_id);
CREATE INDEX IF NOT EXISTS idx_course_info_cards_kb ON course_info_cards(kb_id);
CREATE INDEX IF NOT EXISTS idx_conversations_kb ON conversations(kb_id);
CREATE INDEX IF NOT EXISTS idx_conversations_scenario ON conversations(kb_id, scenario);
CREATE INDEX IF NOT EXISTS idx_conversations_parent ON conversations(parent_conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, sequence_num);
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
            "ALTER TABLE knowledge_bases ADD COLUMN kb_type TEXT DEFAULT 'general'",
            # v1.2.0 新增列
            "ALTER TABLE knowledge_bases ADD COLUMN bound_folder_path TEXT DEFAULT ''",
            "ALTER TABLE documents ADD COLUMN bound_file_path TEXT DEFAULT ''",
            "ALTER TABLE documents ADD COLUMN folder_category TEXT DEFAULT ''",
            "ALTER TABLE course_info_cards ADD COLUMN deadlines_normalized TEXT DEFAULT '[]'",
        ]:
            try:
                await db.execute(sql)
            except Exception:
                pass  # 列已存在，忽略
        await db.commit()
        logger.info("SQLite 数据库初始化完成: {}", settings.sqlite_path)
    finally:
        await db.close()
