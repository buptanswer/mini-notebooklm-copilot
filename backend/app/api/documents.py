"""
文档管理 API（上传、解析触发、状态查询、删除）
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.db.database import get_db

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── Response Models ───────────────────────────────────────

class DocInfo(BaseModel):
    doc_id: str
    kb_id: str
    filename: str
    relative_path: str = ""
    source_format: str
    file_size: int
    page_count: int
    status: str            # uploaded / parsing / needs_review / indexed / failed / text_only / missing
    warnings: str = ""    # 解析警告（needs_review 时有内容）
    origin_pdf_path: str = ""  # 用于 PDF 预览
    folder_category: str = ""  # recording / slides / homework / notice / review_note / ''
    bound_file_path: str = ""  # 绑定文件夹模式下的文件绝对路径
    parent_heading_level: int = 0  # 父块粒度（几级标题=1父块）；0=全局默认
    created_at: str
    updated_at: str


class DocListResponse(BaseModel):
    items: list[DocInfo]


# ── Helpers ───────────────────────────────────────────────

_SUPPORTED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".png", ".jpg", ".jpeg",
                          ".txt", ".md", ".xlsx", ".xls"}
# 明确不支持的类型（音视频等，上传时直接拒绝，文件夹同步时跳过）
_UNSUPPORTED_EXTENSIONS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma",
                           ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv"}
_DOC_SELECT = """
    SELECT doc_id, kb_id, filename,
           COALESCE(relative_path, filename) AS relative_path,
           source_format, file_size, page_count,
           status, COALESCE(warnings,'') AS warnings,
           COALESCE(origin_pdf_path,'') AS origin_pdf_path,
           COALESCE(folder_category,'') AS folder_category,
           COALESCE(bound_file_path,'') AS bound_file_path,
           COALESCE(parent_heading_level,0) AS parent_heading_level,
           created_at, updated_at
    FROM documents
