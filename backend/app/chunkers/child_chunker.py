"""
Child Chunker — 在 ParentChunk 内生成面向 embedding 的 Child Chunk

切分策略（按块类型）：
  list / code / image / table / equation → 原子块，整体作为一个 Child
  paragraph / title → 滑动窗口切分（按标点句子边界）

Child embedding_text 格式：
  "{header_path_str}\n{text}"

其中 header_path_str = " > ".join(header_path)

窗口参数（来自 settings）：
  child_chunk_max_tokens  默认 250（按字符数估算：1 token ≈ 1.5 汉字 ≈ 1 英文单词）
  child_chunk_min_tokens  默认 150
  child_chunk_overlap_ratio 默认 0.15

字符数估算：max_chars = max_tokens * 2（中英混合文档保守估算）
"""

from __future__ import annotations

import re
import uuid

from app.config import settings
from app.models.models_chunk import ChildChunk, ChildChunkMetadata, ParentChunk
from app.models.models_ir import IRBlock, IRPage


# 原子块类型：不拆分
_ATOMIC_TYPES = frozenset({"list", "code", "image", "table", "equation"})

# 句子分割正则（中英文标点均支持）
_SENT_SPLIT = re.compile(r'(?<=[。！？!?\.…])\s*')


def build_child_chunks(
    parent_chunks: list[ParentChunk],
    blocks: list[IRBlock],
    pages: list[IRPage],
    doc_id: str,
) -> list[ChildChunk]:
    """
    遍历所有 ParentChunk 生成 ChildChunk 列表。
    """
    block_map: dict[str, IRBlock] = {b.block_id: b for b in blocks}
    page_numbers_map: dict[int, list[str]] = {
        p.page_idx: [a.text for a in p.auxiliary.page_numbers if a.text]
        for p in pages
    }

    max_chars = settings.child_chunk_max_tokens * 2
    min_chars = settings.child_chunk_min_tokens * 2
    overlap_chars = int(max_chars * settings.child_chunk_overlap_ratio)

    result: list[ChildChunk] = []

    for parent in parent_chunks:
        header_prefix = " > ".join(parent.header_path) if parent.header_path else ""

        # 按 order_in_doc 排好顺序的块
        parent_blocks = sorted(
            [block_map[bid] for bid in parent.block_ids if bid in block_map],
            key=lambda b: b.order_in_doc,
        )

        for blk in parent_blocks:
            if blk.type == "title":
                # 标题不单列为可检索 child：它已作为 header_path 前缀拼进每个子块的
                # embedding_text，单独成块价值低、还会污染检索结果。
                continue
            if blk.type in _ATOMIC_TYPES:
                # 原子块：整体一个 Child
                children = _make_atomic_child(
                    blk, parent, header_prefix, page_numbers_map
                )
                result.extend(children)
            else:
                # paragraph：滑动窗口切分
                children = _slice_paragraph(
                    blk, parent, header_prefix, page_numbers_map,
                    max_chars, min_chars, overlap_chars,
                )
                result.extend(children)

    return result


# ─────────────────────────────────────────────────────────────
# 原子块
# ─────────────────────────────────────────────────────────────

def _make_atomic_child(
    blk: IRBlock,
    parent: ParentChunk,
    header_prefix: str,
    page_numbers_map: dict[int, list[str]],
) -> list[ChildChunk]:
    """整块作为一个 Child，不切分。"""
    retrieval_text = _build_retrieval_text(blk)
    if not retrieval_text:
        return []

    embedding_text = f"{header_prefix}\n{retrieval_text}" if header_prefix else retrieval_text
    page_nums = page_numbers_map.get(blk.page_idx, [])
    bbox_norm1000, bbox_page, anchor_origin_pdf_path = _extract_bboxes(blk)

    return [ChildChunk(
        child_chunk_id=f"cc-{uuid.uuid4().hex[:12]}",
        parent_chunk_id=parent.parent_chunk_id,
        doc_id=parent.doc_id,
        section_id=parent.section_id,
        header_path=list(parent.header_path),
        chunk_type=blk.type if blk.type in {"list", "code", "image", "table", "equation"} else "paragraph",  # type: ignore
        page_span=[blk.page_idx, blk.page_idx],
        source_block_ids=[blk.block_id],
        bbox_norm1000=bbox_norm1000,
        bbox_page=bbox_page,
        anchor_origin_pdf_path=anchor_origin_pdf_path,
        embedding_text=embedding_text,
        retrieval_text=retrieval_text,
        assets=[a.asset_id for a in blk.assets],
        metadata=ChildChunkMetadata(
            page_numbers=page_nums,
            code_language=blk.metadata.code_language,
            is_atomic=True,
        ),
    )]


# ─────────────────────────────────────────────────────────────
# 滑动窗口切分（paragraph / title）
# ─────────────────────────────────────────────────────────────

