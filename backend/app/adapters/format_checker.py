"""
MinerU 输出格式严格校验模块（Format Checker）

职责
----
与 normalizer.py 的"宽松容错"完全相反：
本模块采用严格审计策略——任何字段与预期格式不一致，均记录为偏差项（Deviation）。
目的不是让流水线继续运行，而是发现 MinerU API 格式变化，通知运维人员针对性修复
解析逻辑和格式推断文档。

使用场景
--------
1. 独立探针脚本（tools/mineru_format_probe.py）定期检测
2. 流水线集成：每次正式文件解析后自动追加到 data/format_probe_log.jsonl

设计原则
--------
- 额外字段 → WARNING（API 可能新增字段）
- 未知块类型 → ERROR（新增块类型，解析逻辑需更新）
- 缺少必要字段 → WARNING（API 可能删除或重命名字段）
- 字段类型不符 → WARNING（API 可能变更字段结构）
- ZIP 中出现未知文件 → INFO（不影响解析，但需跟踪）

"已知格式规范"来源：
  doc/在线API输出文件格式（SaaS推断版）.md 第 9 节（2026-05-21 更新）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 已知格式规范（Single Source of Truth）
# 更新此处 = 更新格式推断文档，两者必须保持同步
# ═══════════════════════════════════════════════════════════════════════════

# ── ZIP 包文件结构 ──────────────────────────────────────────────────────────

# 必须存在（至少一个）
ZIP_REQUIRED_FILES = [
    "content_list_v2.json",          # 旧格式（固定名）
    "_content_list_v2.json",         # 新格式（UUID 前缀，endswith 检测）
]

# 可选但预期的文件（出现或不出现都正常）
ZIP_OPTIONAL_PATTERNS = [
    "layout.json",                   # 坐标信息
    "full.md",                       # 全文 Markdown（摘要用）
    "_content_list.json",            # 兼容旧格式
    "_model.json",                   # MinerU 内部模型信息
    "_origin.pdf",                   # PDF 原文（PDF 源文件）
    "_origin.docx",                  # DOCX 原文
    "_origin.pptx",                  # PPTX 原文
    "_origin.doc",
    "_origin.ppt",
    "_origin.png",
    "_origin.jpg",
    "_origin.jpeg",
    "_origin.xlsx",                  # Excel 原文（新版 MinerU 支持表格文件，2026-05）
    "_origin.xls",
    "images/",                       # 图片资源目录
]

# ── content_list_v2.json 块类型 ───────────────────────────────────────────

KNOWN_BLOCK_TYPES: frozenset[str] = frozenset({
    # 核心内容类型
    "title",
    "paragraph",
    "list",
    "image",
    "table",
    "equation_interline",
    "code",
    # 辅助块
    "page_header",
    "page_footer",
    "page_number",
    "page_footnote",
    # 新版 MinerU（2026-05-21 实测）
    "chart",        # 图表（含截图 + 提取数据）
    "index",        # 目录/TOC
})

# ── 块顶级字段 ──────────────────────────────────────────────────────────────

BLOCK_REQUIRED_FIELDS: frozenset[str] = frozenset({"type"})

BLOCK_OPTIONAL_FIELDS: frozenset[str] = frozenset({
    "bbox",         # norm1000 坐标；Office 原生解析时不存在（键缺失，非 null）
    "content",      # 块内容
    "anchor",       # 文档锚点（DOCX 标题/段落）
    "sub_type",     # 块子类型（chart 的图表类型等）
})

BLOCK_KNOWN_FIELDS: frozenset[str] = BLOCK_REQUIRED_FIELDS | BLOCK_OPTIONAL_FIELDS

# ── 各块类型的 content 字段 ────────────────────────────────────────────────

CONTENT_KNOWN_FIELDS: dict[str, frozenset[str]] = {
    "title": frozenset({"level", "title_content"}),
    "paragraph": frozenset({"paragraph_content"}),
    "list": frozenset({"list_type", "list_items", "attribute"}),
    "code": frozenset({"code_content", "code_language", "code_caption"}),
    "equation_interline": frozenset({"math_content", "math_type", "image_source"}),
    "image": frozenset({
        "image_source", "image_caption", "image_footnote",
        "content",      # VLM OCR 识别文本（新版）
    }),
    "table": frozenset({
        "html", "image_source", "table_caption", "table_footnote",
        "table_nest_level", "table_type",
    }),
    # 新块类型（2026-05-21）
    "chart": frozenset({
        "image_source", "content", "chart_caption", "chart_footnote",
    }),
    "index": frozenset({"list_type", "list_items", "attribute"}),
    # 辅助块
    "page_header": frozenset({"page_header_content"}),
    "page_footer": frozenset({"page_footer_content"}),
    "page_number": frozenset({"page_number_content"}),
    "page_footnote": frozenset({"page_footnote_content"}),
}

# ── 文本段（TextSegment）─────────────────────────────────────────────────

TEXT_SEGMENT_KNOWN_FIELDS: frozenset[str] = frozenset({
    "type", "content",
    "url",       # hyperlink 类型
    "style",     # Office 原生解析字体标记
    "children",  # hyperlink 显示文本拆分出的嵌套子文本段（新版 MinerU 2026-05）
})

KNOWN_TEXT_SEGMENT_TYPES: frozenset[str] = frozenset({
    "text",
    "inline_equation",
    "equation_inline",  # 旧版可能有
    "hyperlink",        # 新版
})

# ── 列表项（ListItem）────────────────────────────────────────────────────

LIST_ITEM_KNOWN_FIELDS: frozenset[str] = frozenset({
    "item_type", "item_content",
    "ilevel",   # 缩进层级（新版）
    "prefix",   # 项目符号前缀（新版）
    "anchor",   # 锚点（新版，TOC 条目）
})

# ── image_source 字段 ────────────────────────────────────────────────────

IMAGE_SOURCE_KNOWN_FIELDS: frozenset[str] = frozenset({"path"})

# ── layout.json 顶级字段 ─────────────────────────────────────────────────

LAYOUT_KNOWN_TOP_FIELDS: frozenset[str] = frozenset({
    "pdf_info",
    "_backend", "_ocr_enable", "_vlm_ocr_enable", "_version_name",
})

LAYOUT_PAGE_KNOWN_FIELDS: frozenset[str] = frozenset({
    "para_blocks", "discarded_blocks", "page_size", "page_idx",
    "preproc_blocks",   # MinerU 内部预处理块（稳定出现，2026-05-21 实测确认）
})


# ═══════════════════════════════════════════════════════════════════════════
# 偏差记录结构
# ═══════════════════════════════════════════════════════════════════════════

DeviationSeverity = Literal["error", "warning", "info"]


@dataclass
class Deviation:
    """单条格式偏差记录"""
    severity: DeviationSeverity
    location: str        # 定位路径，如 "content_list_v2[p2][b3].content"
    issue: str           # 人类可读的问题描述
    detail: str = ""     # 额外细节（实际值等）

    def __str__(self) -> str:
        tag = {"error": "❌ ERROR", "warning": "⚠  WARN ", "info": "ℹ  INFO "}[self.severity]
        detail = f" → {self.detail}" if self.detail else ""
        return f"{tag}  [{self.location}]  {self.issue}{detail}"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "location": self.location,
            "issue": self.issue,
            "detail": self.detail,
        }


@dataclass
class FormatCheckReport:
    """单次 ZIP 包严格格式校验报告"""
    source_filename: str           # 用户上传的文件名
    doc_id: str                    # 文档 ID
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deviations: list[Deviation] = field(default_factory=list)

    # 统计数据
    page_count: int = 0
    block_count: int = 0
    block_type_counts: dict[str, int] = field(default_factory=dict)
    zip_files_found: list[str] = field(default_factory=list)
    zip_files_unexpected: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.deviations if d.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.deviations if d.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for d in self.deviations if d.severity == "info")

    @property
    def is_clean(self) -> bool:
        """无任何偏差（info 也算）"""
        return len(self.deviations) == 0

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def add(self, severity: DeviationSeverity, location: str, issue: str, detail: str = "") -> None:
        self.deviations.append(Deviation(severity=severity, location=location, issue=issue, detail=detail))

    def to_dict(self) -> dict:
        return {
            "source_filename": self.source_filename,
            "doc_id": self.doc_id,
            "checked_at": self.checked_at,
            "is_clean": self.is_clean,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "page_count": self.page_count,
            "block_count": self.block_count,
            "block_type_counts": self.block_type_counts,
            "zip_files_found": self.zip_files_found,
            "zip_files_unexpected": self.zip_files_unexpected,
            "deviations": [d.to_dict() for d in self.deviations],
        }

    def to_text_report(self) -> str:
        """生成人类可读的文本报告"""
        lines: list[str] = []
        lines.append("=" * 70)
        lines.append(f"MinerU 输出格式校验报告")
        lines.append(f"  文件: {self.source_filename}  (doc_id: {self.doc_id[:8]}...)")
        lines.append(f"  时间: {self.checked_at}")
        lines.append(f"  统计: {self.page_count} 页, {self.block_count} 块")
        lines.append(f"  块类型分布: {dict(sorted(self.block_type_counts.items()))}")
        lines.append("=" * 70)

        if self.is_clean:
            lines.append("✅ 格式完全符合预期，无任何偏差。")
        else:
            lines.append(f"发现偏差: {self.error_count} 个错误, "
                         f"{self.warning_count} 个警告, {self.info_count} 个提示")
            lines.append("")
            # 按严重程度分组
            for sev in ("error", "warning", "info"):
                items = [d for d in self.deviations if d.severity == sev]
                if items:
                    label = {"error": "❌ 错误（需立即修复解析逻辑）",
                             "warning": "⚠  警告（API 格式可能已更新）",
                             "info": "ℹ  提示（非预期但不影响运行）"}[sev]
                    lines.append(f"── {label} ({len(items)} 条) ──")
                    for item in items:
                        lines.append(f"  {item}")
                    lines.append("")

        if self.zip_files_unexpected:
            lines.append("ZIP 中存在未预期文件（可能是新版 MinerU 输出）:")
            for f in self.zip_files_unexpected:
                lines.append(f"  • {f}")
        lines.append("=" * 70)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# 核心校验函数
# ═══════════════════════════════════════════════════════════════════════════

def check_bundle(
    zip_root: Path,
    source_filename: str,
    doc_id: str,
) -> FormatCheckReport:
    """
    对已解压的 MinerU ZIP 包目录做严格格式校验。

    Args:
        zip_root:        解压后的根目录（bundle_parser.extract_zip 的返回值）
        source_filename: 原始上传文件名（用于报告）
        doc_id:          文档 ID（用于报告定位）

    Returns:
        FormatCheckReport，包含所有偏差记录。
    """
    report = FormatCheckReport(source_filename=source_filename, doc_id=doc_id)

    # ── 1. 校验 ZIP 文件结构 ────────────────────────────────────────────
    _check_zip_structure(zip_root, report)

    # ── 2. 校验 content_list_v2.json ────────────────────────────────────
    clv2_path = _find_content_list_v2(zip_root)
    if clv2_path is None:
        report.add("error", "zip_structure",
                   "content_list_v2.json 不存在（固定名和 UUID 前缀均未找到）",
                   "这是 MinerU 最核心的输出文件，缺失表示格式发生重大变化")
    else:
        try:
            raw_data = json.loads(clv2_path.read_text(encoding="utf-8"))
            _check_content_list_v2(raw_data, report)
        except json.JSONDecodeError as e:
            report.add("error", "content_list_v2", "JSON 解析失败", str(e))

    # ── 3. 校验 layout.json（可选）──────────────────────────────────────
    layout_path = zip_root / "layout.json"
    if layout_path.exists():
        try:
            layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
            _check_layout_json(layout_data, report)
        except json.JSONDecodeError as e:
            report.add("error", "layout.json", "JSON 解析失败", str(e))
    else:
        report.add("info", "layout.json", "layout.json 不存在（部分文件类型可能不提供此文件）")

    return report


def _find_content_list_v2(zip_root: Path) -> Path | None:
    """找 content_list_v2.json（兼容固定名和 UUID 前缀两种格式）"""
    fixed = zip_root / "content_list_v2.json"
    if fixed.exists():
        return fixed
    for f in zip_root.iterdir():
        if f.name.endswith("_content_list_v2.json"):
            return f
    return None


def _check_zip_structure(zip_root: Path, report: FormatCheckReport) -> None:
    """校验 ZIP 解压目录的文件结构"""
    all_entries = list(zip_root.iterdir())
    report.zip_files_found = [e.name for e in all_entries]

    # 检查每个文件是否符合预期
    for entry in all_entries:
        name = entry.name.lower()
        is_known = (
            name == "content_list_v2.json"
            or name.endswith("_content_list_v2.json")
            or name == "layout.json"
            or name == "full.md"
            or name.endswith("_content_list.json")
            or name.endswith("_model.json")
            or (name.endswith((".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"))
                and "_origin." in name)
            or (entry.is_dir() and name == "images")
        )
        if not is_known:
            report.zip_files_unexpected.append(entry.name)
            report.add(
                "warning",
                "zip_structure",
                f"出现未预期文件/目录: {entry.name!r}",
                "可能是新版 MinerU 新增的输出文件，需要检查是否含有重要信息",
            )


def _check_content_list_v2(raw_data: Any, report: FormatCheckReport) -> None:
    """严格校验 content_list_v2.json 的完整结构"""

    # 顶层必须是列表（页面数组）
    if not isinstance(raw_data, list):
        report.add("error", "content_list_v2",
                   f"顶层结构应为 list，实际为 {type(raw_data).__name__}")
        return

    report.page_count = len(raw_data)

    for page_idx, page in enumerate(raw_data):
        loc_page = f"content_list_v2[p{page_idx}]"

        if not isinstance(page, list):
            report.add("error", loc_page,
                       f"页面数据应为 list，实际为 {type(page).__name__}")
            continue

        for block_idx, block in enumerate(page):
            report.block_count += 1
            loc_block = f"content_list_v2[p{page_idx}][b{block_idx}]"
            _check_block(block, loc_block, page_idx, block_idx, report)


def _check_block(
    block: Any,
    loc: str,
    page_idx: int,
    block_idx: int,
    report: FormatCheckReport,
) -> None:
    """严格校验单个 content_list_v2 块"""
    if not isinstance(block, dict):
        report.add("error", loc, f"块应为 dict，实际为 {type(block).__name__}")
        return

    # ── 必须字段 ────────────────────────────────────────────────────────
    for req in BLOCK_REQUIRED_FIELDS:
        if req not in block:
            report.add("warning", loc, f"缺少必要字段 '{req}'")

    # ── 未知顶级字段 ─────────────────────────────────────────────────────
    extra_keys = set(block.keys()) - BLOCK_KNOWN_FIELDS
    if extra_keys:
        report.add(
            "warning", loc,
            f"出现未知顶级字段: {sorted(extra_keys)}",
            "需更新 BLOCK_OPTIONAL_FIELDS 或修改格式推断文档",
        )

    # ── 块类型 ───────────────────────────────────────────────────────────
    raw_type: str = block.get("type", "")
    if not raw_type:
        report.add("error", loc, "块缺少 'type' 字段或 type 为空字符串")
        return

    if raw_type not in KNOWN_BLOCK_TYPES:
        report.add(
            "error", loc,
            f"出现未知块类型: {raw_type!r}",
            f"需将 {raw_type!r} 加入 KNOWN_BLOCK_TYPES 并更新 normalizer._V2_TYPE_MAP",
        )
        # 块类型未知时仍继续检查其他字段（收集更多信息）

    # 统计块类型分布
    report.block_type_counts[raw_type] = report.block_type_counts.get(raw_type, 0) + 1

    # ── bbox 字段 ────────────────────────────────────────────────────────
    if "bbox" in block:
        bbox = block["bbox"]
        if bbox is None:
            # null bbox：允许，但值得记录（目前预期键缺失而非 null）
            report.add(
                "info", f"{loc}.bbox",
                "bbox 字段值为 null（预期：键缺失表示 Office 原生解析，null 是另一种形式）",
            )
        elif not isinstance(bbox, list):
            report.add("warning", f"{loc}.bbox",
                       f"bbox 应为 list，实际为 {type(bbox).__name__}", repr(bbox))
        elif len(bbox) != 4:
            report.add("warning", f"{loc}.bbox",
                       f"bbox 长度应为 4，实际为 {len(bbox)}", repr(bbox))
        else:
            # 检查坐标范围（norm1000 体系：0-1000）
            for i, c in enumerate(bbox):
                if not isinstance(c, (int, float)):
                    report.add("warning", f"{loc}.bbox[{i}]",
                               f"坐标应为数字，实际为 {type(c).__name__}")
                elif not (-50 <= c <= 1050):
                    report.add("warning", f"{loc}.bbox",
                               f"坐标值 {c} 超出 norm1000 合理范围 [-50, 1050]")

    # ── content 字段 ──────────────────────────────────────────────────────
    content = block.get("content")
    if content is None and "content" not in block:
        # content 键完全缺失（不同于 content=null）
        if raw_type not in ("page_header", "page_footer", "page_number", "page_footnote"):
            # 辅助块有时可能没有 content，其他类型通常需要
            report.add("info", loc, "content 键缺失（对非辅助块来说较少见）")
    elif content is not None:
        _check_block_content(content, raw_type, f"{loc}.content", report)


def _check_block_content(
    content: Any,
    raw_type: str,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """校验块的 content 对象"""
    if not isinstance(content, dict):
        report.add("warning", loc,
                   f"content 应为 dict，实际为 {type(content).__name__}",
                   repr(content)[:100])
        return

    # 获取当前类型的已知字段集
    known_fields = CONTENT_KNOWN_FIELDS.get(raw_type)
    if known_fields is None:
        # 未知块类型的 content，只记录字段名，不做进一步校验
        report.add("info", loc,
                   f"未知块类型 {raw_type!r} 的 content 字段: {sorted(content.keys())}")
        return

    # 未知字段
    extra = set(content.keys()) - known_fields
    if extra:
        report.add(
            "warning", loc,
            f"出现未知 content 字段: {sorted(extra)}",
            f"（当前类型 {raw_type!r} 的已知字段: {sorted(known_fields)}）",
        )

    # 缺少预期的核心字段（按类型检查）
    _check_missing_core_content_fields(content, raw_type, loc, report)

    # 深层递归校验
    _check_content_sub_fields(content, raw_type, loc, report)


def _check_missing_core_content_fields(
    content: dict,
    raw_type: str,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """检查 content 中缺少的核心字段（可能是 MinerU 删除了某个字段）"""
    core_required: dict[str, list[str]] = {
        "title":              ["title_content"],
        "paragraph":          ["paragraph_content"],
        "list":               ["list_items"],
        "index":              ["list_items"],
        "image":              ["image_source"],
        "table":              ["html"],
        "equation_interline": ["math_content"],
        "code":               ["code_content"],
        "chart":              ["image_source"],
    }
    for field_name in core_required.get(raw_type, []):
        if field_name not in content:
            report.add(
                "warning", loc,
                f"缺少预期核心字段 '{field_name}'（{raw_type} 块通常必有此字段）",
            )


def _check_content_sub_fields(
    content: dict,
    raw_type: str,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """递归校验 content 内部的嵌套字段"""

    # ── title_content / paragraph_content / caption 等（TextSegment 列表）──
    seg_list_keys = {
        "title_content", "paragraph_content",
        "image_caption", "image_footnote",
        "table_caption", "table_footnote",
        "chart_caption", "chart_footnote",
        "page_header_content", "page_footer_content",
        "page_number_content", "page_footnote_content",
        "code_caption",
        "code_content",
    }
    for key in seg_list_keys:
        val = content.get(key)
        if val is not None:
            _check_text_segment_list(val, f"{loc}.{key}", report)

    # ── list_items（ListItem 列表）─────────────────────────────────────
    list_items = content.get("list_items")
    if list_items is not None:
        _check_list_items(list_items, f"{loc}.list_items", report)

    # ── image_source ──────────────────────────────────────────────────
    img_src = content.get("image_source")
    if img_src is not None:
        _check_image_source(img_src, f"{loc}.image_source", report)

    # ── title.level ───────────────────────────────────────────────────
    if raw_type == "title":
        level = content.get("level")
        if level is not None and not isinstance(level, int):
            report.add("warning", f"{loc}.level",
                       f"title.level 应为 int，实际为 {type(level).__name__}",
                       repr(level))
        elif level is not None and level != 1:
            report.add(
                "warning", f"{loc}.level",
                f"title.level 语义漂移：预期始终为 1（当前 MinerU 版本不做层级检测），"
                f"实际为 {level}",
                "MinerU 可能已启用标题层级识别——需更新推断文档、"
                "重新评估 doc_tree_service LLM 重建策略是否仍然必要",
            )

    # ── chart.content（提取数据，字符串）─────────────────────────────
    if raw_type == "chart":
        chart_data = content.get("content")
        if chart_data is not None and not isinstance(chart_data, str):
            report.add("warning", f"{loc}.content",
                       f"chart.content 应为 str（Markdown 数据），实际为 {type(chart_data).__name__}")

    # ── image.content（VLM OCR 文本）────────────────────────────────
    if raw_type == "image":
        ocr_text = content.get("content")
        if ocr_text is not None and not isinstance(ocr_text, str):
            report.add("warning", f"{loc}.content",
                       f"image.content 应为 str（VLM OCR 文本），实际为 {type(ocr_text).__name__}")

    # ── 语义值校验（字段存在 + 值在预期范围内）──────────────────────
    _check_semantic_values(content, raw_type, loc, report)


def _check_semantic_values(
    content: dict,
    raw_type: str,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """检查字段的**实际值**是否与当前 MinerU 版本的推断格式一致。

    与字段存在性检查不同：这里关注已知字段的值是否发生了语义漂移。
    例如 title.level 当前始终为 1、list.attribute 应为 "ordered"/"unordered" 等。
    任何与推断文档不符的值都应告警，提示更新格式文档和解析代码。
    """

    # ── list: attribute / list_type ───────────────────────────────
    if raw_type in ("list", "index"):
        attr = content.get("attribute")
        if attr is not None and attr not in ("ordered", "unordered"):
            report.add(
                "warning", f"{loc}.attribute",
                f"list.attribute 语义漂移：预期 'ordered' 或 'unordered'，实际为 {attr!r}",
                "MinerU 可能新增了列表样式类型，需更新推断文档",
            )
        lt = content.get("list_type")
        if lt is not None and lt not in ("ordered", "unordered"):
            report.add(
                "warning", f"{loc}.list_type",
                f"list.list_type 语义漂移：预期 'ordered' 或 'unordered'，实际为 {lt!r}",
            )

    # ── table: table_type ────────────────────────────────────────
    if raw_type == "table":
        tt = content.get("table_type")
        if tt is not None and tt not in ("", "simple", "complex", "normal"):
            report.add(
                "warning", f"{loc}.table_type",
                f"table.table_type 语义漂移：已知值 ('simple'|'complex'|'normal'|'')，实际为 {tt!r}",
                "MinerU 可能新增表格分类，需更新推断文档",
            )

    # ── code: code_language ──────────────────────────────────────
    if raw_type == "code":
        lang = content.get("code_language")
        if lang is not None and not isinstance(lang, str):
            report.add("warning", f"{loc}.code_language",
                       f"code.code_language 应为 str 或 null，实际为 {type(lang).__name__}")

    # ── equation_interline: math_type ────────────────────────────
    if raw_type == "equation_interline":
        mt = content.get("math_type")
        if mt is not None and mt not in ("latex", "mathml", "asciimath", ""):
            report.add(
                "warning", f"{loc}.math_type",
                f"equation.math_type 语义漂移：已知值 ('latex'|'mathml'|'asciimath')，实际为 {mt!r}",
            )

    # ── image: image_source 路径格式 ──────────────────────────────
    if raw_type == "image":
        img_src = content.get("image_source")
        if isinstance(img_src, dict):
            path_val = img_src.get("path", "")
            if isinstance(path_val, str) and path_val and not path_val.startswith("images/"):
                report.add(
                    "info", f"{loc}.image_source.path",
                    f"image_source.path 路径格式变化：预期以 'images/' 开头，实际为 {path_val!r}",
                    "MinerU 可能改变了图片资源目录结构，需检查 assets 拼接逻辑",
                )

    # ── chart: image_source 路径格式 ─────────────────────────────
    if raw_type == "chart":
        img_src = content.get("image_source")
        if isinstance(img_src, dict):
            path_val = img_src.get("path", "")
            if isinstance(path_val, str) and path_val and not path_val.startswith("images/"):
                report.add(
                    "info", f"{loc}.image_source.path",
                    f"image_source.path 路径格式变化：预期以 'images/' 开头，实际为 {path_val!r}",
                )

def _check_text_segment_list(
    segs: Any,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """校验 TextSegment 列表"""
    if not isinstance(segs, list):
        report.add("warning", loc,
                   f"TextSegment 列表应为 list，实际为 {type(segs).__name__}")
        return

    for i, seg in enumerate(segs):
        seg_loc = f"{loc}[{i}]"
        if not isinstance(seg, dict):
            report.add("warning", seg_loc,
                       f"TextSegment 应为 dict，实际为 {type(seg).__name__}")
            continue

        # 未知字段
        extra = set(seg.keys()) - TEXT_SEGMENT_KNOWN_FIELDS
        if extra:
            report.add("warning", seg_loc,
                       f"TextSegment 出现未知字段: {sorted(extra)}")

        # type 字段
        seg_type = seg.get("type")
        if seg_type is not None and seg_type not in KNOWN_TEXT_SEGMENT_TYPES:
            report.add(
                "warning", f"{seg_loc}.type",
                f"未知 TextSegment 类型: {seg_type!r}",
                f"已知类型: {sorted(KNOWN_TEXT_SEGMENT_TYPES)}",
            )

        # content 字段
        seg_content = seg.get("content")
        if seg_content is not None and not isinstance(seg_content, str):
            report.add("warning", f"{seg_loc}.content",
                       f"TextSegment.content 应为 str，实际为 {type(seg_content).__name__}")

        # url 字段（hyperlink 类型附带的 URL）
        seg_url = seg.get("url")
        if seg_url is not None and not isinstance(seg_url, str):
            report.add("warning", f"{seg_loc}.url",
                       f"TextSegment.url 应为 str，实际为 {type(seg_url).__name__}")

        # style 字段（Office 字体/样式标记）
        seg_style = seg.get("style")
        if seg_style is not None and not isinstance(seg_style, str):
            report.add("warning", f"{seg_loc}.style",
                       f"TextSegment.style 应为 str，实际为 {type(seg_style).__name__}")

        # children 字段（hyperlink 嵌套子文本段）
        seg_children = seg.get("children")
        if seg_children is not None:
            if not isinstance(seg_children, list):
                report.add("warning", f"{seg_loc}.children",
                           f"TextSegment.children 应为 list，实际为 {type(seg_children).__name__}")
            else:
                _check_text_segment_list(seg_children, f"{seg_loc}.children", report)


def _check_list_items(
    items: Any,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """校验 ListItem 列表"""
    if not isinstance(items, list):
        report.add("warning", loc,
                   f"list_items 应为 list，实际为 {type(items).__name__}")
        return

    for i, item in enumerate(items):
        item_loc = f"{loc}[{i}]"
        if not isinstance(item, dict):
            report.add("warning", item_loc,
                       f"ListItem 应为 dict，实际为 {type(item).__name__}")
            continue

        extra = set(item.keys()) - LIST_ITEM_KNOWN_FIELDS
        if extra:
            report.add("warning", item_loc,
                       f"ListItem 出现未知字段: {sorted(extra)}")

        # 校验 item_content
        item_content = item.get("item_content")
        if item_content is not None:
            _check_text_segment_list(item_content, f"{item_loc}.item_content", report)

        # ilevel 应为 int 且 ≥ 0
        ilevel = item.get("ilevel")
        if ilevel is not None:
            if not isinstance(ilevel, int):
                report.add("warning", f"{item_loc}.ilevel",
                           f"ilevel 应为 int，实际为 {type(ilevel).__name__}")
            elif ilevel < 0:
                report.add("warning", f"{item_loc}.ilevel",
                           f"ilevel 语义漂移：预期 ≥0，实际为 {ilevel}",
                           "缩进层级不应为负数，MinerU 可能变更了数据结构")
            elif ilevel > 10:
                report.add("info", f"{item_loc}.ilevel",
                           f"ilevel 值较大: {ilevel}（正常范围 0-5，超过 10 需确认是否是 MinerU 格式变更）")

        # prefix 应为 str
        prefix = item.get("prefix")
        if prefix is not None and not isinstance(prefix, str):
            report.add("warning", f"{item_loc}.prefix",
                       f"prefix 应为 str，实际为 {type(prefix).__name__}")


def _check_image_source(
    img_src: Any,
    loc: str,
    report: FormatCheckReport,
) -> None:
    """校验 image_source 对象"""
    if not isinstance(img_src, dict):
        report.add("warning", loc,
                   f"image_source 应为 dict，实际为 {type(img_src).__name__}")
        return

    extra = set(img_src.keys()) - IMAGE_SOURCE_KNOWN_FIELDS
    if extra:
        report.add("warning", loc,
                   f"image_source 出现未知字段: {sorted(extra)}")

    path = img_src.get("path")
    if path is None:
        report.add("warning", f"{loc}.path", "image_source 缺少 'path' 字段")
    elif not isinstance(path, str):
        report.add("warning", f"{loc}.path",
                   f"image_source.path 应为 str，实际为 {type(path).__name__}")


def _check_layout_json(
    layout_data: Any,
    report: FormatCheckReport,
) -> None:
    """校验 layout.json 顶层结构"""
    if not isinstance(layout_data, dict):
        report.add("error", "layout.json",
                   f"顶层结构应为 dict，实际为 {type(layout_data).__name__}")
        return

    extra = set(layout_data.keys()) - LAYOUT_KNOWN_TOP_FIELDS
    if extra:
        report.add("warning", "layout.json",
                   f"出现未知顶级字段: {sorted(extra)}")

    pdf_info = layout_data.get("pdf_info")
    if pdf_info is None:
        report.add("warning", "layout.json", "缺少 'pdf_info' 字段")
    elif not isinstance(pdf_info, list):
        report.add("warning", "layout.json.pdf_info",
                   f"pdf_info 应为 list，实际为 {type(pdf_info).__name__}")
    else:
        for i, page in enumerate(pdf_info[:3]):  # 只检前 3 页，避免过多输出
            if not isinstance(page, dict):
                continue
            extra_page = set(page.keys()) - LAYOUT_PAGE_KNOWN_FIELDS
            if extra_page:
                report.add("info", f"layout.json.pdf_info[{i}]",
                           f"页面出现未知字段: {sorted(extra_page)}")


# ═══════════════════════════════════════════════════════════════════════════
# 快捷工具函数
# ═══════════════════════════════════════════════════════════════════════════

def log_report_to_file(report: FormatCheckReport, log_path: Path) -> None:
    """
    将格式校验报告以 JSON Lines 格式追加到日志文件。

    用于流水线集成：每次解析后追加，运维人员可定期检查。
    只有存在偏差时才写入（clean 的不写，避免日志膨胀）。
    """
    if report.is_clean:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(report.to_dict(), ensure_ascii=False))
        f.write("\n")


def summarize_report(report: FormatCheckReport) -> str:
    """
    生成单行摘要，用于嵌入文档 warnings 字段。
    格式：'[format_probe] 2e, 3w, 1i: 发现未知块类型chart; ...'
    """
    if report.is_clean:
        return ""

    # 取前 3 条错误/警告的简短描述
    top_issues = [
        f"{d.issue[:60]}"
        for d in report.deviations
        if d.severity in ("error", "warning")
    ][:3]
    summary_text = "; ".join(top_issues)
    return (
        f"[format_probe] {report.error_count}e/{report.warning_count}w/{report.info_count}i: "
        f"{summary_text}"
    )
