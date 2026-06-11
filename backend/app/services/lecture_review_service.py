"""
课后复习服务（模块七）

核心流程：
  1. 扫描 KB 下的录音文件，按日期/节次组织
  2. 创建新 conversation（scenario=lecture_review）
  3. 对每节循环：构造提示词 + 读 txt → 流式生成讲义 → 持久化
  4. 支持保存讲义到磁盘（写回绑定文件夹）
  5. 支持加载已存在的讲义
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

from app.db.database import get_db
from app.prompts import load_prompt
from app.services import conversation_service

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"第(\d+)节")          # 匹配"第N节"，提取节次号
_NOTE_SUFFIX = "课堂要点.md"
_INVALID_WIN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe_filename(name: str) -> str:
    """Strip Windows-invalid filename characters."""
    return _INVALID_WIN_CHARS.sub("_", name).strip()


async def list_dates(kb_id: str) -> list[dict]:
    """
    扫描 KB 下 folder_category='recording' 的文档，
    按相对路径提取日期目录，返回 [{date, section_count, has_notes}, ...] 按日期升序。
    """
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT relative_path, folder_category, source_format FROM documents WHERE kb_id=? AND status != 'missing'",
            (kb_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

    date_info: dict[str, dict] = {}  # date_str -> {section_count, has_notes}
    for r in rows:
        rel = r["relative_path"].replace("\\", "/")
        parts = rel.split("/")
        # 期望结构：课堂录音/<date>/<filename>
        if len(parts) < 3 or parts[0] != "课堂录音":
            continue
        date_str = parts[1]
        if date_str not in date_info:
            date_info[date_str] = {"section_count": 0, "has_notes": False}
        cat = r["folder_category"]
        if cat == "recording" and r["source_format"] == "txt":
            # 只有 .txt 文件才计为一节（过滤音频源文件 m4a/mp3/flac 等）
            date_info[date_str]["section_count"] += 1
        elif cat == "review_note":
            date_info[date_str]["has_notes"] = True

    return sorted(
        [{"date": d, **info} for d, info in date_info.items()],
        key=lambda x: x["date"],
    )


async def list_sections(kb_id: str, date: str) -> list[dict]:
    """
    返回指定日期下的录音文件信息（按节次升序），
    格式：[{section_num, txt_doc_id, txt_path, note_doc_id, note_path}, ...]
    """
    db = await get_db()
    try:
        prefix = f"课堂录音/{date}/"
        cur = await db.execute(
            """SELECT doc_id, filename, relative_path, bound_file_path, upload_path,
                      folder_category, source_format
               FROM documents
               WHERE kb_id=? AND relative_path LIKE ? AND status != 'missing'""",
            (kb_id, prefix + "%"),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

    recordings: list[tuple[int, dict]] = []
    notes: dict[int, dict] = {}

    for r in rows:
        m = _SECTION_RE.search(r["filename"])
        if not m:
            continue
        section_num = int(m.group(1))
        path = r["bound_file_path"] or r["upload_path"] or ""
        if r["folder_category"] == "review_note":
            notes[section_num] = {"note_doc_id": r["doc_id"], "note_path": path}
        elif r["folder_category"] == "recording" and r["source_format"] == "txt":
            # 只识别 .txt 录音转写文件（过滤 .m4a/.mp3/.flac 等音频源文件）
            recordings.append((section_num, {"txt_doc_id": r["doc_id"], "txt_path": path}))

    recordings.sort(key=lambda x: x[0])
    return [
        {
            "section_num": sec_num,
            "txt_doc_id": info["txt_doc_id"],
            "txt_path": info["txt_path"],
            "note_doc_id": notes.get(sec_num, {}).get("note_doc_id"),
            "note_path": notes.get(sec_num, {}).get("note_path"),
        }
        for sec_num, info in recordings
    ]


async def read_section_text(txt_path: str) -> str:
    """读取 .txt 文件内容（自动处理 BOM）。"""
    p = Path(txt_path)
    if not p.exists():
        raise FileNotFoundError(f"录音文件不存在: {txt_path}")
    return p.read_text(encoding="utf-8-sig", errors="replace")


async def generate_notes_streaming(
    kb_id: str,
    date: str,
    *,
    course_name: str | None = None,
    time_descriptor: str = "",
    user_identity: str = "",
    enable_thinking: bool = False,
) -> AsyncIterator[str]:
    """
    主入口：为指定日期的所有节次生成讲义（流式，**统一 SSE 词汇**）。

    每节通过 conversation_service.stream_turn 生成：录音转写作为 hidden user
    message（进入 LLM 上下文但前端不渲染），assistant message 打
    metadata={"kind":"section","section_num":N}。所有节共享同一 conversation 上下文。

    事件序列：
      conversation {conversation_id, total_sections}
      （每节）message_start(assistant,{kind:section,section_num}) / thinking / delta / message_end
      done {conversation_id}
      error {message[, section_num]}
    """
    sections = await list_sections(kb_id, date)
    if not sections:
        yield conversation_service.sse_line(
            {"type": "error", "message": f"日期 {date} 下没有找到录音文件"}
        )
        return

    # 从 KB 名称获取课程名
    if not course_name:
        db = await get_db()
        try:
            cur = await db.execute("SELECT name FROM knowledge_bases WHERE kb_id=?", (kb_id,))
            row = await cur.fetchone()
            course_name = dict(row)["name"] if row else ""
        finally:
            await db.close()

    # 创建 conversation
    meta = {
        "date": date,
        "course_name": course_name,
        "time_descriptor": time_descriptor,
        "user_identity": user_identity,
        "section_files": [s["txt_path"] for s in sections],
    }
    conv_id = await conversation_service.create_conversation(
        kb_id=kb_id,
        scenario="lecture_review",
        title=f"{course_name} {date} 课后复习",
        metadata=meta,
        enable_thinking=enable_thinking,
    )

    yield conversation_service.sse_line(
        {"type": "conversation", "conversation_id": conv_id, "total_sections": len(sections)}
    )

    for idx, sec in enumerate(sections):
        section_num = sec["section_num"]

        # 读取录音文本
        try:
            txt_content = await read_section_text(sec["txt_path"])
        except FileNotFoundError as e:
            yield conversation_service.sse_line(
                {"type": "error", "message": str(e), "section_num": section_num}
            )
            continue

        # 构造 prompt
        if idx == 0:
            prompt_text = load_prompt(
                "lecture_review_section_first",
                user_identity=user_identity or "北邮通信工程专业大二下",
                time_descriptor=time_descriptor or "课程",
                course_name=course_name,
                section_index=section_num,
            )
        else:
            prompt_text = load_prompt(
                "lecture_review_section_subsequent",
                time_descriptor=time_descriptor or "课程",
                course_name=course_name,
                section_index=section_num,
            )

        user_content = f"{prompt_text}\n\n【录音转写】\n{txt_content}"

        async for chunk in conversation_service.stream_turn(
            conv_id,
            user_content=user_content,
            hidden_user=True,
            assistant_metadata={"kind": "section", "section_num": section_num},
        ):
            yield chunk

    # 在所有节生成成功后，自动保存到本地文件夹并同步登记
    try:
        await save_notes_to_disk(kb_id, conv_id)
    except Exception as e:
        logger.error("Auto-saving lecture notes to disk failed: %s", e, exc_info=True)

    yield conversation_service.sse_line({"type": "done", "conversation_id": conv_id})


async def save_notes_to_disk(kb_id: str, conversation_id: str) -> list[dict]:
    """
    从 conversation 提取 assistant messages（按 section_num），
    写入 课堂录音/{date}/{course_name}{date}第NN节课堂要点.md。
    写完后触发文件夹同步让新文件登记到 DB。
    返回 [{section_num, path}, ...]。
    """
    from app.services import folder_sync_service

    conv = await conversation_service.get_conversation(conversation_id)
    if not conv:
        raise ValueError("会话不存在")

    meta = conv.get("metadata") or {}
    date = meta.get("date", "")
    course_name = meta.get("course_name", "")

    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT bound_folder_path FROM knowledge_bases WHERE kb_id=?", (kb_id,)
        )
        row = await cur.fetchone()
        folder_path = dict(row).get("bound_folder_path", "") if row else ""
    finally:
        await db.close()

    if not folder_path or not Path(folder_path).exists():
        raise ValueError("该知识库未绑定文件夹或文件夹不存在")

    msgs = await conversation_service.list_messages(conversation_id)
    saved: list[dict] = []

    for m in msgs:
        if m["role"] != "assistant":
            continue
        section_num = (m.get("metadata") or {}).get("section_num")
        if section_num is None:
            continue
        filename = f"{_safe_filename(course_name)}{date}第{section_num:02d}节{_NOTE_SUFFIX}"
        target_dir = Path(folder_path) / "课堂录音" / date
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        target_path.write_text(m["content"], encoding="utf-8")
        saved.append({"section_num": section_num, "path": str(target_path)})

    # 触发同步让新文件登记到 DB
    try:
        await folder_sync_service.scan_and_sync(kb_id)
    except Exception:
        logger.warning("讲义保存后文件夹同步失败 kb=%s", kb_id, exc_info=True)

    # 自动索引生成的讲义 .md（录音 .txt 永不索引），供问答检索高质量讲义
    from app.services import text_index_service
    for item in saved:
        try:
            db2 = await get_db()
            try:
                cur = await db2.execute(
                    "SELECT doc_id, source_format, folder_category FROM documents "
                    "WHERE kb_id=? AND bound_file_path=? AND status!='missing'",
                    (kb_id, item["path"]),
                )
                row = await cur.fetchone()
            finally:
                await db2.close()
            if not row:
                continue
            r = dict(row)
            if text_index_service.is_indexable_text(r.get("folder_category"), r.get("source_format")):
                await text_index_service.index_text_document(
                    r["doc_id"], item["path"], source_format=r["source_format"]
                )
        except Exception:
            logger.warning("讲义自动索引失败: %s", item.get("path"), exc_info=True)

    return saved


async def load_existing_notes(kb_id: str, date: str) -> list[dict]:
    """
    读取该日期下已存在的 *课堂要点.md 文件内容。
    返回 [{section_num, path, content_md}, ...] 按节次升序。
    """
    db = await get_db()
    try:
        prefix = f"课堂录音/{date}/"
        cur = await db.execute(
            """SELECT doc_id, filename, bound_file_path, upload_path
               FROM documents
               WHERE kb_id=? AND folder_category='review_note'
                     AND relative_path LIKE ? AND status != 'missing'""",
            (kb_id, prefix + "%"),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

    results = []
    for r in rows:
        m = _SECTION_RE.search(r["filename"])
        if not m:
            continue
        section_num = int(m.group(1))
        path_str = r["bound_file_path"] or r["upload_path"] or ""
        p = Path(path_str)
        content = p.read_text(encoding="utf-8-sig", errors="replace") if p.exists() else ""
        results.append({"section_num": section_num, "path": path_str, "content_md": content})

    return sorted(results, key=lambda x: x["section_num"])