"""


def _detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": "pdf", ".ppt": "pptx", ".pptx": "pptx",
        ".doc": "docx", ".docx": "docx",
        ".png": "png", ".jpg": "jpg", ".jpeg": "jpeg",
        ".txt": "txt", ".md": "md",
        ".xlsx": "xlsx", ".xls": "xlsx",
    }
    return mapping.get(ext, "unknown")


def _sanitize_relative_path(relative_path: str) -> str:
    """规范化逻辑路径，防止路径穿越。"""
    normalized = relative_path.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=400, detail="relative_path 非法")
    return "/".join(parts)


# ── 上传文件 ──────────────────────────────────────────────

@router.post("/{kb_id}/upload", response_model=DocInfo)
async def upload_document(
    kb_id: str,
    file: UploadFile,
    relative_path: str | None = Form(default=None),
):
    """上传文件到指定知识库（仅保存，不自动解析，需单独调用 /parse）。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    display_name = Path(file.filename).name
    ext = Path(display_name).suffix.lower()
    if ext in _UNSUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持音视频文件（当前版本未接入转写服务）: {ext}")
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    logical_path = _sanitize_relative_path(relative_path or display_name)
    if not logical_path:
        logical_path = display_name

    doc_id = str(uuid.uuid4())
    settings.ensure_dirs()
    doc_dir = settings.upload_dir / kb_id / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    upload_path = doc_dir / display_name

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = upload_path.stat().st_size
    source_format = _detect_format(display_name)
    # .txt/.md 无需 MinerU，直接标记为可用
    initial_status = "text_only" if source_format in ("txt", "md") else "uploaded"
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    try:
        cursor = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (kb_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="知识库不存在")

        await db.execute(
            """INSERT INTO documents
               (doc_id, kb_id, filename, relative_path, source_format, file_size, upload_path,
                status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, kb_id, display_name, logical_path, source_format, file_size, str(upload_path),
             initial_status, now, now),
        )
        await db.execute(
            "UPDATE knowledge_bases SET file_count = file_count + 1, updated_at = ? WHERE kb_id = ?",
            (now, kb_id),
        )
        await db.commit()

        return DocInfo(
            doc_id=doc_id, kb_id=kb_id, filename=display_name,
            relative_path=logical_path,
            source_format=source_format, file_size=file_size, page_count=0,
            status=initial_status, created_at=now, updated_at=now,
        )
    finally:
        await db.close()


# ── 查询文档 ──────────────────────────────────────────────

@router.get("/{kb_id}", response_model=DocListResponse)
async def list_documents(kb_id: str):
    db = await get_db()
    try:
        cur = await db.execute(
            _DOC_SELECT + "WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
        )
        rows = await cur.fetchall()
        return DocListResponse(items=[DocInfo(**dict(r)) for r in rows])
    finally:
        await db.close()


@router.get("/{kb_id}/{doc_id}", response_model=DocInfo)
async def get_document(kb_id: str, doc_id: str):
    """获取单个文档（含 status，可用于轮询解析状态）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            _DOC_SELECT + "WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocInfo(**dict(row))
    finally:
        await db.close()


# ── 触发解析 ──────────────────────────────────────────────

@router.post("/{kb_id}/{doc_id}/parse", summary="触发文档解析流水线")
async def trigger_parse(kb_id: str, doc_id: str, bg: BackgroundTasks):
    """
    异步触发解析流水线（MinerU → IR → Chunk → Embed → Index）。
    文档必须是 uploaded / failed / needs_review 状态才能重新触发。
    """
    from app.services.pipeline_service import run_parse_pipeline

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, filename, source_format, upload_path, bound_file_path, status FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
        if r["source_format"] in ("txt", "md"):
            raise HTTPException(status_code=400, detail="txt/md 文件无需解析（已直接可用）")
        if r["status"] not in ("uploaded", "failed", "needs_review"):
            raise HTTPException(
                status_code=409,
                detail=f"当前状态 '{r['status']}' 无法重新解析",
            )
        # 兼容文件夹同步模式：upload_path 为空时使用 bound_file_path
        effective_path_str = r["upload_path"] or r["bound_file_path"] or ""
        if not effective_path_str or not Path(effective_path_str).exists():
            raise HTTPException(status_code=400, detail="原始文件不存在，请检查文件是否在磁盘上")
    finally:
        await db.close()

    bg.add_task(
        run_parse_pipeline,
        doc_id=r["doc_id"],
        kb_id=r["kb_id"],
        upload_path=Path(effective_path_str),
        filename=r["filename"],
        source_format=r["source_format"],
    )
    return {"detail": "解析任务已启动", "doc_id": doc_id}


@router.post("/{kb_id}/{doc_id}/index-text", summary="索引文本文档（txt/md）到检索库")
async def index_text(kb_id: str, doc_id: str, bg: BackgroundTasks):
    """
    把 txt/md 文本文档切片→嵌入→入库供混合检索。
    **录音转写 .txt 不可索引**（仅作课后复习生成素材）。
    """
    from app.services import text_index_service

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, source_format, folder_category, bound_file_path, upload_path, status "
            "FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
    finally:
        await db.close()

    if not text_index_service.is_indexable_text(r.get("folder_category"), r.get("source_format")):
        raise HTTPException(
            status_code=400,
            detail="该文档不可索引（仅非录音的 txt/md 文本可索引；录音转写仅作复习素材）",
        )
    path = r["bound_file_path"] or r["upload_path"] or ""
    if not path or not Path(path).exists():
        raise HTTPException(status_code=400, detail="原始文件不存在")

    bg.add_task(
        text_index_service.index_text_document_bg, doc_id, path, r["source_format"]
    )
    return {"detail": "文本索引任务已启动", "doc_id": doc_id}


# ── 删除文档 ──────────────────────────────────────────────

@router.delete("/{kb_id}/{doc_id}", summary="删除文档及其所有数据")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档：清除 Qdrant 向量、SQLite 所有相关记录、本地文件。"""
    from app.db.qdrant_client import get_qdrant
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="文档不存在")

        # 1. 清除 Qdrant 向量（失败不阻断删除）
        try:
            client = get_qdrant()
            client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    )
                ),
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Qdrant 删除失败（继续）: %s", exc)

        # 2. 清除 SQLite（按 FK 顺序）
        await db.execute("DELETE FROM child_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM parent_chunks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM assets WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM tasks WHERE doc_id=?", (doc_id,))
        await db.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
        await db.execute(
            "UPDATE knowledge_bases SET file_count = MAX(0, file_count - 1), updated_at=? WHERE kb_id=?",
            (datetime.now(timezone.utc).isoformat(), kb_id),
        )
        await db.commit()
    finally:
        await db.close()

    # 3. 删除本系统生成的本地数据（失败不影响请求）。
    #    路径全部由 kb_id/doc_id 显式拼接、限定在 data 子目录内：
    #    - 绝不再从 upload_path 反推父目录——文件夹绑定文档的 upload_path 为空串，
    #      旧实现 Path("").parent == "."，shutil.rmtree(".") 会把整个后端工作目录删光（致命 bug）。
    #    - 文件夹绑定模式下用户的原始文件（bound_file_path）也绝不删除，只清我们的派生数据。
    import logging
    _logger = logging.getLogger(__name__)
    for target in (
        settings.upload_dir / kb_id / doc_id,   # 上传模式：该文档独立目录
        settings.rag_output_dir / doc_id,        # IR / chunk / origin.pdf 落盘目录
        settings.mineru_zip_dir / doc_id,        # MinerU zip 解压目录
    ):
        try:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        except Exception as exc:
            _logger.warning("删除本地数据失败（继续）: %s", exc)

    return {"detail": "已删除", "doc_id": doc_id}


# ── 获取原始 PDF ──────────────────────────────────────────

@router.get("/{kb_id}/{doc_id}/origin-pdf", summary="获取 origin.pdf 文件")
async def get_origin_pdf(kb_id: str, doc_id: str):
    """返回 *_origin.pdf 文件，前端 iframe 嵌入 + #page=N 跳转。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT origin_pdf_path FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        path_str = (dict(row).get("origin_pdf_path") or "").strip()
    finally:
        await db.close()

    if not path_str or not Path(path_str).exists():
        raise HTTPException(status_code=404, detail="origin.pdf 尚未生成（请先完成文档解析）")

    return FileResponse(
        path=path_str,
        media_type="application/pdf",
        filename=f"{doc_id}_origin.pdf",
        headers={"Content-Disposition": "inline"},
    )


# ── 读取 txt/md 原文 ──────────────────────────────────────

@router.get("/{kb_id}/{doc_id}/raw-text", summary="读取 txt/md 文件原文")
async def get_raw_text(kb_id: str, doc_id: str):
    """返回 txt/md 文件的纯文本内容（UTF-8）。仅限 source_format in (txt, md)。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT source_format, upload_path, bound_file_path FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
    finally:
        await db.close()

    if r["source_format"] not in ("txt", "md"):
        raise HTTPException(status_code=400, detail="仅支持 txt/md 格式文件")

    # 优先用 bound_file_path（文件夹绑定），否则用 upload_path
    path_str = (r.get("bound_file_path") or "").strip() or (r.get("upload_path") or "").strip()
    if not path_str or not Path(path_str).exists():
        raise HTTPException(status_code=404, detail="文件不存在于磁盘，请重新同步")

    text = Path(path_str).read_text(encoding="utf-8", errors="replace")
    return {"doc_id": doc_id, "text": text, "path": path_str}


# ── 解析透视检视接口（v1.4.0 Phase 2，只读）──────────────────

@router.get("/{kb_id}/{doc_id}/ir", summary="解析透视：IR 投影（blocks/sections/bbox/VLM描述）")
async def get_document_ir(kb_id: str, doc_id: str):
    """
    返回文档 IR 的可视化投影：页尺寸、section 树、blocks（含 bbox/类型/文本/图片 VLM 描述）、
    父切片按页 bbox 并集。优先 enriched IR（含 VLM 描述），兜底 basic IR。
    """
    from app.services import inspection_service

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COALESCE(ir_enriched_path,'') AS e, COALESCE(ir_path,'') AS b "
            "FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
    finally:
        await db.close()

    proj = inspection_service.load_ir_projection(r["e"], r["b"])
    if proj is None:
        raise HTTPException(status_code=404, detail="IR 尚未生成（请先完成文档解析）")
    return {"doc_id": doc_id, "kb_id": kb_id, **proj}


@router.get("/{kb_id}/{doc_id}/chunks", summary="解析透视：父/子切片全文（含 source_block_ids）")
async def get_document_chunks(kb_id: str, doc_id: str):
    """返回 parent_chunks.jsonl + child_chunks.jsonl 全字段，给前端「块 ↔ 切片」映射。"""
    from app.services import inspection_service

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COALESCE(parent_chunks_path,'') AS p, COALESCE(child_chunks_path,'') AS c "
            "FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
    finally:
        await db.close()

    data = inspection_service.load_chunks(r["p"], r["c"])
    if data is None:
        raise HTTPException(status_code=404, detail="切片文件尚未生成（请先完成文档解析）")
    return {"doc_id": doc_id, "kb_id": kb_id, **data}


@router.get("/{kb_id}/{doc_id}/asset/{asset_id}", summary="解析透视：服务图片资产（裁剪图）")
async def get_document_asset(kb_id: str, doc_id: str, asset_id: str):
    """按 asset_id 返回图片文件（VLM 描述见 /ir）。路径限定在 DATA_ROOT 内防穿越。"""
    from app.services.inspection_service import path_within_data_root

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT path, COALESCE(mime,'') AS mime FROM assets WHERE asset_id=? AND doc_id=?",
            (asset_id, doc_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="资产不存在")
        r = dict(row)
    finally:
        await db.close()

    safe = path_within_data_root(r["path"])
    if not safe:
        raise HTTPException(status_code=404, detail="资产文件不存在")

    media_type = r["mime"] or "image/jpeg"
    return FileResponse(path=str(safe), media_type=media_type, headers={"Content-Disposition": "inline"})


# ── 父块自定义索引（v1.5.0）──────────────────────────────────
# 摘要 / 推测问题(可预答,默认关) / 图片描述 / 表格描述 / 自定义；可生成·开关·编辑·删除，
# 启用即物化为虚拟子块接入混合检索（详见 services/index_builder_service）。

class GenerateIndexBody(BaseModel):
    parent_chunk_id: str
    kind: str                       # summary / hypo_question / custom
    custom_text: str | None = None  # 仅 custom 需要
    title: str | None = None
    with_answer: bool = False       # 仅 hypo_question：是否一并预答（更耗 API）
    enable: bool = False            # 生成后是否立即启用并参与检索


class ReindexBody(BaseModel):
    parent_level: int               # 几级标题=1 父块（≥1）


class UpdateIndexBody(BaseModel):
    index_text: str | None = None
    title: str | None = None


class ToggleIndexBody(BaseModel):
    enabled: bool


class RegenerateIndexBody(BaseModel):
    with_answer: bool = False


async def _assert_doc(kb_id: str, doc_id: str) -> None:
    """校验文档存在且属于该知识库。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT 1 FROM documents WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="文档不存在")
    finally:
        await db.close()


