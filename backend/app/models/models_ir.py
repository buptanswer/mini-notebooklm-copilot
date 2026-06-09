"""
标准化 IR 模型（第二层：严出）

设计原则：
- 严格定义字段、类型、嵌套关系和约束
- 枚举字段使用 Literal
- bbox / page_idx / header_path 等核心字段不允许用弱类型占位
- 对 bbox_norm1000 增加范围校验
- 对 page_idx 增加非负校验

覆盖产物：
- document_ir.json          （基础 IR）
- document_ir_enriched.json （富化 IR，在基础 IR 上扩展 enrichment 字段）
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════

BlockType = Literal[
    "title",
    "paragraph",
    "list",
    "code",
    "table",
    "image",
    "equation",
    "page_header",
    "page_footer",
    "page_number",
    "page_footnote",
]

BlockRole = Literal["main", "auxiliary"]

SourceFormat = Literal["pdf", "docx", "pptx", "jpg", "jpeg", "png"]

AssetType = Literal[
    "image",
    "chart_image",      # MinerU chart 块（图表截图 + 提取数据）
    "table_image",
    "equation_image",
]

AssetUsage = Literal[
    "primary",
    "qa_preferred",
    "debug_or_render",
]


# ═══════════════════════════════════════════════════════════
# 公共子结构
# ═══════════════════════════════════════════════════════════

class BboxNorm1000(BaseModel):
    """归一化到 0-1000 的坐标 [x0, y0, x1, y1]"""
    coords: list[float] = Field(..., min_length=4, max_length=4)

    @field_validator("coords")
    @classmethod
    def check_range(cls, v: list[float]) -> list[float]:
        for c in v:
            if not (-10 <= c <= 1010):  # 留轻微容差
                raise ValueError(f"bbox_norm1000 坐标 {c} 超出合理范围")
        return v


class BboxPage(BaseModel):
    """原始 PDF 页坐标 [x0, y0, x1, y1]"""
    coords: list[float] = Field(..., min_length=4, max_length=4)


class Anchor(BaseModel):
    """块的坐标锚点，用于前端 PDF 高亮"""
    page_id: str
    origin_pdf_path: str
    coord_space: str = "origin_pdf_native"


class TextSegment(BaseModel):
    """文本片段"""
    type: Literal["text", "inline_equation"] = "text"
    content: str = ""


class Asset(BaseModel):
    """多模态资产引用"""
    asset_id: str
    asset_type: AssetType
    path: str
    usage: AssetUsage = "primary"
    mime: Optional[str] = None


class FootnoteLink(BaseModel):
    """脚注链接"""
    footnote_block_id: str
    attach_mode: Literal["inline_append", "orphan"] = "inline_append"
    confidence: float = 0.0


class PageAuxiliaryRef(BaseModel):
    """块关联的页面辅助信息引用"""
    header_block_ids: list[str] = Field(default_factory=list)
    footer_block_ids: list[str] = Field(default_factory=list)
    page_number_block_ids: list[str] = Field(default_factory=list)


class RawSourceTrace(BaseModel):
    """原始来源追踪"""
    source_file: str
    source_type: str


# ═══════════════════════════════════════════════════════════
# Block 元数据
# ═══════════════════════════════════════════════════════════

class BlockMetadata(BaseModel):
    """块级元数据"""
    title_level: Optional[int] = None
    code_language: Optional[str] = None
    list_type: Optional[str] = None
    math_type: Optional[str] = None
    table_type: Optional[str] = None
    table_html: Optional[str] = None
    math_content: Optional[str] = None
    retrieval_text_override: Optional[str] = None  # code/equation LLM 富化文本，供子块检索
    page_auxiliary_ref: Optional[PageAuxiliaryRef] = None


# ═══════════════════════════════════════════════════════════
# IR Block
# ═══════════════════════════════════════════════════════════

class IRBlock(BaseModel):
    """标准化 IR 块 — document_ir.json 的核心"""

    block_id: str
    page_idx: int = Field(..., ge=0)
    order_in_page: int = Field(..., ge=0)
    order_in_doc: int = Field(..., ge=0)
    section_id: str
    header_path: list[str] = Field(default_factory=list)
    type: BlockType
    subtype: Optional[str] = None
    role: BlockRole = "main"
    bbox_norm1000: BboxNorm1000
    bbox_page: Optional[BboxPage] = None
    anchor: Optional[Anchor] = None
    text: str = ""
    segments: list[TextSegment] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    metadata: BlockMetadata = Field(default_factory=BlockMetadata)
    footnote_links: list[FootnoteLink] = Field(default_factory=list)
    raw_source: Optional[RawSourceTrace] = None


# ═══════════════════════════════════════════════════════════
# Page 辅助信息
# ═══════════════════════════════════════════════════════════

class AuxiliaryItem(BaseModel):
    text: str = ""
    block_id: str = ""


class PageFootnote(BaseModel):
    block_id: str
    text: str = ""


class PageAuxiliary(BaseModel):
    page_headers: list[AuxiliaryItem] = Field(default_factory=list)
    page_footers: list[AuxiliaryItem] = Field(default_factory=list)
    page_numbers: list[AuxiliaryItem] = Field(default_factory=list)


class PageSize(BaseModel):
    width: float
    height: float
    unit: str = "origin_pdf_native"


class IRPage(BaseModel):
    """IR 页面对象"""
    page_id: str
    page_idx: int = Field(..., ge=0)
    page_size: Optional[PageSize] = None
    auxiliary: PageAuxiliary = Field(default_factory=PageAuxiliary)
    footnotes: list[PageFootnote] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Section Tree
# ═══════════════════════════════════════════════════════════

class IRSection(BaseModel):
    """IR Section 节点"""
    section_id: str
    parent_section_id: Optional[str] = None
    level: int = Field(..., ge=0)
    title: str = ""
    header_path: list[str] = Field(default_factory=list)
    synthetic: bool = False
    page_span: list[int] = Field(default_factory=list)  # [start_page, end_page]
    child_section_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    order_start: Optional[int] = None
    order_end: Optional[int] = None


# ═══════════════════════════════════════════════════════════
# 顶层 Source / Bundle / Document
# ═══════════════════════════════════════════════════════════

class IRSource(BaseModel):
    """原始来源信息"""
    doc_id: str
    source_filename: str
    source_format: SourceFormat
    mineru_request_model: str = "vlm"
    mineru_actual_backend: Optional[str] = None
    mineru_version_name: Optional[str] = None
    origin_pdf_path: Optional[str] = None


class IRBundleRootFiles(BaseModel):
    content_list_v2: Optional[str] = None
    layout: Optional[str] = None
    full_md: Optional[str] = None
    content_list_compat: Optional[str] = None
    model_raw: Optional[str] = None
    origin_pdf: Optional[str] = None


class IRBundle(BaseModel):
    root_files: IRBundleRootFiles = Field(default_factory=IRBundleRootFiles)
    asset_root: str = "images/"
    asset_count: int = 0


class IRDocument(BaseModel):
    title: str = ""
    language: Literal["zh", "en", "mixed", "unknown"] = "unknown"
    page_count: int = 0
    reading_order: str = "page_then_block"
    has_multimodal: bool = False
    has_code: bool = False
    has_table: bool = False
    has_equation: bool = False
    has_footnote: bool = False


# ═══════════════════════════════════════════════════════════
# Relations
# ═══════════════════════════════════════════════════════════

class IRRelations(BaseModel):
    parent_child: list[dict] = Field(default_factory=list)
    footnote_attachment: list[dict] = Field(default_factory=list)
    block_neighbors: list[dict] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Quality signals
# ═══════════════════════════════════════════════════════════

class IRQuality(BaseModel):
    title_coverage: Optional[float] = None
    footnote_attach_rate: Optional[float] = None
    table_summary_coverage: Optional[float] = None
    image_vlm_coverage: Optional[float] = None
    ui_anchor_coverage: Optional[float] = None
    degraded_modes: list[str] = Field(default_factory=list)
    # 解析警告汇总：只要 degraded_modes 非空就置 True，pipeline 据此将文档标记为 needs_review
    has_warnings: bool = False
    warning_count: int = 0


# ═══════════════════════════════════════════════════════════
# Document IR 顶层
# ═══════════════════════════════════════════════════════════

class DocumentIR(BaseModel):
    """document_ir.json 的顶层结构"""
    ir_version: str = "1.0.0"
    pipeline_version: str = "1.0.0"
    source: IRSource
    bundle: IRBundle = Field(default_factory=IRBundle)
    document: IRDocument = Field(default_factory=IRDocument)
    pages: list[IRPage] = Field(default_factory=list)
    sections: list[IRSection] = Field(default_factory=list)
    blocks: list[IRBlock] = Field(default_factory=list)
    relations: IRRelations = Field(default_factory=IRRelations)
    quality: IRQuality = Field(default_factory=IRQuality)


# ═══════════════════════════════════════════════════════════
# Enrichment 扩展（用于 document_ir_enriched.json）
# ═══════════════════════════════════════════════════════════

class NeighborContext(BaseModel):
    prev_paragraphs: list[str] = Field(default_factory=list)
    next_paragraphs: list[str] = Field(default_factory=list)


class ImageEnrichment(BaseModel):
    image_caption_text: str = ""
    image_vlm_description: str = ""
    neighbor_context: NeighborContext = Field(default_factory=NeighborContext)
    embedding_text: str = ""


class TableEnrichment(BaseModel):
    table_caption_text: str = ""
    table_summary: str = ""
    table_html_available: bool = False
    embedding_text: str = ""


class EquationEnrichment(BaseModel):
    """公式富化：LLM 生成的自然语言解释"""
    equation_context_text: str = ""   # 公式含义的自然语言说明
    embedding_text: str = ""          # [数学公式]:LaTeX\n[公式含义]:说明 → 用于检索


class CodeEnrichment(BaseModel):
    """代码块富化：LLM 生成的功能摘要 + 提取核心代码"""
    code_summary: str = ""            # 1-2 句代码功能说明
    core_code: str = ""              # 提取的核心函数/类代码（剔除 import/boilerplate）
    embedding_text: str = ""          # [代码功能说明]:摘要\n[核心代码]:code → 用于检索


class BlockEnrichment(BaseModel):
    """富化后块的扩展字段"""
    image: Optional[ImageEnrichment] = None
    table: Optional[TableEnrichment] = None
    equation: Optional[EquationEnrichment] = None
    code: Optional[CodeEnrichment] = None
    enrichment_status: Literal["ok", "partial_failed", "skipped"] = "ok"


class IRBlockEnriched(IRBlock):
    """富化后的 IR Block"""
    enrichment: Optional[BlockEnrichment] = None


class DocumentIREnriched(DocumentIR):
    """document_ir_enriched.json 顶层结构"""
    blocks: list[IRBlockEnriched] = Field(default_factory=list)  # type: ignore[assignment]
