"""
Phase B — 将 content_list_v2.json + layout.json 归一化为 IRBlock 列表

核心职责：
1. 读取并宽松解析 content_list_v2.json（按页二维数组）
2. 从 layout.json 提取页面尺寸（page_size）
3. 块类型映射：content_list_v2 类型 → BlockType
4. 坐标处理：
   - content_list_v2 的 bbox 已是 norm1000（直接用）
   - layout.json 的 bbox 是绝对坐标，用 page_size 换算为 bbox_page
5. 辅助块（page_header/footer/number/footnote）→ role="auxiliary"
6. 多模态块（image/table）→ assets 填充
7. 文本提取：各类型按规则 flatten 为纯文本字段

宽松降级策略：
  - 未知 type → 降级为 paragraph，记录 degraded_modes
  - bbox 长度异常 → 用 [0,0,0,0] 兜底，记录 warning
  - content 为 None → 空内容，记录 warning
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.models.models_ir import (
    Anchor,
    Asset,
    AssetType,
    BboxNorm1000,
    BboxPage,
    BlockMetadata,
    BlockRole,
    BlockType,
    IRBlock,
    IRPage,
    PageAuxiliary,
    PageAuxiliaryRef,
    PageFootnote,
    PageSize,
    RawSourceTrace,
    TextSegment,
)

logger = logging.getLogger(__name__)

# ── content_list_v2 类型 → IRBlockType 映射 ──────────────────
_V2_TYPE_MAP: dict[str, BlockType] = {
    "title": "title",
    "paragraph": "paragraph",
    "list": "list",
    "image": "image",
    "table": "table",
    "equation_interline": "equation",
    "code": "code",
    "page_header": "page_header",
    "page_footer": "page_footer",
    "page_number": "page_number",
    "page_footnote": "page_footnote",
    # MinerU 新增类型（兼容映射）
    "chart": "image",   # 图表 → image（内含截图 + 提取数据）
    "index": "list",    # 目录 → list
}

_AUXILIARY_TYPES: frozenset[BlockType] = frozenset(
    {"page_header", "page_footer", "page_number", "page_footnote"}
)

# ── 各块级/内容级已知字段白名单（用于未知字段 WARNING 检测）─────────────
# anchor: DOCX Office 原生解析添加的文档锚点，sub_type: chart/equation 子类型
_KNOWN_BLOCK_KEYS = frozenset({"type", "bbox", "content", "anchor", "sub_type"})

_KNOWN_CONTENT_KEYS: dict[str, frozenset] = {
    "title":        frozenset({"level", "title_content"}),
    "paragraph":    frozenset({"paragraph_content"}),
    "list":         frozenset({"list_type", "list_items", "attribute"}),  # attribute: "unordered"/"ordered"
    "code":         frozenset({"code_content", "code_language", "code_caption"}),
    "equation":     frozenset({"math_content", "math_type", "image_source"}),
    "image":        frozenset({
                        "image_source", "image_caption", "image_footnote",
                        "content",  # VLM OCR 提取文本（新版 MinerU 可能包含）
                    }),
    "table":        frozenset({
                        "html", "image_source", "table_caption", "table_footnote",
                        "table_nest_level", "table_type",
                    }),
    # chart 类型的 content 结构（映射为 image）
    "chart":        frozenset({
                        "image_source", "content", "chart_caption", "chart_footnote",
                    }),
    # index 类型（TOC，映射为 list）
    "index":        frozenset({"list_type", "list_items", "attribute"}),
    # 辅助块：真实字段是 {type}_content，不是 text
    "page_header":   frozenset({"page_header_content"}),
    "page_footer":   frozenset({"page_footer_content"}),
    "page_number":   frozenset({"page_number_content"}),
    "page_footnote": frozenset({"page_footnote_content"}),
}

_KNOWN_TEXT_SEGMENT_KEYS = frozenset({
    "type", "content",
    "url",      # hyperlink 类型附带的 URL 字段
    "style",    # Office 原生解析添加的字体/样式信息（忽略，不用于嵌入）
    "children", # hyperlink 显示文本拆分出的嵌套子文本段（新版 MinerU，2026-05）
})
_KNOWN_LIST_ITEM_KEYS    = frozenset({
    "item_type", "item_content",
    "ilevel",    # 缩进层级（Office 原生解析）
    "prefix",    # 项目符号前缀（"-", "1.", 等）
    "anchor",    # 文档锚点（TOC 中的超链接目标）
})
_KNOWN_IMAGE_SOURCE_KEYS = frozenset({"path"})


def _warn_extra_keys(
    d: dict,
    known: frozenset,
    ctx: str,
    degraded: list[str] | None = None,
) -> None:
    """
    检查 dict d 中是否存在 known 集合以外的键。
    若有，输出 WARNING；若提供了 degraded 列表，还追加一条降级记录。
    """
    extra = set(d.keys()) - known
    if extra:
        logger.warning(
            "[MinerU 未知字段] %s 发现未预期键: %s"
            " — 可能来自新版 API，请更新解析逻辑以避免信息丢失",
            ctx,
            sorted(extra),
        )
        if degraded is not None:
            degraded.append(f"unknown_keys_{ctx}")


# ═══════════════════════════════════════════════════════════
# 公共函数
# ═══════════════════════════════════════════════════════════

def normalize(
    content_list_v2_path: str,
    layout_path: str | None,
    doc_id: str,
    source_filename: str,
    source_format: str,
    images_dir: str | None,
    origin_pdf_path: str | None = None,
) -> tuple[list[IRBlock], list[IRPage], list[str]]:
    """
    主入口。

    Returns:
        (blocks, pages, degraded_modes)
    """
    degraded: list[str] = []

    # 1. 读取 content_list_v2.json
    raw_pages: list[list[Any]] = _load_json(content_list_v2_path)
    if not isinstance(raw_pages, list):
        raise ValueError(f"content_list_v2.json 顶层不是列表: {content_list_v2_path}")

    # 2. 读取 layout.json 提取页面尺寸（可选）
    page_sizes: dict[int, tuple[float, float]] = {}
    if layout_path:
        page_sizes = _extract_page_sizes(layout_path, degraded)

    # 3. 逐页归一化
    all_blocks: list[IRBlock] = []
    ir_pages: list[IRPage] = []
    global_order = 0

    for page_idx, raw_page in enumerate(raw_pages):
        if not isinstance(raw_page, list):
            logger.warning("page %d 不是列表，跳过", page_idx)
            degraded.append(f"page_{page_idx}_not_list")
            continue

        pw, ph = page_sizes.get(page_idx, (1000.0, 1000.0))
        page_id = f"page-{page_idx:04d}"
        page_size = PageSize(width=pw, height=ph)

        ir_page = IRPage(
            page_id=page_id,
            page_idx=page_idx,
            page_size=page_size,
        )

        page_main_block_ids: list[str] = []
        order_in_page = 0

        for raw_block in raw_page:
            if not isinstance(raw_block, dict):
                continue

            block, block_degraded = _normalize_block(
                raw_block=raw_block,
                page_idx=page_idx,
                order_in_page=order_in_page,
                order_in_doc=global_order,
                page_id=page_id,
                page_width=pw,
                page_height=ph,
                doc_id=doc_id,
                source_filename=source_filename,
                source_format=source_format,
                images_dir=images_dir,
                origin_pdf_path=origin_pdf_path,
            )

            degraded.extend(block_degraded)

            # 辅助块写入页面 auxiliary，主块进入 block 列表
            btype: BlockType = block.type
            if btype in _AUXILIARY_TYPES:
                _append_auxiliary(ir_page, block)
            else:
                page_main_block_ids.append(block.block_id)
                ir_page.block_ids.append(block.block_id)

            all_blocks.append(block)
            order_in_page += 1
            global_order += 1

        ir_pages.append(ir_page)

    return all_blocks, ir_pages, degraded


# ═══════════════════════════════════════════════════════════
# 内部：单块归一化
# ═══════════════════════════════════════════════════════════

def _normalize_block(
    raw_block: dict,
    page_idx: int,
    order_in_page: int,
    order_in_doc: int,
    page_id: str,
    page_width: float,
    page_height: float,
    doc_id: str,
    source_filename: str,
    source_format: str,
    images_dir: str | None,
    origin_pdf_path: str | None = None,
) -> tuple[IRBlock, list[str]]:
    """归一化单个 content_list_v2 块，返回 (IRBlock, degraded_list)"""
    degraded: list[str] = []

    raw_type: str = raw_block.get("type", "paragraph")
    block_type: BlockType = _V2_TYPE_MAP.get(raw_type, "paragraph")
    if raw_type not in _V2_TYPE_MAP:
        logger.warning("未知 type=%s，降级为 paragraph", raw_type)
        degraded.append(f"unknown_type_{raw_type}")

    # 检查块顶层字段是否有未预期键（已知: type / bbox / content / anchor / sub_type）
    _warn_extra_keys(
        raw_block,
        _KNOWN_BLOCK_KEYS,
        f"block[p{page_idx},type={raw_type}]",
        degraded,
    )

    role: BlockRole = "auxiliary" if block_type in _AUXILIARY_TYPES else "main"

    # bbox 处理：
    # - bbox 键不存在（Office 原生解析）→ 静默使用 [0,0,0,0]，不产生警告
    # - bbox 键存在但长度不足 → 产生 bad_bbox 警告（真正的坐标异常）
    raw_bbox_value = raw_block.get("bbox")   # None 表示键不存在
    if raw_bbox_value is None:
        # Office 原生解析：没有坐标信息，静默兜底，不写 degraded
        bbox_norm = BboxNorm1000(coords=[0.0, 0.0, 0.0, 0.0])
        bbox_page = None
        raw_bbox: list = []
    else:
        raw_bbox = raw_bbox_value if isinstance(raw_bbox_value, list) else []
        bbox_norm = _safe_bbox_norm1000(raw_bbox, degraded, f"p{page_idx}-type{raw_type}")
        bbox_page = _compute_bbox_page(raw_bbox, page_width, page_height)

    block_id = f"p{page_idx:04d}-b{order_in_page:04d}-{uuid.uuid4().hex[:6]}"

    content: Any = raw_block.get("content")

    text, segments, assets, metadata = _extract_content(
        block_type=block_type,
        raw_type=raw_type,
        content=content,
        images_dir=images_dir,
        block_id=block_id,
        degraded=degraded,
    )

    block = IRBlock(
        block_id=block_id,
        page_idx=page_idx,
        order_in_page=order_in_page,
        order_in_doc=order_in_doc,
        section_id="",          # dom_builder 后填充
        header_path=[],         # dom_builder 后填充
        type=block_type,
        role=role,
        bbox_norm1000=bbox_norm,
        bbox_page=bbox_page,
        anchor=Anchor(
            page_id=page_id,
            origin_pdf_path=origin_pdf_path or "",
        ) if origin_pdf_path else None,
        text=text,
        segments=segments,
        assets=assets,
        metadata=metadata,
        raw_source=RawSourceTrace(
            source_file="content_list_v2.json",
            source_type=raw_type,
        ),
    )

    return block, degraded


# ═══════════════════════════════════════════════════════════
# 内容提取
# ═══════════════════════════════════════════════════════════

def _extract_content(
    block_type: BlockType,
    raw_type: str,
    content: Any,
    images_dir: str | None,
    block_id: str,
    degraded: list[str],
) -> tuple[str, list[TextSegment], list[Asset], BlockMetadata]:
    """
    根据块类型从 content 对象提取 text/segments/assets/metadata。
    content 为 None 时安全兜底。

    raw_type: 原始 MinerU 类型字符串（未映射），用于选择正确的已知字段集合。
    """
    text = ""
    segments: list[TextSegment] = []
    assets: list[Asset] = []
    metadata = BlockMetadata()

    if content is None:
        logger.warning("block_id=%s content=None，类型=%s", block_id, block_type)
        degraded.append(f"content_none_{block_id}")
        return text, segments, assets, metadata

    # 检查 content dict 中是否有未预期字段
    # 优先用原始 raw_type 查找（chart/index 有自己的字段集）
    if isinstance(content, dict):
        _content_known = _KNOWN_CONTENT_KEYS.get(raw_type) or _KNOWN_CONTENT_KEYS.get(block_type)
        if _content_known is not None:
            _warn_extra_keys(
                content,
                _content_known,
                f"{block_id}:{block_type}.content",
                degraded,
            )
        else:
            logger.warning(
                "[MinerU 未知字段] block_id=%s type=%s 无已知字段集合，跳过完整性检查",
                block_id, block_type,
            )

    if block_type == "title":
        level = content.get("level", 1) if isinstance(content, dict) else 1
        title_segs = content.get("title_content", []) if isinstance(content, dict) else []
        text, segments = _flatten_text_segments(title_segs)
        metadata = BlockMetadata(title_level=level)

    elif block_type == "paragraph":
        para_segs = content.get("paragraph_content", []) if isinstance(content, dict) else []
        text, segments = _flatten_text_segments(para_segs)

    elif block_type == "list":
        list_type = content.get("list_type") if isinstance(content, dict) else None
        list_items = content.get("list_items", []) if isinstance(content, dict) else []
        text = _flatten_list(list_items)
        segments = [TextSegment(type="text", content=text)]
        metadata = BlockMetadata(list_type=list_type)

    elif block_type == "code":
        code_segs = content.get("code_content", []) if isinstance(content, dict) else []
        code_lang = content.get("code_language") if isinstance(content, dict) else None
        text, segments = _flatten_text_segments(code_segs)
        metadata = BlockMetadata(code_language=code_lang)

    elif block_type == "equation":
        math_content = content.get("math_content", "") if isinstance(content, dict) else ""
        math_type = content.get("math_type") if isinstance(content, dict) else None
        img_src = _get_image_source_path(content, images_dir)
        text = math_content
        segments = [TextSegment(type="inline_equation", content=math_content)]
        metadata = BlockMetadata(math_content=math_content, math_type=math_type)
        if img_src:
            asset_id = f"asset-{block_id}-eq"
            assets = [Asset(
                asset_id=asset_id,
                asset_type="equation_image",
                path=img_src,
                usage="qa_preferred",
                mime="image/jpeg",
            )]

    elif block_type == "image":
        img_src = _get_image_source_path(content, images_dir)

        if raw_type == "chart":
            # chart: 有图片截图 + 提取的 Markdown 数据 + caption
            caption_segs = content.get("chart_caption", []) if isinstance(content, dict) else []
            caption_text, _ = _flatten_text_segments(caption_segs)
            # content["content"] 是 MinerU 从图表中提取的 Markdown/文本数据
            chart_data = content.get("content", "") if isinstance(content, dict) else ""
            if isinstance(chart_data, str) and chart_data:
                text_parts = [caption_text, chart_data] if caption_text else [chart_data]
            else:
                text_parts = [caption_text] if caption_text else []
            text = "\n".join(text_parts)
        else:
            # 普通 image：caption + 可选 VLM OCR 提取文本
            caption_segs = content.get("image_caption", []) if isinstance(content, dict) else []
            caption_text, _ = _flatten_text_segments(caption_segs)
            # content["content"] 是新版 MinerU 对图片内容的 VLM 识别结果
            ocr_text = content.get("content", "") if isinstance(content, dict) else ""
            if isinstance(ocr_text, str) and ocr_text:
                text = f"{caption_text}\n{ocr_text}".strip() if caption_text else ocr_text
            else:
                text = caption_text

        segments = [TextSegment(type="text", content=text)] if text else []
        if img_src:
            asset_id = f"asset-{block_id}-img"
            asset_type = "chart_image" if raw_type == "chart" else "image"
            assets = [Asset(
                asset_id=asset_id,
                asset_type=asset_type,
                path=img_src,
                usage="primary",
                mime="image/jpeg",
            )]

    elif block_type == "table":
        html = content.get("html", "") if isinstance(content, dict) else ""
        img_src = _get_image_source_path(content, images_dir)
        caption_segs = content.get("table_caption", []) if isinstance(content, dict) else []
        caption_text, _ = _flatten_text_segments(caption_segs)
        text = caption_text
        segments = [TextSegment(type="text", content=caption_text)] if caption_text else []
        table_type = content.get("table_type") if isinstance(content, dict) else None
        metadata = BlockMetadata(table_html=html, table_type=table_type)
        if img_src:
            asset_id = f"asset-{block_id}-tbl"
            assets = [Asset(
                asset_id=asset_id,
                asset_type="table_image",
                path=img_src,
                usage="primary",
                mime="image/jpeg",
            )]

    elif block_type in _AUXILIARY_TYPES:
        # page_header/footer/number/footnote
        # 真实字段是 {block_type}_content (list[TextSegment])，而非简单的 text
        if isinstance(content, dict):
            seg_key = f"{block_type}_content"  # e.g. "page_header_content"
            segs = content.get(seg_key, [])
            if isinstance(segs, list) and segs:
                text, segments = _flatten_text_segments(segs)
            else:
                # 尝试兼容旧版 text 字段
                raw_text = content.get("text", "")
                text = raw_text
                segments = [TextSegment(type="text", content=raw_text)] if raw_text else []
        elif isinstance(content, str):
            text = content
            segments = [TextSegment(type="text", content=content)] if content else []
        else:
            text = ""
            segments = []

    return text, segments, assets, metadata


def _flatten_text_segments(segs: list) -> tuple[str, list[TextSegment]]:
    """将 [{type, content}, ...] 转为 text 字符串 + TextSegment 列表。

    支持的 segment 类型：
    - text: 普通文本
    - inline_equation/equation_inline: 行内公式
    - hyperlink: 超链接（取 content 文本，忽略 url 用于嵌入）
    """
    ir_segs: list[TextSegment] = []
    parts: list[str] = []
    for s in segs:
        if not isinstance(s, dict):
            continue
        _warn_extra_keys(s, _KNOWN_TEXT_SEGMENT_KEYS, "text_segment")
        seg_type = s.get("type", "text")
        seg_content = s.get("content", "")
        # 新版 MinerU 的 hyperlink 可能把显示文本拆进 children；content 为空时递归兜底，避免丢文本
        if not seg_content and isinstance(s.get("children"), list):
            seg_content, _ = _flatten_text_segments(s["children"])
        if "equation" in seg_type:
            seg_t = "inline_equation"
        else:
            seg_t = "text"  # hyperlink 和其他类型都归为 text
        ir_segs.append(TextSegment(type=seg_t, content=seg_content))
        parts.append(seg_content)
    return "".join(parts), ir_segs


def _flatten_list(list_items: list) -> str:
    """将 list_items 展平为纯文本。

    支持新版字段：ilevel（缩进）、prefix（前缀符号）、anchor（锚点，忽略）。
    使用 ilevel 控制缩进，prefix 用于显示列表符号。
    """
    lines: list[str] = []
    for item in list_items:
        if not isinstance(item, dict):
            continue
        _warn_extra_keys(item, _KNOWN_LIST_ITEM_KEYS, "list_item")
        item_content = item.get("item_content", [])
        text, _ = _flatten_text_segments(item_content)
        if text:
            # 使用 ilevel 缩进（每级 2 空格），prefix 作为项目符号前缀
            ilevel = item.get("ilevel", 0) or 0
            prefix = item.get("prefix", "")
            indent = "  " * max(0, ilevel)
            if prefix:
                lines.append(f"{indent}{prefix} {text}")
            else:
                lines.append(f"{indent}{text}")
    return "\n".join(lines)


def _get_image_source_path(content: Any, images_dir: str | None) -> str | None:
    """从 content 中提取 image_source.path，拼接 images_dir 返回绝对路径或相对路径"""
    if not isinstance(content, dict):
        return None
    img_source = content.get("image_source")
    if not img_source or not isinstance(img_source, dict):
        return None
    _warn_extra_keys(img_source, _KNOWN_IMAGE_SOURCE_KEYS, "image_source")
    rel_path: str = img_source.get("path", "")
    if not rel_path:
        return None
    if images_dir:
        abs_path = Path(images_dir).parent / rel_path
        return str(abs_path)
    return rel_path


# ═══════════════════════════════════════════════════════════
# 坐标处理
# ═══════════════════════════════════════════════════════════

def _safe_bbox_norm1000(
    bbox: list,
    degraded: list[str],
    ctx: str,
) -> BboxNorm1000:
    """将 content_list_v2 的 bbox（已是 norm1000）包装为 BboxNorm1000"""
    if len(bbox) >= 4:
        coords = [float(c) for c in bbox[:4]]
    else:
        logger.warning("bbox 长度异常 ctx=%s bbox=%s，使用 [0,0,0,0]", ctx, bbox)
        degraded.append(f"bad_bbox_{ctx}")
        coords = [0.0, 0.0, 0.0, 0.0]
    return BboxNorm1000(coords=coords)


def _compute_bbox_page(
    bbox_norm: list,
    page_width: float,
    page_height: float,
) -> BboxPage | None:
    """从 norm1000 bbox 反算绝对坐标（content_list_v2 坐标已是 norm1000）"""
    if len(bbox_norm) < 4:
        return None
    x0, y0, x1, y1 = [float(c) for c in bbox_norm[:4]]
    return BboxPage(coords=[
        x0 / 1000 * page_width,
        y0 / 1000 * page_height,
        x1 / 1000 * page_width,
        y1 / 1000 * page_height,
    ])


# ═══════════════════════════════════════════════════════════
# 页面辅助块填充
# ═══════════════════════════════════════════════════════════

def _append_auxiliary(ir_page: IRPage, block: IRBlock) -> None:
    btype = block.type
    aux = ir_page.auxiliary
    item_text = block.text

    if btype == "page_header":
        from app.models.models_ir import AuxiliaryItem
        aux.page_headers.append(AuxiliaryItem(text=item_text, block_id=block.block_id))
    elif btype == "page_footer":
        from app.models.models_ir import AuxiliaryItem
        aux.page_footers.append(AuxiliaryItem(text=item_text, block_id=block.block_id))
    elif btype == "page_number":
        from app.models.models_ir import AuxiliaryItem
        aux.page_numbers.append(AuxiliaryItem(text=item_text, block_id=block.block_id))
    elif btype == "page_footnote":
        ir_page.footnotes.append(PageFootnote(block_id=block.block_id, text=item_text))


# ═══════════════════════════════════════════════════════════
# 工具：读取 JSON
# ═══════════════════════════════════════════════════════════

def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_page_sizes(layout_path: str, degraded: list[str]) -> dict[int, tuple[float, float]]:
    """从 layout.json 提取每页的 page_size，返回 {page_idx: (width, height)}"""
    sizes: dict[int, tuple[float, float]] = {}
    try:
        data = _load_json(layout_path)
        pdf_info = data.get("pdf_info", []) if isinstance(data, dict) else []
        for page in pdf_info:
            if not isinstance(page, dict):
                continue
            idx = page.get("page_idx", 0)
            ps = page.get("page_size", [])
            if len(ps) >= 2:
                sizes[idx] = (float(ps[0]), float(ps[1]))
    except Exception as e:
        logger.warning("读取 layout.json 失败，使用默认 page_size: %s", e)
        degraded.append("layout_load_failed")
    return sizes