@router.get("/{kb_id}/{doc_id}/indexes", summary="列出文档的父块自定义索引")
async def list_doc_indexes(kb_id: str, doc_id: str):
    """返回该文档全部自定义索引（按父块聚合，供解析透视父块面板展示）。"""
    from app.services import index_builder_service

    await _assert_doc(kb_id, doc_id)
    items = await index_builder_service.list_doc_indexes(doc_id)
    # 按 parent_chunk_id 聚合，便于前端直接挂到父块
    by_parent: dict[str, list[dict]] = {}
    for it in items:
        by_parent.setdefault(it["parent_chunk_id"], []).append(it)
    return {"doc_id": doc_id, "kb_id": kb_id, "items": items, "by_parent": by_parent}


@router.post("/{kb_id}/{doc_id}/indexes", summary="生成一条父块自定义索引")
async def create_doc_index(kb_id: str, doc_id: str, body: GenerateIndexBody):
    """生成（custom 为手填）一条父块索引；enable=true 时立即物化参与检索。"""
    from app.services import index_builder_service
    from app.services.index_builder_service import IndexBuildError

    await _assert_doc(kb_id, doc_id)
    try:
        row = await index_builder_service.generate_index(
            doc_id, body.parent_chunk_id, body.kind,
            custom_text=body.custom_text, title=body.title,
            with_answer=body.with_answer, enable=body.enable,
        )
    except IndexBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.patch("/{kb_id}/{doc_id}/indexes/{index_id}", summary="编辑父块索引文本/标题")
