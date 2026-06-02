"""
Inspection Service — 解析/切片透视的只读数据投影（v1.4.0 Phase 2）

把落盘的 IR / chunk 产物投影成前端「MinerU 解析透视」好用的结构：
  - load_ir_projection：读 enriched IR（兜底 basic IR）→ {document, pages, sections, blocks,
    section_bbox(父切片按页 bbox 并集)}；图片块带我们的 VLM 描述。
  - load_chunks：读 parent_chunks.jsonl + child_chunks.jsonl（全字段，含 source_block_ids，
    给前端"块 ↔ 切片"映射）。

全部只读、不触网、不改库。路径安全由调用方（documents API）用 path_within_data_root 兜底。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_ROOT

logger = logging.getLogger(__name__)


# ── 路径安全 ────────────────────────────────────────────────

def path_within_data_root(path_str: str) -> Path | None:
    """把字符串路径解析为绝对路径，校验落在 DATA_ROOT 内且存在，否则返回 None（防穿越）。"""
    if not path_str:
        return None
    try:
        p = Path(path_str).resolve()
        root = DATA_ROOT.resolve()
        if root in p.parents and p.exists():
            return p
    except (OSError, ValueError):
        return None
    return None


# ── IR 投影 ─────────────────────────────────────────────────

def _coords(bbox: object) -> list[float]:
    """从 IR 的 bbox 字段（{"coords":[...]} 或 None）取出 [x0,y0,x1,y1]。"""
    if isinstance(bbox, dict):
        c = bbox.get("coords")
        if isinstance(c, list) and len(c) >= 4:
            return [float(v) for v in c[:4]]
    return []


def _vlm_description(block: dict) -> str:
    """取图片块我们自己 VLM 生成的描述（enriched IR 才有）。"""
    enr = block.get("enrichment")
    if not isinstance(enr, dict):
        return ""
    img = enr.get("image")
    if isinstance(img, dict):
        return (img.get("image_vlm_description") or "").strip()
    return ""


def _project_section(s: dict) -> dict:
    return {
        "section_id": s.get("section_id", ""),
        "parent_section_id": s.get("parent_section_id"),
        "level": s.get("level", 0),
        "title": s.get("title", ""),
        "header_path": s.get("header_path", []),
        "synthetic": s.get("synthetic", False),
        "page_span": s.get("page_span", []),
        "child_section_ids": s.get("child_section_ids", []),
        "block_ids": s.get("block_ids", []),
    }


def _section_bbox_union(blocks: list[dict]) -> dict[str, list[dict]]:
    """按 section_id × page_idx 求成员块 bbox_norm1000 的并集（供左栏父切片大框）。"""
    # section_id -> page_idx -> [x0, y0, x1, y1]
    acc: dict[str, dict[int, list[float]]] = {}
    for b in blocks:
        box = b.get("bbox_norm1000") or []
        if len(box) < 4:
            continue
        sid = b.get("section_id") or ""
        if not sid:
            continue
        page = int(b.get("page_idx", 0))
        page_map = acc.setdefault(sid, {})
        cur = page_map.get(page)
        if cur is None:
            page_map[page] = [box[0], box[1], box[2], box[3]]
        else:
            cur[0] = min(cur[0], box[0])
            cur[1] = min(cur[1], box[1])
            cur[2] = max(cur[2], box[2])
            cur[3] = max(cur[3], box[3])
    return {
        sid: [{"page_idx": pg, "bbox_norm1000": box} for pg, box in sorted(pages.items())]
        for sid, pages in acc.items()
    }


def _project_ir(ir: dict) -> dict:
    document = ir.get("document", {}) or {}
    source = ir.get("source", {}) or {}
    pages = ir.get("pages", []) or []
    sections = ir.get("sections", []) or []
    blocks = ir.get("blocks", []) or []

    proj_pages = []
    for p in pages:
        ps = p.get("page_size") or {}
        proj_pages.append({
            "page_idx": p.get("page_idx", 0),
            "width": ps.get("width"),
            "height": ps.get("height"),
        })

    proj_blocks = []
    enriched = False
    for b in blocks:
        meta = b.get("metadata") or {}
        vlm = _vlm_description(b)
        if vlm:
            enriched = True
        proj_blocks.append({
            "block_id": b.get("block_id", ""),
            "page_idx": b.get("page_idx", 0),
            "order_in_doc": b.get("order_in_doc", 0),
            "order_in_page": b.get("order_in_page", 0),
            "section_id": b.get("section_id", ""),
            "header_path": b.get("header_path", []),
            "type": b.get("type", ""),
            "role": b.get("role", "main"),
            "text": b.get("text", ""),
            "bbox_norm1000": _coords(b.get("bbox_norm1000")),
            "bbox_page": _coords(b.get("bbox_page")),
            "assets": [a.get("asset_id") for a in (b.get("assets") or []) if a.get("asset_id")],
            "title_level": meta.get("title_level"),
            "table_html": meta.get("table_html"),
            "vlm_description": vlm,
        })

    return {
        "document": {
            "title": document.get("title", ""),
            "language": document.get("language", "unknown"),
            "page_count": document.get("page_count", len(proj_pages)),
            "source_format": source.get("source_format", ""),
            "origin_pdf_path": source.get("origin_pdf_path") or "",
            "has_multimodal": document.get("has_multimodal", False),
            "has_table": document.get("has_table", False),
            "has_code": document.get("has_code", False),
            "has_equation": document.get("has_equation", False),
        },
        "enriched": enriched,
        "pages": proj_pages,
        "sections": [_project_section(s) for s in sections],
        "blocks": proj_blocks,
        "section_bbox": _section_bbox_union(proj_blocks),
    }


def load_ir_projection(ir_enriched_path: str, ir_path: str) -> dict | None:
    """优先读 enriched IR（含 VLM 描述），兜底 basic IR；都没有返回 None。"""
    for candidate in (ir_enriched_path, ir_path):
        p = path_within_data_root(candidate)
        if not p:
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                ir = json.load(f)
            return _project_ir(ir)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 IR 失败 %s: %s", p, exc)
            continue
    return None


# ── Chunk 投影 ─────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_chunks(parent_chunks_path: str, child_chunks_path: str) -> dict | None:
    """读 parent/child chunk JSONL（全字段，含 source_block_ids）。任一缺失即返回 None。"""
    pp = path_within_data_root(parent_chunks_path)
    cp = path_within_data_root(child_chunks_path)
    if not pp or not cp:
        return None
    try:
        parents = _read_jsonl(pp)
        children = _read_jsonl(cp)
    except OSError as exc:
        logger.warning("读取 chunk JSONL 失败: %s", exc)
        return None
    return {
        "parents": parents,
        "children": children,
        "counts": {"parents": len(parents), "children": len(children)},
    }
