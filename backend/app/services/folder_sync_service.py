"""
文件夹绑定同步服务

将 KB 绑定到本地文件夹，扫描差异后自动登记新文件、标记消失文件。
.txt/.md 直接置为 text_only，其他格式置为 uploaded 等待用户手动触发解析。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException

from app.db.database import get_db

# 跳过的文件名或前缀
_SKIP_NAMES = {".git", ".DS_Store", "Thumbs.db", "__pycache__"}
_SKIP_PREFIXES = ("~$",)

# 音视频文件：不支持解析/索引，同步时跳过（用户可后续通过音视频转写功能接入）
_UNSUPPORTED_AUDIO_VIDEO_EXTS = frozenset({
    ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma",
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv",
})

_FORMAT_MAP = {
    ".pdf": "pdf", ".ppt": "pptx", ".pptx": "pptx",
    ".doc": "docx", ".docx": "docx",
    ".png": "png", ".jpg": "jpg", ".jpeg": "jpeg",
    ".txt": "txt", ".md": "md",
    ".xlsx": "xlsx", ".xls": "xlsx",
}


class SyncDiff(TypedDict):
    added: list[dict]
    removed: list[dict]
    unchanged: int


def _is_text_format(ext: str) -> bool:
    return ext.lower() in (".txt", ".md")


def _categorize(relative_path: str) -> str:
    """根据相对路径第一段映射 folder_category。"""
    parts = Path(relative_path).parts
    if not parts:
        return ""
    first = parts[0]
    if first == "课堂录音":
        filename = parts[-1] if len(parts) > 1 else ""
        if Path(filename).suffix.lower() == ".md" and "课堂要点" in filename:
            return "review_note"
        return "recording"
    if first == "课件":
        return "slides"
    if first == "作业":
        return "homework"
    if first == "通知":
        return "notice"
    return ""


def _detect_source_format(filename: str) -> str:
    return _FORMAT_MAP.get(Path(filename).suffix.lower(), "unknown")


async def scan_and_sync(kb_id: str) -> SyncDiff:
    """
    扫描 KB 绑定文件夹与 DB 做 diff：
    - 新文件 → INSERT（txt/md=text_only，其他=uploaded）
    - 磁盘消失 → status='missing'
    - 已消失后重新出现 → 恢复正常 status
    - 已存在无变化 → unchanged 计数
    幂等：同一文件不会重复登记。
    """
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT bound_folder_path FROM knowledge_bases WHERE kb_id=?", (kb_id,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="知识库不存在")

        folder_path = (dict(row).get("bound_folder_path") or "").strip()
        if not folder_path:
            raise HTTPException(status_code=400, detail="该知识库未绑定文件夹")

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"绑定文件夹不存在: {folder_path}")

        # 读取 DB 中已有的绑定记录
        cur = await db.execute(
            "SELECT doc_id, bound_file_path, status, source_format FROM documents "
            "WHERE kb_id=? AND bound_file_path != ''",
            (kb_id,),
        )
        db_records: dict[str, dict] = {
            dict(r)["bound_file_path"]: dict(r) for r in await cur.fetchall()
        }

        # 扫描磁盘
        disk_files: dict[str, Path] = {}
        for p in folder.rglob("*"):
            if not p.is_file():
                continue
            if p.stat().st_size == 0:
                continue
            name = p.name
            if name in _SKIP_NAMES:
                continue
            if any(name.startswith(px) for px in _SKIP_PREFIXES):
                continue
            # 跳过隐藏目录下的文件
            if any(part.startswith(".") for part in p.relative_to(folder).parts):
                continue
            # 跳过音视频文件（当前不支持，以后可通过转写接入）
            if p.suffix.lower() in _UNSUPPORTED_AUDIO_VIDEO_EXTS:
                continue
            disk_files[str(p)] = p

        added: list[dict] = []
        removed: list[dict] = []
        unchanged = 0
        now = datetime.now(timezone.utc).isoformat()

        # 新文件 or 重新出现的文件
        for abs_path_str, p in disk_files.items():
            if abs_path_str in db_records:
                rec = db_records[abs_path_str]
                if rec["status"] == "missing":
                    ext = p.suffix.lower()
                    restored = "text_only" if _is_text_format(ext) else "uploaded"
                    await db.execute(
                        "UPDATE documents SET status=?, updated_at=? WHERE doc_id=?",
                        (restored, now, rec["doc_id"]),
                    )
                unchanged += 1
            else:
                doc_id = str(uuid.uuid4())
                rel_path = str(p.relative_to(folder)).replace("\\", "/")
                category = _categorize(rel_path)
                ext = p.suffix.lower()
                source_format = _detect_source_format(p.name)
                status = "text_only" if _is_text_format(ext) else "uploaded"
                file_size = p.stat().st_size

                await db.execute(
                    """INSERT INTO documents
                       (doc_id, kb_id, filename, relative_path, source_format, file_size,
                        bound_file_path, folder_category, status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (doc_id, kb_id, p.name, rel_path, source_format, file_size,
                     abs_path_str, category, status, now, now),
                )
                await db.execute(
                    "UPDATE knowledge_bases SET file_count = file_count + 1, updated_at=? WHERE kb_id=?",
                    (now, kb_id),
                )
                added.append({
                    "doc_id": doc_id,
                    "filename": p.name,
                    "relative_path": rel_path,
                    "folder_category": category,
                    "source_format": source_format,
                    "status": status,
                })

        # 消失的文件
        for abs_path_str, rec in db_records.items():
            if abs_path_str not in disk_files and rec["status"] != "missing":
                await db.execute(
                    "UPDATE documents SET status='missing', updated_at=? WHERE doc_id=?",
                    (now, rec["doc_id"]),
                )
                removed.append({"doc_id": rec["doc_id"], "bound_file_path": abs_path_str})

        await db.commit()
        return SyncDiff(added=added, removed=removed, unchanged=unchanged)
    finally:
        await db.close()
