"""
Text Index Service — 把纯文本 / Markdown 文档（课堂讲义、笔记）切片 → 嵌入 → 入库，
让它们与 PDF/PPT/Word 共用同一套混合检索（向量 + FTS5）。

设计要点：
- **录音转写 .txt（folder_category='recording'）永不索引**——仅作模块七生成讲义的素材，
  原始转写噪声大，作为问答上下文质量差。
- 生成的「课堂要点.md」（folder_category='review_note'）保存后自动索引；
  其他非录音文本笔记可经端点手动索引。
- 切片复用 child_chunker 的句窗逻辑；Markdown 按标题层级切 Parent，标题路径作为 header_path。
- 文本文档无 PDF / bbox，citation 仅含标题路径，前端隐藏「查看原文」。
- 幂等：重索引前先清空该 doc 的旧 Qdrant 点与 SQLite 块。
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.chunkers.child_chunker import _SENT_SPLIT, _build_windows
from app.config import settings
from app.db.database import get_db
from app.models.models_chunk import ChildChunk, ChildChunkMetadata, ParentChunk
from app.services import embedding_service, index_service

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def is_indexable_text(folder_category: str | None, source_format: str | None) -> bool:
    """录音转写 .txt 不可索引；其余 txt/md 文本可索引。"""
    if source_format not in ("txt", "md"):
        return False
    if folder_category == "recording" and source_format == "txt":
        return False
    return True


def _split_markdown_sections(md: str) -> list[tuple[list[str], str]]:
    """
    按 Markdown 标题切分为 (header_path, body_text)。维护标题栈，
    每段 body 是该标题下、下一个标题前的正文；首个标题前的内容归到 header_path=[]。
    """
    sections: list[tuple[list[str], str]] = []
    header_stack: list[tuple[int, str]] = []
    current_path: list[str] = []
    current_body: list[str] = []

    def flush() -> None:
        body = "\n".join(current_body).strip()
        if body:
            sections.append((list(current_path), body))

    for line in md.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            current_body.clear()
            level = len(m.group(1))
            title = m.group(2).strip()
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            header_stack.append((level, title))
            current_path = [t for _, t in header_stack]
        else:
            current_body.append(line)
    flush()
    return sections


_PARA_SPLIT = re.compile(r"\n\s*\n")  # 空行分段


def _segment_body(body: str) -> list[str]:
    """
    把一段正文切成"切片单元"：先按空行分段（保留 Markdown 段落/列表块边界），
    段内再按句末标点切句。比纯句切更贴合讲义/笔记结构，避免无标点长行被当成超大单句。
    """
    segs: list[str] = []
    for para in _PARA_SPLIT.split(body):
        para = para.strip()
        if not para:
            continue
        parts = [s for s in _SENT_SPLIT.split(para) if s.strip()]
        segs.extend(parts if parts else [para])
    return segs or [body.strip()]


def _build_chunks_for_section(
    doc_id: str,
    sec_idx: int,
    header_path: list[str],
    body: str,
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> tuple[ParentChunk, list[ChildChunk]]:
    section_id = f"sec-{doc_id[:8]}-{sec_idx}"
    parent_id = f"pc-{uuid.uuid4().hex[:12]}"
    parent = ParentChunk(
        parent_chunk_id=parent_id,
        doc_id=doc_id,
        section_id=section_id,
        header_path=header_path,
        title=header_path[-1] if header_path else "",
        page_span=[0, 0],
        block_ids=[],
        text_for_generation=body,
    )

    header_prefix = " > ".join(header_path) if header_path else ""
    if len(body) <= max_chars:
        windows = [body]
    else:
        windows = _build_windows(_segment_body(body), max_chars, min_chars, overlap_chars)

    total = len(windows)
    children: list[ChildChunk] = []
    for w_idx, w in enumerate(windows):
        emb = f"{header_prefix}\n{w}" if header_prefix else w
        children.append(ChildChunk(
            child_chunk_id=f"cc-{uuid.uuid4().hex[:12]}",
            parent_chunk_id=parent_id,
            doc_id=doc_id,
            section_id=section_id,
            header_path=list(header_path),
            chunk_type="paragraph",
            page_span=[0, 0],
            source_block_ids=[],
            bbox_norm1000=[],
            bbox_page=[],
            anchor_origin_pdf_path="",
            embedding_text=emb,
            retrieval_text=w,
            assets=[],
            metadata=ChildChunkMetadata(
                is_atomic=False,
                is_atomic_fragment=(total > 1),
                fragment_index=w_idx if total > 1 else None,
                fragment_total=total if total > 1 else None,
            ),
        ))
    return parent, children


async def _clear_doc_chunks(doc_id: str) -> None:
    """清空该文档已有的 Qdrant 点与 SQLite parent/child 块（幂等重索引）。"""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    from app.db.qdrant_client import get_qdrant

    try:
        client = get_qdrant()
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
            ),
        )
    except Exception:
        logger.warning("清理 Qdrant 旧点失败 doc=%s（可能本就为空）", doc_id, exc_info=True)

    db = await get_db()
    try:
        await db.execute("DELETE FROM child_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM parent_chunks WHERE doc_id=?", (doc_id,))
        await db.commit()
    finally:
        await db.close()


async def _set_doc_status(doc_id: str, status: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE documents SET status=?, updated_at=? WHERE doc_id=?",
            (status, datetime.now(timezone.utc).isoformat(), doc_id),
        )
        await db.commit()
    finally:
        await db.close()


async def index_text_document(
    doc_id: str,
    file_path: str,
    *,
    source_format: str,
) -> int:
    """
    切片 → 嵌入 → 入库一个文本文档。返回 child chunk 数。
    调用方需保证该文档可索引（见 is_indexable_text）。
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"文本文件不存在: {file_path}")
    text = p.read_text(encoding="utf-8-sig", errors="replace")

    if source_format == "md":
        sections = _split_markdown_sections(text)
    else:
        sections = [([], text.strip())]
    if not sections:
        sections = [([], text.strip())]

    max_chars = settings.child_chunk_max_tokens * 2
    min_chars = settings.child_chunk_min_tokens * 2
    overlap_chars = int(max_chars * settings.child_chunk_overlap_ratio)

    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    for sec_idx, (header_path, body) in enumerate(sections):
        if not body.strip():
            continue
        parent, sec_children = _build_chunks_for_section(
            doc_id, sec_idx, header_path, body,
            max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars,
        )
        if not sec_children:
            continue
        parents.append(parent)
        children.extend(sec_children)

    await _clear_doc_chunks(doc_id)

    if not children:
        await _set_doc_status(doc_id, "indexed")
        logger.info("text index: doc=%s 无可索引内容", doc_id)
        return 0

    vectors = await embedding_service.embed_texts(
        [c.embedding_text for c in children], text_type="document"
    )
    await index_service.index_chunks(parents, children, vectors, [], doc_id)
    await _set_doc_status(doc_id, "indexed")
    logger.info(
        "text index done: doc=%s, %d parents, %d children", doc_id, len(parents), len(children)
    )
    return len(children)


async def index_text_document_bg(doc_id: str, file_path: str, source_format: str) -> None:
    """后台任务封装：失败时把文档状态置为 failed，不抛出。"""
    try:
        await index_text_document(doc_id, file_path, source_format=source_format)
    except Exception:
        logger.exception("文本索引失败 doc=%s", doc_id)
        await _set_doc_status(doc_id, "failed")
