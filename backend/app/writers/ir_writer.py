"""
IR Writer — 将 DocumentIR 序列化为 document_ir.json

职责：
1. 组装 DocumentIR 顶层（source / bundle / document / pages / sections / blocks）
2. 用严格模型验证（如果验证失败，则 BLOCK 而不是写入垃圾数据）
3. 写入 {rag_output_dir}/{doc_id}/document_ir.json
4. 返回写出路径
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.models.models_ir import (
    DocumentIR,
    IRBlock,
    IRBundle,
    IRBundleRootFiles,
    IRDocument,
    IRPage,
    IRQuality,
    IRRelations,
    IRSection,
    IRSource,
    SourceFormat,
)
from app.models.models_raw_mineru import RawBundleManifest

logger = logging.getLogger(__name__)


def write_ir(
    doc_id: str,
    source_filename: str,
    source_format: str,
    manifest: RawBundleManifest,
    blocks: list[IRBlock],
    pages: list[IRPage],
    sections: list[IRSection],
    degraded_modes: list[str],
    mineru_backend: str | None = None,
    mineru_version: str | None = None,
) -> Path:
    """
    组装 DocumentIR 并写出 document_ir.json。

    Returns:
        Path to the written document_ir.json
    """
    # ── 文档元数据统计 ────────────────────────────────────────
    has_multimodal = any(b.type in {"image", "table"} for b in blocks)
    has_code = any(b.type == "code" for b in blocks)
    has_table = any(b.type == "table" for b in blocks)
    has_equation = any(b.type == "equation" for b in blocks)
    has_footnote = any(b.footnote_links for b in blocks)
    page_count = len(pages)

    # 推断文档标题（第一个非 synthetic title block 的文本）
    doc_title = ""
    for b in sorted(blocks, key=lambda x: x.order_in_doc):
        if b.type == "title" and b.text:
            doc_title = b.text
            break

    # ── 构建 IR ────────────────────────────────────────────
    safe_format: SourceFormat = _safe_source_format(source_format)

    source = IRSource(
        doc_id=doc_id,
        source_filename=source_filename,
        source_format=safe_format,
        mineru_request_model=settings.mineru_model_version,
        mineru_actual_backend=mineru_backend,
        mineru_version_name=mineru_version,
        origin_pdf_path=manifest.origin_pdf_path,
    )

    bundle = IRBundle(
        root_files=IRBundleRootFiles(
            content_list_v2=manifest.content_list_v2_path,
            layout=manifest.layout_path,
            full_md=manifest.full_md_path,
            content_list_compat=manifest.content_list_compat_path,
            model_raw=manifest.model_raw_path,
            origin_pdf=manifest.origin_pdf_path,
        ),
        asset_root=manifest.images_dir or "",
        asset_count=sum(len(b.assets) for b in blocks),
    )

    document = IRDocument(
        title=doc_title,
        page_count=page_count,
        has_multimodal=has_multimodal,
        has_code=has_code,
        has_table=has_table,
        has_equation=has_equation,
        has_footnote=has_footnote,
    )

    unique_degraded = list(set(degraded_modes))
    quality = IRQuality(
        degraded_modes=unique_degraded,
        has_warnings=len(unique_degraded) > 0,
        warning_count=len(unique_degraded),
    )

    ir = DocumentIR(
        source=source,
        bundle=bundle,
        document=document,
        pages=pages,
        sections=sections,
        blocks=sorted(blocks, key=lambda b: b.order_in_doc),
        quality=quality,
    )

    # ── 严格验证（已由 Pydantic 构造函数完成，此处仅做二次确认）────
    # DocumentIR 是严格模型，如果到此无异常说明通过
    logger.info(
        "DocumentIR 验证通过: %d 页, %d 块, %d sections, degraded=%s",
        page_count, len(blocks), len(sections), len(degraded_modes),
    )

    # ── 写出文件 ──────────────────────────────────────────────
    out_dir = settings.rag_output_dir / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "document_ir.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            ir.model_dump(mode="json", exclude_none=False),
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info("写出 document_ir.json → %s", out_path)
    return out_path


def _safe_source_format(fmt: str) -> SourceFormat:
    """将 source_format 字符串映射到 Literal 允许的值"""
    mapping = {
        "pdf": "pdf",
        "docx": "docx",
        "doc": "docx",
        "pptx": "pptx",
        "ppt": "pptx",
        "jpg": "jpg",
        "jpeg": "jpeg",
        "png": "png",
    }
    result = mapping.get(fmt.lower(), "pdf")
    return result  # type: ignore[return-value]
