"""
Pipeline Service — 完整文档解析流水线（异步后台任务）

流程：
  文件上传（已完成）
    ↓
  [A] 申请预签名上传 URL（MinerU）
    ↓
  [B] PUT 上传文件
    ↓
  [C] 轮询 batch 结果，获取 full_zip_url
    ↓
  [D] 下载 ZIP
    ↓
  [E] 解压 + bundle 识别（bundle_parser）
    ↓
  [F] 归一化：content_list_v2 → IRBlock[] + IRPage[]（normalizer）
    ↓
  [G] DOM 重建：section 树 + header_path（dom_builder）
    ↓
  [H] 脚注关联（footnote_linker）
    ↓
  [I] 读取 layout.json 元数据
    ↓
  [J] 写出 document_ir.json（ir_writer）
    ↓
  [L] 构建 ParentChunk（parent_chunker）
    ↓
  [M] 构建 ChildChunk（child_chunker）
    ↓
  [N] 向量化：text-embedding-v4（embedding_service）
    ↓
  [O] 写入 Qdrant + SQLite（index_service）
    ↓
  [P] 写出 parent_chunks.jsonl + child_chunks.jsonl（chunk_writer）
    ↓
  [K] 更新 documents 表状态 → indexed / needs_review

任务状态写入 SQLite：
  created → running → done / failed

使用方式：
  await run_parse_pipeline(doc_id, kb_id, upload_path, filename, source_format)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.adapters.bundle_parser import extract_zip, parse_bundle_manifest
from app.adapters.dom_builder import build_dom
from app.adapters.footnote_linker import link_footnotes
from app.adapters.normalizer import normalize
from app.chunkers.child_chunker import build_child_chunks
from app.chunkers.parent_chunker import build_parent_chunks
from app.config import settings
from app.db.database import get_db
from app.services.embedding_service import embed_texts
from app.services.index_service import index_chunks
from app.services.mineru_client import (
    download_zip,
    poll_batch_results,
    request_batch_upload_urls,
    upload_file_to_presigned_url,
)
from app.writers.chunk_writer import write_chunks
from app.writers.ir_writer import write_ir

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 任务状态辅助
# ─────────────────────────────────────────────────────────────

async def _create_task(doc_id: str, task_type: str) -> str:
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO tasks (task_id, doc_id, task_type, status, progress, error_msg, created_at, updated_at)
               VALUES (?, ?, ?, 'created', 0.0, '', ?, ?)""",
            (task_id, doc_id, task_type, now, now),
        )
        await db.commit()
    finally:
        await db.close()
    return task_id


async def _update_task(task_id: str, status: str, progress: float, error_msg: str = "") -> None:
    now = datetime.utcnow().isoformat()
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET status=?, progress=?, error_msg=?, updated_at=? WHERE task_id=?",
            (status, progress, error_msg, now, task_id),
        )
        await db.commit()
    finally:
        await db.close()


async def _update_doc_status(
    doc_id: str,
    status: str,
    page_count: int = 0,
    ir_path: str = "",
    parent_chunks_path: str = "",
    child_chunks_path: str = "",
    origin_pdf_path: str = "",
    warnings: str = "",
) -> None:
    now = datetime.utcnow().isoformat()
    db = await get_db()
    try:
        await db.execute(
            """UPDATE documents
               SET status=?, page_count=?, ir_path=?,
                   parent_chunks_path=?, child_chunks_path=?,
                   origin_pdf_path=?, warnings=?, updated_at=?
               WHERE doc_id=?""",
            (status, page_count, ir_path,
             parent_chunks_path, child_chunks_path,
             origin_pdf_path, warnings, now, doc_id),
        )
        await db.commit()
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────
# 主流水线
# ─────────────────────────────────────────────────────────────