async def patch_doc_index(kb_id: str, doc_id: str, index_id: str, body: UpdateIndexBody):
    from app.services import index_builder_service
    from app.services.index_builder_service import IndexBuildError

    await _assert_doc(kb_id, doc_id)
    try:
        row = await index_builder_service.update_index(
            index_id, index_text=body.index_text, title=body.title,
        )
    except IndexBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.post("/{kb_id}/{doc_id}/indexes/{index_id}/toggle", summary="启用/停用父块索引")
async def toggle_doc_index(kb_id: str, doc_id: str, index_id: str, body: ToggleIndexBody):
    from app.services import index_builder_service
    from app.services.index_builder_service import IndexBuildError

    await _assert_doc(kb_id, doc_id)
    try:
        row = await index_builder_service.set_index_enabled(index_id, body.enabled)
    except IndexBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.post("/{kb_id}/{doc_id}/indexes/{index_id}/regenerate", summary="重新生成父块索引（auto 类）")
async def regenerate_doc_index(kb_id: str, doc_id: str, index_id: str, body: RegenerateIndexBody):
    from app.services import index_builder_service
    from app.services.index_builder_service import IndexBuildError

    await _assert_doc(kb_id, doc_id)
    try:
        row = await index_builder_service.regenerate_index(index_id, with_answer=body.with_answer)
    except IndexBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.delete("/{kb_id}/{doc_id}/indexes/{index_id}", summary="删除父块索引")