def _slice_paragraph(
    blk: IRBlock,
    parent: ParentChunk,
    header_prefix: str,
    page_numbers_map: dict[int, list[str]],
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> list[ChildChunk]:
    """按句子边界做滑动窗口切分。"""
    text = blk.text.strip()
    if not text:
        return []

    page_nums = page_numbers_map.get(blk.page_idx, [])
    bbox_norm1000, bbox_page, anchor_origin_pdf_path = _extract_bboxes(blk)

    # 短文本直接整块
    if len(text) <= max_chars:
        embedding_text = f"{header_prefix}\n{text}" if header_prefix else text
        return [ChildChunk(
            child_chunk_id=f"cc-{uuid.uuid4().hex[:12]}",
            parent_chunk_id=parent.parent_chunk_id,
            doc_id=parent.doc_id,
            section_id=parent.section_id,
            header_path=list(parent.header_path),
            chunk_type="paragraph",
            page_span=[blk.page_idx, blk.page_idx],
            source_block_ids=[blk.block_id],
            bbox_norm1000=bbox_norm1000,
            bbox_page=bbox_page,
            anchor_origin_pdf_path=anchor_origin_pdf_path,
            embedding_text=embedding_text,
            retrieval_text=text,
            assets=[],
            metadata=ChildChunkMetadata(page_numbers=page_nums, is_atomic=False),
        )]

    # 分句
    sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    windows = _build_windows(sentences, max_chars, min_chars, overlap_chars)
    total = len(windows)
    children: list[ChildChunk] = []

    for idx, window_text in enumerate(windows):
        embedding_text = f"{header_prefix}\n{window_text}" if header_prefix else window_text
        children.append(ChildChunk(
            child_chunk_id=f"cc-{uuid.uuid4().hex[:12]}",
            parent_chunk_id=parent.parent_chunk_id,
            doc_id=parent.doc_id,
            section_id=parent.section_id,
            header_path=list(parent.header_path),
            chunk_type="paragraph",
            page_span=[blk.page_idx, blk.page_idx],
            source_block_ids=[blk.block_id],
            bbox_norm1000=bbox_norm1000,
            bbox_page=bbox_page,
            anchor_origin_pdf_path=anchor_origin_pdf_path,
            embedding_text=embedding_text,
            retrieval_text=window_text,
            assets=[],
            metadata=ChildChunkMetadata(
                page_numbers=page_nums,
                is_atomic=False,
                is_atomic_fragment=(total > 1),
                fragment_index=idx if total > 1 else None,
                fragment_total=total if total > 1 else None,
            ),
        ))

    return children


def _build_windows(
    sentences: list[str],
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> list[str]:
    """
    将句子列表合并为滑动窗口文本块（带重叠）。

    用 for 循环逐句消费，保证每次迭代都前进——避免「单句长度超过
    max_chars - overlap_chars」时 flush 后反复重试同一句导致**死循环卡死事件循环**。
    """
    windows: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        # 单句本身超过窗口上限：先收尾当前窗口，再把长句按 max_chars 硬切成多块
        if len(sent) > max_chars:
            if current:
                windows.append("".join(current))
                current = []
                current_len = 0
            for k in range(0, len(sent), max_chars):
                windows.append(sent[k:k + max_chars])
            continue

        if current_len + len(sent) <= max_chars:
            current.append(sent)
            current_len += len(sent)
        else:
            # 收尾当前窗口；新窗口 = overlap 前缀 + 本句（本句一定被消费，不再重试）
            if current:
                windows.append("".join(current))
                overlap_text = "".join(current)[-overlap_chars:] if overlap_chars else ""
                current = [overlap_text, sent] if overlap_text else [sent]
                current_len = len(overlap_text) + len(sent)
            else:
                current = [sent]
                current_len = len(sent)

    if current:
        tail = "".join(current)
        # 尾部太短且已有窗口时合并到最后一个
        if windows and len(tail) < min_chars:
            windows[-1] = windows[-1] + tail
        else:
            windows.append(tail)

    return windows if windows else ["".join(sentences)]


# ─────────────────────────────────────────────────────────────
# 工具：构建 retrieval_text
# ─────────────────────────────────────────────────────────────

def _build_retrieval_text(blk: IRBlock) -> str:
    """根据块类型生成 retrieval_text（不含 header_path 前缀）。"""
    if blk.type == "image":
        caption = blk.text.strip()
        return f"[图片: {caption}]" if caption else "[图片]"
    elif blk.type == "table":
        caption = blk.text.strip()
        html = blk.metadata.table_html or ""
        if caption:
            return f"[表格: {caption}]"
        elif html:
            # 剥离 HTML 标签取纯文本（简单版）
            plain = re.sub(r'<[^>]+>', ' ', html).strip()
            return plain[:500] if plain else "[表格]"
        return "[表格]"
    elif blk.type == "equation":
        return blk.metadata.math_content or blk.text or "[公式]"
    else:
        return blk.text.strip()


def _extract_bboxes(blk: IRBlock) -> tuple[list[list[float]], list[list[float]], str]:
    """从 IRBlock 提取前端高亮所需坐标。"""
    bbox_norm1000: list[list[float]] = []
    bbox_page: list[list[float]] = []

    if blk.bbox_norm1000 and getattr(blk.bbox_norm1000, "coords", None):
        bbox_norm1000.append([float(v) for v in blk.bbox_norm1000.coords[:4]])

    if blk.bbox_page and getattr(blk.bbox_page, "coords", None):
        bbox_page.append([float(v) for v in blk.bbox_page.coords[:4]])

    anchor_origin_pdf_path = ""
    if blk.anchor and blk.anchor.origin_pdf_path:
        anchor_origin_pdf_path = blk.anchor.origin_pdf_path

    return bbox_norm1000, bbox_page, anchor_origin_pdf_path