async def run_parse_pipeline(
    doc_id: str,
    kb_id: str,
    upload_path: Path,
    filename: str,
    source_format: str,
) -> str:
    """
    启动并执行完整解析流水线。

    Returns:
        task_id（已写入 SQLite）
    """
    task_id = await _create_task(doc_id, "parse")
    logger.info("[pipeline] 开始解析 doc_id=%s file=%s", doc_id, filename)

    try:
        await _update_task(task_id, "running", 0.05)
        await _update_doc_status(doc_id, "parsing")

        # ── [A] 申请预签名上传 URL ─────────────────────────────
        logger.info("[pipeline] [A] 申请预签名 URL")
        file_info = [{"name": filename, "data_id": doc_id}]
        batch_id, file_urls = await request_batch_upload_urls(
            files_info=file_info,
            model_version=settings.mineru_model_version,
        )
        await _update_task(task_id, "running", 0.1)

        # ── [B] PUT 上传文件 ───────────────────────────────────
        logger.info("[pipeline] [B] 上传文件到预签名 URL")
        if not file_urls:
            raise RuntimeError("预签名 URL 列表为空")
        await upload_file_to_presigned_url(file_urls[0], upload_path)
        await _update_task(task_id, "running", 0.2)

        # ── [C] 轮询批量结果 ───────────────────────────────────
        logger.info("[pipeline] [C] 等待 MinerU 解析完成 …")
        results = await poll_batch_results(batch_id)
        await _update_task(task_id, "running", 0.5)

        result = results[0]
        if result.get("state") == "failed":
            raise RuntimeError(f"MinerU 解析失败: {result.get('err_msg', '未知错误')}")

        full_zip_url: str = result["full_zip_url"]
        logger.info("[pipeline] 解析完成，zip_url=%s", full_zip_url[:60])

        # ── [D] 下载 ZIP ──────────────────────────────────────
        logger.info("[pipeline] [D] 下载解析结果 ZIP")
        zip_dir = settings.mineru_zip_dir / doc_id
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"{doc_id}.zip"
        await download_zip(full_zip_url, zip_path)
        await _update_task(task_id, "running", 0.6)

        # ── [E] 解压 + bundle 识别 ────────────────────────────
        logger.info("[pipeline] [E] 解压 + 文件角色识别")
        extract_dir = zip_dir / "extracted"
        zip_root = extract_zip(zip_path, extract_dir)
        manifest = parse_bundle_manifest(zip_root)

        if not manifest.content_list_v2_path:
            raise RuntimeError("content_list_v2.json 未找到，无法继续")

        await _update_task(task_id, "running", 0.65)

        # ── [F] 归一化 ────────────────────────────────────────
        logger.info("[pipeline] [F] 归一化 → IRBlock[]")
        blocks, pages, degraded = normalize(
            content_list_v2_path=manifest.content_list_v2_path,
            layout_path=manifest.layout_path,
            doc_id=doc_id,
            source_filename=filename,
            source_format=source_format,
            images_dir=manifest.images_dir,
        )
        await _update_task(task_id, "running", 0.75)

        # ── [G] DOM 重建 ──────────────────────────────────────
        logger.info("[pipeline] [G] DOM 重建 → sections + header_path")
        blocks, sections = build_dom(blocks)

        # ── [H] 脚注关联 ──────────────────────────────────────
        logger.info("[pipeline] [H] 脚注关联")
        blocks = link_footnotes(blocks, pages)
        await _update_task(task_id, "running", 0.85)

        # ── [I] 读取 layout.json 元数据（backend/version）─────
        mineru_backend: str | None = None
        mineru_version: str | None = None
        if manifest.layout_path:
            mineru_backend, mineru_version = _read_layout_meta(manifest.layout_path)

        # ── [J] 写出 document_ir.json ─────────────────────────
        logger.info("[pipeline] [J] 写出 document_ir.json")
        ir_path = write_ir(
            doc_id=doc_id,
            source_filename=filename,
            source_format=source_format,
            manifest=manifest,
            blocks=blocks,
            pages=pages,
            sections=sections,
            degraded_modes=degraded,
            mineru_backend=mineru_backend,
            mineru_version=mineru_version,
        )
        await _update_task(task_id, "running", 0.95)

        # ── [L] Parent Chunk 构建 ─────────────────────────────
        logger.info("[pipeline] [L] 构建 ParentChunk")
        parent_chunks = build_parent_chunks(sections, blocks, pages, doc_id)
        logger.info("[pipeline] 共 %d 个 ParentChunk", len(parent_chunks))

        # ── [M] Child Chunk 构建 ──────────────────────────────
        logger.info("[pipeline] [M] 构建 ChildChunk")
        child_chunks = build_child_chunks(parent_chunks, blocks, pages, doc_id)
        logger.info("[pipeline] 共 %d 个 ChildChunk", len(child_chunks))
        await _update_task(task_id, "running", 0.97)

        # ── [N] 向量化 ────────────────────────────────────────
        logger.info("[pipeline] [N] text-embedding-v4 向量化")
        embedding_texts = [cc.embedding_text for cc in child_chunks]
        vectors = await embed_texts(embedding_texts, text_type="document")

        # ── [O] 写入 Qdrant + SQLite ──────────────────────────
        logger.info("[pipeline] [O] 写入 Qdrant + SQLite")
        await index_chunks(parent_chunks, child_chunks, vectors, blocks, doc_id)

        # ── [P] 写出 chunk JSONL ──────────────────────────────
        logger.info("[pipeline] [P] 写出 chunk JSONL")
        parent_chunks_path, child_chunks_path = write_chunks(
            doc_id, parent_chunks, child_chunks
        )

        # ── [K] 更新 documents 表 ─────────────────────────────
        # 有任何解析警告 → needs_review，否则 → indexed
        doc_status = "needs_review" if degraded else "indexed"
        warn_str = ""
        if degraded:
            warn_list = sorted(set(degraded))
            warn_str = "\u26a0 MinerU解析警告: " + "; ".join(warn_list)
            logger.warning(
                "[pipeline] doc_id=%s 出现 %d 条解析警告，状态设为 needs_review\n  警告列表: %s",
                doc_id, len(set(degraded)), warn_list,
            )
        # 保存 origin.pdf 路径（前端可用于 PDF 预览）
        origin_pdf = manifest.origin_pdf_path or ""
        await _update_doc_status(
            doc_id, doc_status,
            page_count=len(pages),
            ir_path=str(ir_path),
            parent_chunks_path=str(parent_chunks_path),
            child_chunks_path=str(child_chunks_path),
            origin_pdf_path=origin_pdf,
            warnings=warn_str,
        )

        await _update_task(task_id, "done", 1.0, error_msg=warn_str)

        logger.info(
            "[pipeline] 完成 doc_id=%s, %d 页, %d 块, %d sections → %s",
            doc_id, len(pages), len(blocks), len(sections), ir_path,
        )
        return task_id

    except Exception as exc:
        logger.exception("[pipeline] 解析失败 doc_id=%s: %s", doc_id, exc)
        await _update_task(task_id, "failed", 0.0, error_msg=str(exc))
        await _update_doc_status(doc_id, "failed", ir_path="")
        raise


def _read_layout_meta(layout_path: str) -> tuple[str | None, str | None]:
    """从 layout.json 读取 _backend 与 _version_name"""
    try:
        with open(layout_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("_backend"), data.get("_version_name")
    except Exception:
        return None, None