async def delete_doc_index(kb_id: str, doc_id: str, index_id: str):
    from app.services import index_builder_service
    from app.services.index_builder_service import IndexBuildError

    await _assert_doc(kb_id, doc_id)
    try:
        await index_builder_service.delete_index(index_id)
    except IndexBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"detail": "已删除", "index_id": index_id}


# ── 父块粒度重切片 / 重解析（v1.5.0）─────────────────────────

@router.post("/{kb_id}/{doc_id}/reindex", summary="按新父块粒度重切片+重索引（不重新解析 MinerU）")
async def reindex_document(kb_id: str, doc_id: str, body: ReindexBody):
    """复用已持久化的 enriched IR，按「几级标题=1父块」重切片、重嵌入、重入库（省 MinerU/VLM 开销）。

    注意：父块边界变化会清掉该文档已建的自定义索引（需重建）。
    """
    from app.services import reindex_service
    from app.services.reindex_service import ReindexError

    await _assert_doc(kb_id, doc_id)
    try:
        result = await reindex_service.rechunk_and_reindex(doc_id, body.parent_level)
    except ReindexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"detail": "重切片完成", **result}


@router.post("/{kb_id}/{doc_id}/reparse", summary="重置状态并重新解析（已索引文档取坐标/更新格式）")
async def reparse_document(kb_id: str, doc_id: str, bg: BackgroundTasks):
    """对**已索引**文档重新走完整解析流水线（MinerU→IR→Chunk→Embed→Index）。

    用途：①已索引的 Office 文档取版面坐标（is_ocr 重解析）；②MinerU 格式更新后刷新。
    会消耗 MinerU / VLM API。沿用当前 per-doc 父块粒度设置。
    """
    from app.services.pipeline_service import run_parse_pipeline

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, filename, source_format, upload_path, bound_file_path, status "
            "FROM documents WHERE doc_id=? AND kb_id=?",
            (doc_id, kb_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)
        if r["source_format"] in ("txt", "md"):
            raise HTTPException(status_code=400, detail="txt/md 文件无需解析")
        effective_path_str = r["upload_path"] or r["bound_file_path"] or ""
        if not effective_path_str or not Path(effective_path_str).exists():
            raise HTTPException(status_code=400, detail="原始文件不存在，无法重新解析")
        # 重置为 uploaded，让流水线重新走（run_parse_pipeline 内部 _purge_doc 幂等清旧数据）
        await db.execute(
            "UPDATE documents SET status='uploaded', updated_at=datetime('now') WHERE doc_id=?",
            (doc_id,),
        )
        await db.commit()
    finally:
        await db.close()

    bg.add_task(
        run_parse_pipeline,
        doc_id=r["doc_id"],
        kb_id=r["kb_id"],
        upload_path=Path(effective_path_str),
        filename=r["filename"],
        source_format=r["source_format"],
    )
    return {"detail": "重新解析任务已启动", "doc_id": doc_id}


