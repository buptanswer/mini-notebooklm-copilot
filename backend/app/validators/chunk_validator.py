"""
Chunk Validator — ParentChunk / ChildChunk 结构校验

校验项：
  - ParentChunk: parent_chunk_id 非空、section_id 非空、doc_id 非空
  - ChildChunk: child_chunk_id 非空、embedding_text 非空、parent_chunk_id 引用存在
  - Parent-Child 映射完整性
  - page_span 合理性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.models.models_chunk import ChildChunk, ParentChunk

logger = logging.getLogger(__name__)


@dataclass
class ChunkValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_chunks(
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
) -> ChunkValidationResult:
    """
    对 ParentChunk 和 ChildChunk 做结构性校验。

    Returns:
        ChunkValidationResult
    """
    result = ChunkValidationResult()
    parent_ids: set[str] = set()

    # ParentChunk 校验
    for pc in parent_chunks:
        if not pc.parent_chunk_id:
            result.errors.append("ParentChunk 缺少 parent_chunk_id")
        else:
            parent_ids.add(pc.parent_chunk_id)

        if not pc.doc_id:
            result.errors.append(f"ParentChunk {pc.parent_chunk_id}: doc_id 为空")
        if not pc.section_id:
            result.warnings.append(f"ParentChunk {pc.parent_chunk_id}: section_id 为空")

        if pc.page_span and len(pc.page_span) == 2:
            if pc.page_span[0] > pc.page_span[1]:
                result.warnings.append(f"ParentChunk {pc.parent_chunk_id}: page_span 逆序 {pc.page_span}")

    # ChildChunk 校验
    child_ids: set[str] = set()
    orphan_parent_refs: set[str] = set()

    for cc in child_chunks:
        if not cc.child_chunk_id:
            result.errors.append("ChildChunk 缺少 child_chunk_id")
        else:
            child_ids.add(cc.child_chunk_id)

        if not cc.embedding_text.strip():
            result.errors.append(f"ChildChunk {cc.child_chunk_id}: embedding_text 为空")
        if not cc.doc_id:
            result.errors.append(f"ChildChunk {cc.child_chunk_id}: doc_id 为空")

        # parent_chunk_id 引用完整性
        if cc.parent_chunk_id and cc.parent_chunk_id not in parent_ids:
            orphan_parent_refs.add(cc.parent_chunk_id)

        # page_span
        if cc.page_span and len(cc.page_span) == 2:
            if cc.page_span[0] > cc.page_span[1]:
                result.warnings.append(f"ChildChunk {cc.child_chunk_id}: page_span 逆序 {cc.page_span}")

        # chunk_type 合理性
        valid_types = {"paragraph", "list", "code", "image", "table", "equation"}
        if cc.chunk_type not in valid_types:
            result.warnings.append(f"ChildChunk {cc.child_chunk_id}: 未知 chunk_type={cc.chunk_type}")

    if orphan_parent_refs:
        result.warnings.append(
            f"{len(orphan_parent_refs)} 个 ChildChunk 引用了不存在的 parent_chunk_id: "
            f"{list(orphan_parent_refs)[:5]}"
        )

    # 统计
    if result.errors:
        logger.warning("Chunk 校验发现 %d 个错误: %s", len(result.errors), result.errors[:5])
    if result.warnings:
        logger.info("Chunk 校验发现 %d 个警告: %s", len(result.warnings), result.warnings[:5])
    if not result.errors and not result.warnings:
        logger.info("Chunk 校验通过 (%d parent, %d child)", len(parent_chunks), len(child_chunks))

    return result
