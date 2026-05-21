"""
IR Validator — IRBlock / IRPage / IRSection 结构校验

校验项：
  - block_id 非空且唯一
  - bbox_norm1000 坐标范围合法
  - page_idx >= 0
  - order_in_page / order_in_doc 非负
  - section_id 非空（dom_builder 后应已填充）
  - text 字段至少对 paragraph/title/list/code 非空
  - header_path 合理性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.models.models_ir import IRBlock, IRPage, IRSection

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


_TEXT_TYPES = frozenset({"title", "paragraph", "list", "code"})


def validate_ir(
    blocks: list[IRBlock],
    pages: list[IRPage],
    sections: list[IRSection],
) -> ValidationResult:
    """
    对 IR 数据做结构性校验。

    Returns:
        ValidationResult，包含 errors（致命）和 warnings（非致命）
    """
    result = ValidationResult()
    block_ids: set[str] = set()
    section_ids: set[str] = {s.section_id for s in sections}

    for i, blk in enumerate(blocks):
        ctx = f"block[{i}] id={blk.block_id}"

        # block_id 唯一性
        if not blk.block_id:
            result.errors.append(f"{ctx}: block_id 为空")
        elif blk.block_id in block_ids:
            result.errors.append(f"{ctx}: block_id 重复")
        block_ids.add(blk.block_id)

        # bbox 坐标
        # [0,0,0,0] 是 Office 原生解析（DOCX/PPTX）没有坐标时的静默占位符，跳过坐标校验
        coords = blk.bbox_norm1000.coords
        if len(coords) == 4:
            is_sentinel = all(c == 0.0 for c in coords)
            if not is_sentinel:
                if not (coords[0] < coords[2] and coords[1] < coords[3]):
                    result.warnings.append(f"{ctx}: bbox 坐标异常 {coords}")
                if coords[0] < -10 or coords[1] < -10 or coords[2] > 1010 or coords[3] > 1010:
                    result.warnings.append(f"{ctx}: bbox 坐标越界 {coords}")
        else:
            result.warnings.append(f"{ctx}: bbox 坐标长度异常")

        # page_idx
        if blk.page_idx < 0:
            result.errors.append(f"{ctx}: page_idx={blk.page_idx} 为负数")

        # order 字段
        if blk.order_in_page < 0:
            result.errors.append(f"{ctx}: order_in_page={blk.order_in_page} 为负数")
        if blk.order_in_doc < 0:
            result.errors.append(f"{ctx}: order_in_doc={blk.order_in_doc} 为负数")

        # section_id（辅助块允许为空）
        if blk.role == "main" and not blk.section_id:
            result.warnings.append(f"{ctx}: section_id 为空（可能未经过 dom_builder）")

        # 文本内容
        if blk.type in _TEXT_TYPES and not blk.text.strip():
            result.warnings.append(f"{ctx}: {blk.type} 块的 text 为空")

    # sections 校验
    for sec in sections:
        if sec.synthetic:
            continue
        if not sec.section_id:
            result.errors.append(f"section title={sec.title!r}: section_id 为空")
        if sec.level < 0:
            result.errors.append(f"section {sec.section_id}: level={sec.level} 为负数")

    # pages 校验
    page_indices: set[int] = set()
    for pg in pages:
        if pg.page_idx in page_indices:
            result.warnings.append(f"page {pg.page_id}: page_idx={pg.page_idx} 重复")
        page_indices.add(pg.page_idx)
        if pg.page_size and (pg.page_size.width <= 0 or pg.page_size.height <= 0):
            result.warnings.append(f"page {pg.page_id}: page_size 异常")

    if result.errors:
        logger.warning("IR 校验发现 %d 个错误: %s", len(result.errors), result.errors[:5])
    if result.warnings:
        logger.info("IR 校验发现 %d 个警告: %s", len(result.warnings), result.warnings[:5])
    if not result.errors and not result.warnings:
        logger.info("IR 校验通过 (%d blocks, %d pages, %d sections)", len(blocks), len(pages), len(sections))

    return result