@router.get("/{kb_id}/{doc_id}/stats", summary="获取文档解析/切片统计信息")
async def get_document_stats(kb_id: str, doc_id: str):
    """返回文档的解析与切片统计：父块数、子块数、资产数等（供属性面板使用）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, filename, source_format, file_size, page_count, "
            "status, parent_heading_level, created_at, updated_at "
            "FROM documents WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)

        # 父块 / 子块计数
        cur2 = await db.execute(
            "SELECT COUNT(*) FROM parent_chunks WHERE doc_id=?", (doc_id,)
        )
        pcnt_row = await cur2.fetchone()
        pcnt = pcnt_row[0] if pcnt_row else 0

        cur3 = await db.execute(
            "SELECT COUNT(*) FROM child_chunks WHERE doc_id=?", (doc_id,)
        )
        ccnt_row = await cur3.fetchone()
        ccnt = ccnt_row[0] if ccnt_row else 0

        # 资产计数
        cur4 = await db.execute(
            "SELECT COUNT(*) FROM assets WHERE doc_id=?", (doc_id,)
        )
        acnt_row = await cur4.fetchone()
        acnt = acnt_row[0] if acnt_row else 0

        # 自定义索引计数
        cur5 = await db.execute(
            "SELECT COUNT(*) FROM parent_extra_indexes WHERE doc_id=?", (doc_id,)
        )
        ecnt_row = await cur5.fetchone()
        ecnt = ecnt_row[0] if ecnt_row else 0

        return {
            "doc_id": r["doc_id"],
            "filename": r["filename"],
            "source_format": r["source_format"],
            "file_size": r["file_size"],
            "page_count": r["page_count"],
            "status": r["status"],
            "parent_heading_level": r["parent_heading_level"] or 1,
            "parent_chunks_count": pcnt,
            "child_chunks_count": ccnt,
            "assets_count": acnt,
            "extra_indexes_count": ecnt,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    finally:
        await db.close()


class RenameBody(BaseModel):
    new_name: str


@router.patch("/{kb_id}/{doc_id}/rename", summary="重命名文档")
async def rename_document(kb_id: str, doc_id: str, body: RenameBody):
    """重命名文档（仅改显示名称和磁盘文件，不改 relative_path）。"""
    new_name = body.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if "/" in new_name or "\\" in new_name:
        raise HTTPException(status_code=400, detail="文件名不能包含路径分隔符")

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, filename, upload_path, bound_file_path FROM documents "
            "WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)

        old_path = r["upload_path"] or r["bound_file_path"] or ""
        new_upload = old_path
        if old_path:
            old = Path(old_path)
            if old.exists():
                new_path = old.parent / new_name
                old.rename(new_path)
                new_upload = str(new_path)

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE documents SET filename=?, upload_path=?, bound_file_path=?, updated_at=? WHERE doc_id=?",
            (new_name, new_upload, new_upload, now, doc_id),
        )
        await db.commit()
        return {"detail": "已重命名", "new_name": new_name}
    finally:
        await db.close()


class CopyBody(BaseModel):
    target_kb_id: str | None = None


@router.post("/{kb_id}/{doc_id}/copy", summary="复制文档")
async def copy_document(kb_id: str, doc_id: str, body: CopyBody = CopyBody()):
    """复制文档到同 KB 或指定 KB（仅复制文件+元数据，不复制索引/向量）。"""
    target_kb = body.target_kb_id or kb_id

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, filename, source_format, file_size, upload_path, "
            "bound_file_path, relative_path, folder_category "
            "FROM documents WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)

        cur2 = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (target_kb,))
        if not await cur2.fetchone():
            raise HTTPException(status_code=404, detail="目标知识库不存在")

        new_doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        stem = Path(r["filename"]).stem
        suffix = Path(r["filename"]).suffix
        new_name = f"{stem}_副本{suffix}"

        new_upload = ""
        old_path = r["upload_path"] or r["bound_file_path"] or ""
        if old_path:
            old = Path(old_path)
            if old.exists():
                dest_dir = settings.upload_dir / target_kb / new_doc_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / new_name
                shutil.copy2(old, dest)
                new_upload = str(dest)

        await db.execute(
            """INSERT INTO documents
               (doc_id, kb_id, filename, relative_path, source_format, file_size,
                upload_path, folder_category, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,'uploaded',?,?)""",
            (new_doc_id, target_kb, new_name, r["relative_path"], r["source_format"],
             r["file_size"], new_upload, r["folder_category"], now, now),
        )
        await db.commit()
        return {"detail": "已复制", "new_doc_id": new_doc_id, "new_name": new_name}
    finally:
        await db.close()


class MoveBody(BaseModel):
    target_kb_id: str | None = None
    relative_path: str | None = None


@router.post("/{kb_id}/{doc_id}/move", summary="移动文档")
async def move_document(kb_id: str, doc_id: str, body: MoveBody):
    """移动文档到其他 KB 或修改 relative_path（子文件夹）。"""
    target_kb = body.target_kb_id or kb_id

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT doc_id, kb_id, filename, upload_path, bound_file_path, "
            "relative_path, source_format, file_size, folder_category "
            "FROM documents WHERE doc_id=? AND kb_id=?", (doc_id, kb_id)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在")
        r = dict(row)

        if target_kb != kb_id:
            cur2 = await db.execute("SELECT kb_id FROM knowledge_bases WHERE kb_id=?", (target_kb,))
            if not await cur2.fetchone():
                raise HTTPException(status_code=404, detail="目标知识库不存在")

        new_rel = body.relative_path or r["relative_path"]
        now = datetime.now(timezone.utc).isoformat()

        new_upload = r["upload_path"]
        old_path = r["upload_path"] or r["bound_file_path"] or ""
        if old_path and target_kb != r["kb_id"]:
            old = Path(old_path)
            if old.exists():
                dest_dir = settings.upload_dir / target_kb / r["doc_id"]
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / old.name
                shutil.move(str(old), str(dest))
                new_upload = str(dest)

        await db.execute(
            "UPDATE documents SET kb_id=?, relative_path=?, upload_path=?, bound_file_path=?, updated_at=? WHERE doc_id=?",
            (target_kb, new_rel, new_upload, new_upload, now, doc_id),
        )
        await db.commit()
        return {"detail": "已移动", "target_kb_id": target_kb}
    finally:
        await db.close()
