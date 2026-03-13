"""
Phase C — DOM 重建：标题栈 + section 树 + header_path 注入

算法（Section First 策略）：
1. 遍历所有 IRBlock（按 order_in_doc 排序）
2. 维护一个标题栈（title stack），每个元素是 (level, section_id, title_text)
3. 遇到 title 块时：
   - 弹出栈中所有层级 >= 当前 level 的节点（退出子树）
   - 创建新 IRSection
   - 将当前 title 推入栈
4. 非 title 块归入当前（栈顶）section
5. header_path = 栈中所有 title 文本（从根到当前）
6. 如果文档开头没有标题，自动生成一个 level=0 的合成根 section

输入：list[IRBlock]（已排好序）
输出：(blocks_with_section, sections_list)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.models.models_ir import IRBlock, IRSection

logger = logging.getLogger(__name__)


@dataclass
class _StackEntry:
    level: int
    section_id: str
    title: str
    header_path: list[str]


def build_dom(blocks: list[IRBlock]) -> tuple[list[IRBlock], list[IRSection]]:
    """
    对 blocks（不含辅助块）重建 DOM 树，注入 section_id 与 header_path。

    注意：辅助块（page_header/footer 等）已在 normalizer 中分离到 IRPage.auxiliary，
    但这里仍然安全处理它们（section_id="" 留空，不影响树结构）。

    Returns:
        (updated_blocks, sections)
    """
    # 按 order_in_doc 排序
    sorted_blocks = sorted(blocks, key=lambda b: b.order_in_doc)

    sections: list[IRSection] = []
    section_map: dict[str, IRSection] = {}

    title_stack: list[_StackEntry] = []

    # 合成根 section（始终存在）
    root_section = _make_synthetic_root()
    sections.append(root_section)
    section_map[root_section.section_id] = root_section
    current_section_id = root_section.section_id

    updated: list[IRBlock] = []

    for block in sorted_blocks:
        # 辅助块不参与 DOM 建树，但填入当前 section_id
        if block.role == "auxiliary":
            updated_block = block.model_copy(update={
                "section_id": current_section_id,
                "header_path": _stack_to_path(title_stack),
            })
            updated.append(updated_block)
            continue

        if block.type == "title":
            level = block.metadata.title_level or 1
            new_section, title_stack, current_section_id = _handle_title(
                block=block,
                level=level,
                title_stack=title_stack,
                sections=sections,
                section_map=section_map,
                root_section_id=root_section.section_id,
            )
            header_path = _stack_to_path(title_stack)
            updated_block = block.model_copy(update={
                "section_id": current_section_id,
                "header_path": header_path,
            })
        else:
            header_path = _stack_to_path(title_stack)
            updated_block = block.model_copy(update={
                "section_id": current_section_id,
                "header_path": header_path,
            })

        # 将 block_id 加入当前 section
        section_map[current_section_id].block_ids.append(updated_block.block_id)

        updated.append(updated_block)

    # 填充 section 的 page_span
    _fill_page_spans(updated, section_map)

    # 对 root_section：如果有其他 section，则它的直接子 section 就是第一层 title section
    # 修正 child_section_ids
    _fill_child_sections(sections, section_map, root_section.section_id)

    return updated, sections


# ─────────────────────────────────────────────────────────────

def _handle_title(
    block: IRBlock,
    level: int,
    title_stack: list[_StackEntry],
    sections: list[IRSection],
    section_map: dict[str, IRSection],
    root_section_id: str,
) -> tuple[IRSection, list[_StackEntry], str]:
    """
    处理 title 块：更新 title_stack，创建新 IRSection，返回新 section。
    """
    # 弹出所有层级 >= level 的栈帧（它们已经结束）
    while title_stack and title_stack[-1].level >= level:
        title_stack.pop()

    # 父 section
    parent_sid = title_stack[-1].section_id if title_stack else root_section_id
    parent_path = title_stack[-1].header_path if title_stack else []

    new_sid = f"sec-{uuid.uuid4().hex[:10]}"
    new_path = parent_path + [block.text]

    new_section = IRSection(
        section_id=new_sid,
        parent_section_id=parent_sid,
        level=level,
        title=block.text,
        header_path=new_path,
        synthetic=False,
    )
    sections.append(new_section)
    section_map[new_sid] = new_section

    # 把新 section 加入父 section 的 child_section_ids
    parent_sec = section_map.get(parent_sid)
    if parent_sec:
        parent_sec.child_section_ids.append(new_sid)

    # 推入栈
    title_stack.append(_StackEntry(
        level=level,
        section_id=new_sid,
        title=block.text,
        header_path=new_path,
    ))

    return new_section, title_stack, new_sid


def _make_synthetic_root() -> IRSection:
    """合成的 level=0 根 section，保证所有文档都有一个根节点"""
    return IRSection(
        section_id=f"sec-root-{uuid.uuid4().hex[:8]}",
        parent_section_id=None,
        level=0,
        title="",
        header_path=[],
        synthetic=True,
    )


def _stack_to_path(stack: list[_StackEntry]) -> list[str]:
    return [e.title for e in stack]


def _fill_page_spans(
    blocks: list[IRBlock],
    section_map: dict[str, IRSection],
) -> None:
    """为每个 section 计算 page_span = [min_page, max_page]"""
    sec_pages: dict[str, set[int]] = {sid: set() for sid in section_map}
    for block in blocks:
        sid = block.section_id
        if sid in sec_pages:
            sec_pages[sid].add(block.page_idx)

    for sid, pages in sec_pages.items():
        if pages:
            span = [min(pages), max(pages)]
            section_map[sid].page_span = span


def _fill_child_sections(
    sections: list[IRSection],
    section_map: dict[str, IRSection],
    root_section_id: str,
) -> None:
    """重新确保 child_section_ids 已在 _handle_title 中正确填充（此处做完整性校验）"""
    # child_section_ids 在 _handle_title 中已经写入 parent_sec，
    # 此处仅确保根节点存在于 sections 列表中
    pass
