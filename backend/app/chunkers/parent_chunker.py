"""
Parent Chunker — 按"标题粒度"把 section 树聚合成 Parent Chunk

粒度规则（parent_level，默认 1）：
- "N 级标题(含其下所有子标题的内容)合成 1 个父块"。
- 按 parent_level 在 section 树上"切一刀"：级别 ≤ N 的 section 各自成组根，级别 > N 的
  section 内容上卷到最近的 ≤ N 祖先组根。每个组根聚合自身 + 所有后代的正文块为一个父块。
- 父块越大 → 给问答模型的上下文越全(Small-to-Big)，但越费 token。

出不出父块（替代旧的"纯标题容器/合成根"特判）：
- 一个组只有当聚合后含 ≥1 个正文块(role != auxiliary 且 type != title)时才出父块。
- 由此天然处理两类边界：①有标题文档的 synthetic 根/纯标题章节无正文 → 不出父块（噪音）；
  ②无标题文档的 synthetic 根直含全部正文 → 照常出父块（修复"heading-less 文档 0 chunk"）。

text_for_generation 拼接策略：
  title    → 直接输出文本（聚合后子标题作为结构内联保留）
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


def build_parent_chunks(
    sections: list[IRSection],
    blocks: list[IRBlock],
    pages: list[IRPage],
    doc_id: str,
    *,
    parent_level: int = 1,
) -> list[ParentChunk]:
    """
    按 parent_level 将 section 树聚合成 ParentChunk 列表。

    Args:
        parent_level: N 级标题=1 父块（默认 1）。级别 > N 的 section 内容上卷到 ≤ N 祖先。

    Returns:
        list[ParentChunk]，按组根 section 在 sections 中的出现顺序。
    """
    block_map: dict[str, IRBlock] = {b.block_id: b for b in blocks}
    page_auxiliary: dict[int, IRPage] = {p.page_idx: p for p in pages}
    section_map: dict[str, IRSection] = {s.section_id: s for s in sections}
    level = max(1, parent_level)

    def group_root_id(sec: IRSection) -> str:
        """组根 = 自身或最近的级别 ≤ level 的祖先（树自顶向下 level 递增，故自底向上第一个 ≤ level 即最深的 ≤ level）。"""
        if sec.level <= level:
            return sec.section_id
        cur = sec
        while cur.parent_section_id and cur.parent_section_id in section_map:
            cur = section_map[cur.parent_section_id]
            if cur.level <= level:
                return cur.section_id
        return cur.section_id  # 兜底：走到顶（synthetic 根 level=0 必 ≤ level）

    # 按组根聚合成员 section（成员块上卷到组根）
    groups: dict[str, list[IRSection]] = defaultdict(list)
    for s in sections:
        groups[group_root_id(s)].append(s)

    result: list[ParentChunk] = []

    # 以组根 section 在 sections 中的顺序产出（保持文档顺序）
    for root_sec in sections:
        members = groups.get(root_sec.section_id)
        if members is None:
            continue  # 非组根（其内容已上卷到别的组根）

        # 聚合成员块：按 order_in_doc 排序
        member_block_ids: list[str] = []
        for m in members:
            member_block_ids.extend(m.block_ids)
        sec_blocks = sorted(
            [block_map[bid] for bid in member_block_ids if bid in block_map],
            key=lambda b: b.order_in_doc,
        )

        # 仅当组内含 ≥1 正文块时才出父块（纯标题/空容器/合成根无正文 → 跳过）
        if not any(b.role not in _SKIP_ROLE and b.type != "title" for b in sec_blocks):
            continue

        parent_chunk_id = f"pc-{uuid.uuid4().hex[:12]}"

        text_parts: list[str] = []
        asset_ids: list[str] = []
        page_indices: set[int] = set()

        for blk in sec_blocks:
            if blk.role in _SKIP_ROLE:
                continue
            page_indices.add(blk.page_idx)

            for asset in blk.assets:
                asset_ids.append(asset.asset_id)

            if blk.type in {"image"}:
                caption = blk.text.strip()
                text_parts.append(f"[图片: {caption}]" if caption else "[图片]")
            elif blk.type in {"table"}:
                caption = blk.text.strip()
                text_parts.append(f"[表格: {caption}]" if caption else "[表格]")
            elif blk.text:
                text_parts.append(blk.text)

        text_for_generation = "\n\n".join(filter(None, text_parts))

        page_span: list[int] = (
            [min(page_indices), max(page_indices)] if page_indices else []
        )

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
            section_id=root_sec.section_id,
            header_path=list(root_sec.header_path),
            title=root_sec.title,
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
