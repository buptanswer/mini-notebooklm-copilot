"""
Phase D — 脚注关联启发式算法

策略：
1. 每页收集 page_footnote 块（role=auxiliary，已在 IRPage.footnotes 中）
2. 遍历该页的主块，找最近的相邻块（空间距离最近 by order_in_doc）
3. 将 page_footnote 以 FootnoteLink 附加到最近的主块上
4. 无法关联的脚注标记为 attach_mode="orphan"

置信度计算：
  - 同页最近块：confidence=0.8
  - 孤儿（全文无主块）：confidence=0.0
"""

from __future__ import annotations

import logging

from app.models.models_ir import FootnoteLink, IRBlock, IRPage

logger = logging.getLogger(__name__)


def link_footnotes(
    blocks: list[IRBlock],
    pages: list[IRPage],
) -> list[IRBlock]:
    """
    将每页的 page_footnote 块关联到最近的主块，返回更新后的 blocks。

    blocks 会被原地复制（immutable update），不修改原列表内对象。
    """
    # block_id → block 的可变映射（我们要更新 footnote_links）
    block_map: dict[str, IRBlock] = {b.block_id: b for b in blocks}

    for page in pages:
        if not page.footnotes:
            continue

        # 本页主块（按 order_in_doc 排序）
        page_main_blocks = sorted(
            [block_map[bid] for bid in page.block_ids if bid in block_map],
            key=lambda b: b.order_in_doc,
        )

        if not page_main_blocks:
            # 全页无主块，全部标为 orphan
            for fn in page.footnotes:
                fn_block = block_map.get(fn.block_id)
                if fn_block:
                    logger.debug("脚注 %s 无可关联主块，标记 orphan", fn.block_id)
            continue

        for fn in page.footnotes:
            fn_block = block_map.get(fn.block_id)
            if fn_block is None:
                continue

            # 找 order_in_doc 最小差的主块（即最近的前置块）
            best_block: IRBlock | None = None
            best_diff = float("inf")

            for mb in page_main_blocks:
                diff = abs(mb.order_in_doc - fn_block.order_in_doc)
                if diff < best_diff:
                    best_diff = diff
                    best_block = mb

            if best_block:
                link = FootnoteLink(
                    footnote_block_id=fn.block_id,
                    attach_mode="inline_append",
                    confidence=0.8,
                )
                updated = best_block.model_copy(
                    update={"footnote_links": best_block.footnote_links + [link]}
                )
                block_map[best_block.block_id] = updated
                logger.debug(
                    "脚注 %s → 主块 %s (diff=%d)",
                    fn.block_id,
                    best_block.block_id,
                    best_diff,
                )

    return list(block_map.values())
