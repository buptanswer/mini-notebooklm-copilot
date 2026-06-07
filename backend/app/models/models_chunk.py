"""
Parent / Child Chunk 模型（第二层：严出）

设计原则：
- Parent Chunk = 整个小节（section 级别），用于回答阶段补全上下文
- Child Chunk = 面向 embedding 的小粒度块，用于向量检索
- 两者之间必须存在显式 ID 映射
- Child 不跨 section 边界
- list / code 默认作为原子块保留

覆盖产物：
- parent_chunks.jsonl
- child_chunks.jsonl
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


ChunkType = Literal[
    "paragraph",
    "list",
    "code",
    "image",
    "table",
    "equation",
]


# ═══════════════════════════════════════════════════════════
# Parent Chunk
# ═══════════════════════════════════════════════════════════

class ParentChunkMetadata(BaseModel):
    """Parent Chunk 附加的页面辅助信息"""
    page_headers: list[str] = Field(default_factory=list)
    page_footers: list[str] = Field(default_factory=list)
    page_numbers: list[str] = Field(default_factory=list)


class ParentChunk(BaseModel):
    """
    Parent Chunk — 以 section 为边界的大粒度块

    用途：检索命中后回填大上下文，最终问答时作为 Big Context
    """
    parent_chunk_id: str
    doc_id: str
    section_id: str
    header_path: list[str] = Field(default_factory=list)
    title: str = ""
    page_span: list[int] = Field(default_factory=list)  # [start_page, end_page]
    block_ids: list[str] = Field(default_factory=list)
    text_for_generation: str = ""
    assets: list[str] = Field(default_factory=list)  # asset_id 列表
    metadata: ParentChunkMetadata = Field(default_factory=ParentChunkMetadata)


# ═══════════════════════════════════════════════════════════
# Child Chunk
# ═══════════════════════════════════════════════════════════

class ChildChunkMetadata(BaseModel):
    """Child Chunk 附加元数据"""
    page_numbers: list[str] = Field(default_factory=list)
    code_language: Optional[str] = None
    is_atomic: bool = False
    is_atomic_fragment: bool = False
    fragment_index: Optional[int] = None
    fragment_total: Optional[int] = None
    enrichment_status: Literal["ok", "partial_failed", "skipped"] = "ok"


class ChildChunk(BaseModel):
    """
    Child Chunk — 面向向量检索的小粒度块

    embedding_text: 拼接了 header_path 前缀的完整文本（用于向量化）
    retrieval_text: 不含 header_path 前缀的原文（用于展示）
    """
    child_chunk_id: str
    parent_chunk_id: str
    doc_id: str
    section_id: str
    header_path: list[str] = Field(default_factory=list)
    chunk_type: ChunkType
    page_span: list[int] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)
    # 每个子块可对应多个来源 block，保留 bbox 列表用于前端高亮
    bbox_norm1000: list[list[float]] = Field(default_factory=list)
    bbox_page: list[list[float]] = Field(default_factory=list)
    anchor_origin_pdf_path: str = ""
    embedding_text: str = ""
    retrieval_text: str = ""
    assets: list[str] = Field(default_factory=list)  # asset_id 列表
    index_kind: str = ""  # ''=常规子块；非空=父块自定义索引物化的虚拟子块(summary/hypo_question/image_desc/table_desc/custom)
    metadata: ChildChunkMetadata = Field(default_factory=ChildChunkMetadata)
