"""
原始 MinerU SaaS 输出的 Pydantic 宽松模型（第一层：宽进）

设计原则：
- 允许未知字段存在（model_config extra="allow"）
- 对可选字段保持兼容
- 目标是应对 MinerU 的小版本波动
- 不在此层做业务逻辑校验

覆盖文件：
- content_list_v2.json  （主输入）
- layout.json           （坐标 & 结构补充）
- *_content_list.json   （兼容回退）
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

_raw_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 公共基础
# ═══════════════════════════════════════════════════════════

class _RawBase(BaseModel):
    """所有原始模型的基类：允许额外字段，但发现未知字段时输出 WARNING。"""

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _warn_extra_fields(self) -> "_RawBase":
        extra = self.model_extra
        if extra:
            _raw_logger.warning(
                "[MinerU 未知字段] %s 出现 %d 个未知字段: %s"
                " — 源数据格式可能已更新，请更新模型定义以避免信息丢失",
                self.__class__.__name__,
                len(extra),
                sorted(extra.keys()),
            )
        return self


# ═══════════════════════════════════════════════════════════
# content_list_v2.json 模型
# ═══════════════════════════════════════════════════════════

class RawTextSegment(_RawBase):
    """段落/标题内的文本片段 — {"type":"text","content":"..."}
    新版 MinerU 中还可能出现：
    - type=hyperlink 附带 url 字段 + children（显示文本的嵌套子文本段）
    - style 字段（Office 原生解析的字体/样式信息，实测为字符串列表如 ["italic"]）
    """
    type: str = "text"
    content: str = ""
    url: Optional[str] = None                          # hyperlink 类型的目标 URL
    style: Optional[list[str]] = None                  # Office 原生解析的字体样式标记（不用于嵌入）
    children: Optional[list["RawTextSegment"]] = None  # hyperlink 显示文本的嵌套子段（新版 MinerU 2026-05）


class RawImageSource(_RawBase):
    """图片资源引用 — {"path":"images/xxx.jpg"}"""
    path: str = ""


# ── title ─────────────────────────────────────────────────

class RawTitleContent(_RawBase):
    level: int = 1
    title_content: list[RawTextSegment] = Field(default_factory=list)


# ── paragraph ─────────────────────────────────────────────

class RawParagraphContent(_RawBase):
    paragraph_content: list[RawTextSegment] = Field(default_factory=list)


# ── image ─────────────────────────────────────────────────

class RawImageContent(_RawBase):
    image_source: Optional[RawImageSource] = None
    image_caption: list[RawTextSegment] = Field(default_factory=list)
    image_footnote: list[RawTextSegment] = Field(default_factory=list)
    content: Optional[str] = None      # 新版 MinerU：VLM OCR 识别的图片文本内容


# ── table ─────────────────────────────────────────────────

class RawTableContent(_RawBase):
    html: str = ""
    image_source: Optional[RawImageSource] = None
    table_caption: list[RawTextSegment] = Field(default_factory=list)
    table_footnote: list[RawTextSegment] = Field(default_factory=list)
    table_nest_level: Optional[int] = None
    table_type: Optional[str] = None


# ── equation_interline ────────────────────────────────────

class RawEquationContent(_RawBase):
    math_content: str = ""
    math_type: Optional[str] = None
    image_source: Optional[RawImageSource] = None


# ── list ──────────────────────────────────────────────────

class RawListItem(_RawBase):
    item_type: str = "text"
    item_content: list[RawTextSegment] = Field(default_factory=list)
    # 新版 MinerU Office 原生解析新增字段
    ilevel: Optional[int] = None       # 缩进层级
    prefix: Optional[str] = None       # 项目符号前缀（"-", "1.", 等）
    anchor: Optional[str] = None       # 文档锚点（TOC 超链接目标）


class RawListContent(_RawBase):
    list_type: Optional[str] = None
    list_items: list[RawListItem] = Field(default_factory=list)
    attribute: Optional[str] = None    # "unordered" / "ordered"（新版 MinerU）


# ── code ──────────────────────────────────────────────────

class RawCodeContent(_RawBase):
    code_content: list[RawTextSegment] = Field(default_factory=list)
    code_caption: list[RawTextSegment] = Field(default_factory=list)
    code_language: Optional[str] = None


# ── chart（新版 MinerU）─────────────────────────────────────

class RawChartContent(_RawBase):
    """chart 类型块（图表）— 新版 MinerU 新增，与 image 类似但含数据提取结果"""
    image_source: Optional[RawImageSource] = None
    content: Optional[str] = None          # Markdown/文本形式的提取数据
    chart_caption: list[RawTextSegment] = Field(default_factory=list)
    chart_footnote: list[RawTextSegment] = Field(default_factory=list)


# ── auxiliary blocks ──────────────────────────────────────

class RawAuxiliaryContent(_RawBase):
    """page_header / page_footer / page_number / page_footnote

    真实字段格式为 {type}_content: list[RawTextSegment]
    例: page_header_content: [{"type":"text","content":"..."}]
    """
    page_header_content: list[RawTextSegment] = Field(default_factory=list)
    page_footer_content: list[RawTextSegment] = Field(default_factory=list)
    page_number_content: list[RawTextSegment] = Field(default_factory=list)
    page_footnote_content: list[RawTextSegment] = Field(default_factory=list)
    # 尝试小版本兼容：旧版可能用简单 text 字段
    text: Optional[str] = None


# ── 通用 V2 块 ────────────────────────────────────────────

class RawContentListV2Block(_RawBase):
    """content_list_v2.json 中的单个块"""

    type: str
    bbox: Optional[list[float]] = None    # Office 原生解析时可能为 null 或缺失
    content: Any = None                   # 根据 type 解析为具体子结构
    anchor: Optional[str] = None          # DOCX 标题/段落的文档锚点
    sub_type: Optional[str] = None        # chart/equation 的子类型


# ═══════════════════════════════════════════════════════════
# layout.json 模型
# ═══════════════════════════════════════════════════════════

class RawLayoutSpan(_RawBase):
    """layout.json 中 lines[].spans[] 的结构"""
    type: Optional[str] = None
    content: Optional[str] = None
    image_path: Optional[str] = None
    html: Optional[str] = None


class RawLayoutLine(_RawBase):
    """layout.json 中 lines[] 的结构"""
    bbox: list[float] = Field(default_factory=list)
    spans: list[RawLayoutSpan] = Field(default_factory=list)


class RawLayoutSubBlock(_RawBase):
    """layout.json 复合块内的子块"""
    type: Optional[str] = None
    sub_type: Optional[str] = None
    bbox: list[float] = Field(default_factory=list)
    lines: list[RawLayoutLine] = Field(default_factory=list)
    blocks: list[RawLayoutSubBlock] = Field(default_factory=list)
    guess_lang: Optional[str] = None


class RawLayoutParaBlock(_RawBase):
    """layout.json 中 para_blocks[] 的单个块"""
    type: Optional[str] = None
    sub_type: Optional[str] = None
    bbox: list[float] = Field(default_factory=list)
    index: Optional[int] = None
    angle: Optional[float] = None
    lines: list[RawLayoutLine] = Field(default_factory=list)
    blocks: list[RawLayoutSubBlock] = Field(default_factory=list)
    guess_lang: Optional[str] = None


class RawLayoutDiscardedBlock(_RawBase):
    """layout.json 中 discarded_blocks[] 的单个块"""
    type: Optional[str] = None
    bbox: list[float] = Field(default_factory=list)
    index: Optional[int] = None
    lines: list[RawLayoutLine] = Field(default_factory=list)


class RawLayoutPage(_RawBase):
    """layout.json 中的单个页面"""
    para_blocks: list[RawLayoutParaBlock] = Field(default_factory=list)
    discarded_blocks: list[RawLayoutDiscardedBlock] = Field(default_factory=list)
    page_size: list[float] = Field(default_factory=list)  # [width, height]
    page_idx: int = 0


class RawLayoutJson(_RawBase):
    """layout.json 顶层结构"""
    model_config = {"extra": "allow", "populate_by_name": True}

    pdf_info: list[RawLayoutPage] = Field(default_factory=list)
    backend: Optional[str] = Field(None, alias="_backend")
    ocr_enable: Optional[bool] = Field(None, alias="_ocr_enable")
    vlm_ocr_enable: Optional[bool] = Field(None, alias="_vlm_ocr_enable")
    version_name: Optional[str] = Field(None, alias="_version_name")


# ═══════════════════════════════════════════════════════════
# *_content_list.json 兼容层模型
# ═══════════════════════════════════════════════════════════

class RawContentListCompatBlock(_RawBase):
    """*_content_list.json 中的单个块（扁平结构）"""
    type: str = ""
    text: Optional[str] = None
    text_level: Optional[int] = None
    text_format: Optional[str] = None
    bbox: list[float] = Field(default_factory=list)
    page_idx: Optional[int] = None
    img_path: Optional[str] = None
    image_caption: Optional[str] = None
    image_footnote: Optional[str] = None
    table_body: Optional[str] = None
    table_caption: Optional[str] = None
    table_footnote: Optional[str] = None
    sub_type: Optional[str] = None
    list_items: Optional[list[Any]] = None
    code_body: Optional[str] = None
    code_caption: Optional[str] = None
    guess_lang: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# Bundle 文件清单
# ═══════════════════════════════════════════════════════════

class RawBundleManifest(_RawBase):
    """解压后按后缀/固定名识别出的文件角色清单"""
    content_list_v2_path: Optional[str] = None
    layout_path: Optional[str] = None
    full_md_path: Optional[str] = None
    content_list_compat_path: Optional[str] = None
    model_raw_path: Optional[str] = None
    origin_pdf_path: Optional[str] = None
    images_dir: Optional[str] = None
    zip_root: str = ""
