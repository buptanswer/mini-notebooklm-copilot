"""
Parent Chunker — 以 section 为边界生成 Parent Chunk

规则：
- 每个 IRSection 对应一个 ParentChunk（跳过 synthetic root section）
- text_for_generation = 所有 main 块按 order_in_doc 顺序拼接的完整文本
- assets = 该 section 内所有块的 asset_id 汇总
- metadata 透传页眉页脚页码（从 IRPage 的 auxiliary 提取）
- page_span = [min_page_idx, max_page_idx]

text_for_generation 拼接策略：
  title    → 直接输出文本
  paragraph/list/code/equation → 直接输出文本
  image    → "[图片: {caption}]" 或 "[图片]"
  table    → "[表格: {caption}]" 或 "[表格]"
  辅助块   → 不参与拼接（page_header/footer/number/footnote）
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from app.models.models_chunk import ParentChunk, ParentChunkMetadata
from app.models.models_ir import IRBlock, IRPage, IRSection


_SKIP_ROLE = {"auxiliary"}   # 辅助块不进入 text_for_generation
_SYNTHETIC_ROOT_LEVEL = 0    # level=0 的合成根不生成 ParentChunk


def build_parent_chunks(
    sections: list[IRSection],
    blocks: list[IRBlock],
    pages: list[IRPage],
    doc_id: str,
) -> list[ParentChunk]:
    """
    遍历所有 section 生成 ParentChunk 列表。

    Returns:
        list[ParentChunk]，顺序与 section 一致（BFS/DFS 不重要，按 section 列表顺序）
    """
    # 构建快速查找索引
    block_map: dict[str, IRBlock] = {b.block_id: b for b in blocks}
    page_auxiliary: dict[int, IRPage] = {p.page_idx: p for p in pages}

    result: list[ParentChunk] = []

    for section in sections:
        # 跳过 synthetic root（level=0 且 synthetic=True）
        if section.level == _SYNTHETIC_ROOT_LEVEL and section.synthetic:
            continue

        parent_chunk_id = f"pc-{uuid.uuid4().hex[:12]}"

        # 收集块：按 order_in_doc 排序
        sec_blocks = sorted(
            [block_map[bid] for bid in section.block_ids if bid in block_map],
            key=lambda b: b.order_in_doc,
        )

        # text_for_generation
        text_parts: list[str] = []
        asset_ids: list[str] = []
        page_indices: set[int] = set()

        for blk in sec_blocks:
            if blk.role in _SKIP_ROLE:
                continue
            page_indices.add(blk.page_idx)

            # 资产收集
            for asset in blk.assets:
                asset_ids.append(asset.asset_id)

            # 文本拼接
            if blk.type in {"image"}:
                caption = blk.text.strip()
                text_parts.append(f"[图片: {caption}]" if caption else "[图片]")
            elif blk.type in {"table"}:
                caption = blk.text.strip()
                text_parts.append(f"[表格: {caption}]" if caption else "[表格]")
            elif blk.text:
                text_parts.append(blk.text)

        text_for_generation = "\n\n".join(filter(None, text_parts))

        # page_span
        page_span: list[int] = (
            [min(page_indices), max(page_indices)] if page_indices else []
        )

        # 页面辅助信息（按 page_span 范围收集）
        page_headers: list[str] = []
        page_footers: list[str] = []
        page_numbers: list[str] = []
        for pi in sorted(page_indices):
            pg = page_auxiliary.get(pi)
            if not pg:
                continue
            page_headers.extend(a.text for a in pg.auxiliary.page_headers if a.text)
            page_footers.extend(a.text for a in pg.auxiliary.page_footers if a.text)
            page_numbers.extend(a.text for a in pg.auxiliary.page_numbers if a.text)

        result.append(ParentChunk(
            parent_chunk_id=parent_chunk_id,
            doc_id=doc_id,
            section_id=section.section_id,
            header_path=list(section.header_path),
            title=section.title,
            page_span=page_span,
            block_ids=[b.block_id for b in sec_blocks if b.role not in _SKIP_ROLE],
            text_for_generation=text_for_generation,
            assets=asset_ids,
            metadata=ParentChunkMetadata(
                page_headers=list(dict.fromkeys(page_headers)),
                page_footers=list(dict.fromkeys(page_footers)),
                page_numbers=list(dict.fromkeys(page_numbers)),
            ),
        ))

    return result
