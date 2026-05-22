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

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

from app.db.database import get_db
from app.prompts import load_prompt
from app.services import conversation_service
from app.services.qa_service import stream_llm_completion

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
            "SELECT relative_path, folder_category FROM documents WHERE kb_id=? AND status != 'missing'",
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
        if cat == "recording":
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
            """SELECT doc_id, filename, relative_path, bound_file_path, upload_path, folder_category
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
        else:
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
    主入口：为指定日期的所有节次生成讲义（流式）。
    yield SSE 字符串（含 \\n\\n）。

    SSE 事件类型：
      section_start      — 开始生成某节（含 section_num、total_sections）
      thinking           — 思维链内容（含 section_num）
      delta              — 正文增量（含 section_num）
      section_done       — 某节生成完毕（含 message_id）
      all_done           — 所有节完成（含 conversation_id）
      error              — 错误
    """
    sections = await list_sections(kb_id, date)
    if not sections:
        yield _sse({"type": "error", "message": f"日期 {date} 下没有找到录音文件"})
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

    yield _sse({"type": "conversation_created", "conversation_id": conv_id,
                "total_sections": len(sections)})

    for idx, sec in enumerate(sections):
        section_num = sec["section_num"]
        yield _sse({"type": "section_start", "section_num": section_num,
                    "total_sections": len(sections)})

        # 读取录音文本
        try:
            txt_content = await read_section_text(sec["txt_path"])
        except FileNotFoundError as e:
            yield _sse({"type": "error", "message": str(e), "section_num": section_num})
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

        # 追加 user message
        user_msg_id = await conversation_service.append_message(
            conv_id, "user", user_content,
            metadata={"section_num": section_num},
        )

        # 构造完整 messages 历史
        all_msgs = await conversation_service.list_messages(conv_id)
        openai_msgs = [
            {"role": m["role"], "content": m["content"]}
            for m in all_msgs
            if m["role"] in ("user", "assistant", "system")
        ]

        # 流式生成
        accumulated_content: list[str] = []
        accumulated_thinking: list[str] = []

        async for evt in stream_llm_completion(openai_msgs, enable_thinking=enable_thinking):
            if evt["type"] == "thinking":
                accumulated_thinking.append(evt["content"])
                yield _sse({"type": "thinking", "content": evt["content"],
                            "section_num": section_num})
            elif evt["type"] == "delta":
                accumulated_content.append(evt["content"])
                yield _sse({"type": "delta", "content": evt["content"],
                            "section_num": section_num})
            elif evt["type"] == "error":
                yield _sse({"type": "error", "message": evt["message"],
                            "section_num": section_num})

        # 落库 assistant message
        asst_msg_id = await conversation_service.append_message(
            conv_id, "assistant",
            content="".join(accumulated_content),
            thinking="".join(accumulated_thinking),
            metadata={"section_num": section_num},
        )
        yield _sse({"type": "section_done", "section_num": section_num,
                    "message_id": asst_msg_id})

    yield _sse({"type": "all_done", "conversation_id": conv_id})


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
        pass  # 同步失败不影响保存结果

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


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
