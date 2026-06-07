"""QA 上下文渲染 —— 把命中的「父块」按块序还原成问答上下文（位置保真）。

Small-to-Big：检索命中子块 → 把其所在**父块**作为上下文喂给问答模型。父块里可能夹着
图片 / 表格，必须**保留它们在正文中的位置**，模型才知道"这张图夹在这两段文字之间"：

  - 纯文本模型（如 DeepSeek）：图片 → `[图片: VLM描述]`（在原位）；表格 → **MinerU 输出的 HTML**
    （在原位，信息比描述更全，虽不利检索但利于作答）；其余块 → 块文本。
  - 多模态模型：图片 / 表格 → **原图**，插到它在父块中的位置（text → image → text 交错），
    用有序的 content 片段表达；无原图的表格回退为 HTML 文本。

数据来自 enriched IR（按 doc_id 读投影，按 parent.block_ids 取块、order_in_doc 排序），
图片原图本地路径来自 assets 表（asset_id → path）。一次问答内按 doc_id 缓存，避免重复读盘。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.db.database import get_db
from app.services import inspection_service

logger = logging.getLogger(__name__)

# 可作为「原图」喂多模态模型的资产类型
_IMG_ASSET_TYPES = {"image", "chart_image", "table_image", "equation_image"}

# 单条来源（父块）注入上下文的字符上限。表格 HTML 较长但信息全，放宽一些。
PARENT_CONTEXT_CAP = 2800


async def _doc_ir_paths(doc_id: str) -> tuple[str, str]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COALESCE(ir_enriched_path,''), COALESCE(ir_path,'') FROM documents WHERE doc_id=?",
            (doc_id,),
        )
        row = await cur.fetchone()
    finally:
        await db.close()
    return (row[0], row[1]) if row else ("", "")


async def _doc_asset_paths(doc_id: str) -> dict[str, str]:
    """asset_id → 本地路径（仅磁盘存在的图片类资产）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT asset_id, path, asset_type FROM assets WHERE doc_id=?", (doc_id,)
        )
        rows = await cur.fetchall()
    finally:
        await db.close()
    out: dict[str, str] = {}
    for r in rows:
        aid, path, atype = r[0], r[1], r[2]
        if aid and path and atype in _IMG_ASSET_TYPES and Path(path).is_file():
            out[aid] = path
    return out


def _block_text(blk: dict) -> str:
    """单块在纯文本上下文里的表示：图→[图片:描述]，表→HTML，其余→块文本。"""
    t = blk.get("type")
    if t == "image":
        desc = (blk.get("vlm_description") or blk.get("text") or "").strip()
        return f"[图片: {desc}]" if desc else "[图片]"
    if t == "table":
        html = (blk.get("table_html") or "").strip()
        if html:
            return html
        cap = (blk.get("text") or "").strip()
        return f"[表格: {cap}]" if cap else "[表格]"
    return (blk.get("text") or "").strip()


def _block_image_path(blk: dict, asset_paths: dict[str, str]) -> str | None:
    """块的第一个可用原图本地路径（image / table_image 等），无则 None。"""
    for aid in blk.get("assets") or []:
        p = asset_paths.get(aid)
        if p:
            return p
    return None


def _render_text(blocks: list[dict]) -> str:
    """纯文本上下文：各块文本（图=描述、表=HTML）按序拼接。"""
    parts = [_block_text(b) for b in blocks]
    return "\n\n".join(p for p in parts if p.strip())


def _render_segments(blocks: list[dict], asset_paths: dict[str, str]) -> list[dict]:
    """多模态有序片段：文本累积成 text 段，遇到有原图的图/表 → 先收尾文本段，再发 image 段。

    返回 [{"type":"text","text":...} | {"type":"image","path":...}]，位置即父块中的原位。
    """
    segs: list[dict] = []
    buf: list[str] = []

    def flush() -> None:
        text = "\n\n".join(x for x in buf if x.strip())
        if text.strip():
            segs.append({"type": "text", "text": text})
        buf.clear()

    for b in blocks:
        img_path = _block_image_path(b, asset_paths) if b.get("type") in ("image", "table") else None
        if img_path:
            cap = (b.get("vlm_description") or b.get("text") or "").strip()
            buf.append(f"（下图：{cap[:50]}）" if cap else "（下图）")
            flush()
            segs.append({"type": "image", "path": img_path})
        else:
            txt = _block_text(b)
            if txt:
                buf.append(txt)
    flush()
    return segs


async def render_qa_sources(
    chunks: list,
    parent_map: dict[str, dict],
    *,
    multimodal: bool,
) -> list[dict]:
    """命中子块（已重排）→ 每条对应其父块的问答上下文（位置保真）。

    返回 sources，每条：
      {header_path, page_span_start, page_span_end, doc_id,
       text:     纯文本上下文（图=描述、表=HTML，在原位），
       segments: 多模态有序片段（multimodal=True 且父块可还原时才有，否则 None）}
    无法读 IR / 无 block_ids 时回退父块预拼全文（保证不空）。
    """
    ir_cache: dict[str, dict[str, dict]] = {}     # doc_id -> {block_id: block}
    asset_cache: dict[str, dict[str, str]] = {}   # doc_id -> {asset_id: path}

    async def _ensure(doc_id: str) -> None:
        if doc_id in ir_cache:
            return
        ep, bp = await _doc_ir_paths(doc_id)
        proj = inspection_service.load_ir_projection(ep, bp)
        ir_cache[doc_id] = {b["block_id"]: b for b in (proj or {}).get("blocks", [])}
        asset_cache[doc_id] = await _doc_asset_paths(doc_id) if multimodal else {}

    sources: list[dict] = []
    for c in chunks:
        parent = parent_map.get(c.parent_chunk_id, {})
        hp = parent.get("header_path") or getattr(c, "header_path", []) or []
        ps = parent.get("page_span_start", getattr(c, "page_span_start", 0))
        pe = parent.get("page_span_end", getattr(c, "page_span_end", 0))
        doc_id = getattr(c, "doc_id", "") or parent.get("doc_id", "")
        block_ids = parent.get("block_ids") or []

        text = ""
        segments: list[dict] | None = None
        if block_ids and doc_id:
            try:
                await _ensure(doc_id)
                byid = ir_cache.get(doc_id, {})
                blocks = [byid[b] for b in block_ids if b in byid]
                blocks.sort(key=lambda b: b.get("order_in_doc", 0))
                if blocks:
                    text = _render_text(blocks)
                    if multimodal:
                        segments = _render_segments(blocks, asset_cache.get(doc_id, {}))
            except Exception:
                logger.warning("渲染父块上下文失败 doc=%s parent=%s，回退预拼全文",
                               doc_id, c.parent_chunk_id, exc_info=True)

        if not text.strip():
            text = (
                (parent.get("text_full") or "").strip()
                or (parent.get("text_preview") or "").strip()
                or getattr(c, "retrieval_text", "")
                or ""
            )
            segments = None  # 回退时无法保证位置，纯文本注入
        text = text[:PARENT_CONTEXT_CAP]

        sources.append({
            "header_path": hp,
            "page_span_start": ps,
            "page_span_end": pe,
            "doc_id": doc_id,
            "text": text,
            "segments": segments,
        })
    return sources


def sources_have_images(sources: list[dict]) -> bool:
    """是否有任一来源含可注入的原图片段（决定是否走多模态）。"""
    for s in sources:
        for seg in s.get("segments") or []:
            if seg.get("type") == "image":
                return True
    return False
