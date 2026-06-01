"""
test_v120.py — v1.2.0 新功能端到端测试

覆盖：
  1. 文件夹绑定（bound_folder_path 字段）
  2. 文件夹同步（sync-folder 端点）
  3. txt/md 文件上传 → text_only 状态，无需解析
  4. raw-text 端点
  5. 多轮会话 CRUD
  6. 会话 Fork
  7. 流式 send（SSE 事件收集）
  8. 模块九：课程信息卡片（GET → 404 → generate → GET → delete）
  9. 模块九：课程信息聊天（SSE）
  10. 模块七：日期/节次列表、notes 列表（空）
  11. 提示词管理（list + reload）

前置条件：
  - 无需外部 API（LLM 调用被 mock）
  - 绑定文件夹测试使用 tempfile

运行：
  cd backend
  uv run python test_v120.py
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from app.main import app
from app.db.database import init_db
from app.db.qdrant_client import init_qdrant
from app.config import settings

settings.ensure_dirs()

PASS = "[PASS]"
FAIL = "[FAIL]"
_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    icon = PASS if ok else FAIL
    msg = f"  {icon} {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


# ──────────────────────────────────────────────────────────────
# 辅助：收集 SSE 事件
# ──────────────────────────────────────────────────────────────

def _collect_sse(response_text: str) -> list[dict]:
    events = []
    for line in response_text.splitlines():
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:].strip()))
            except Exception:
                pass
    return events


# ──────────────────────────────────────────────────────────────
# 切片回归：长句不得卡死（v1.3.0 修复事件循环冻结的根因）
# ──────────────────────────────────────────────────────────────

def _test_chunk_windows() -> None:
    print("\n[0] 切片回归：_build_windows 长句不死循环")
    from app.chunkers.child_chunker import _build_windows

    max_chars, min_chars, overlap = 500, 300, 75
    # 致命用例：句长 480 ∈ (max-overlap, max]，旧实现会无限重试同一句卡死事件循环
    killer = ["啊" * 480, "啊" * 480, "啊" * 480]
    w = _build_windows(killer, max_chars, min_chars, overlap)
    _record("长句不卡死且产出窗口", len(w) > 0)
    _record("窗口长度有界", all(len(x) <= max_chars + overlap for x in w))

    # 单句远超上限：硬切多块
    w2 = _build_windows(["b" * 1300], max_chars, min_chars, overlap)
    _record("超长单句被硬切为多块", len(w2) >= 3)

    # 正常短句仍合并
    w3 = _build_windows(["第一句。", "第二句。", "第三句。"], max_chars, min_chars, overlap)
    _record("短句合并为单窗口", len(w3) == 1)


# ──────────────────────────────────────────────────────────────
# 主测试
# ──────────────────────────────────────────────────────────────

async def run_all_tests() -> None:
    await init_db()
    init_qdrant()
    _test_chunk_windows()

    # Mock LLM 流式输出（避免真实 API 调用）
    async def _mock_stream_llm(messages, *, enable_thinking=False, model=None):
        yield {"type": "delta", "content": "这是测试回答。"}
        yield {"type": "end"}

    mock_pipeline = AsyncMock(return_value="mock-task-id")
    transport = httpx.ASGITransport(app=app)

    # Mock 嵌入，让文本索引（讲义 .md）在无 API key 下也能跑通（仍写真实本地 Qdrant）
    async def _mock_embed(texts, text_type="document"):
        return [[0.0] * 1024 for _ in texts]

    with (
        patch("app.services.pipeline_service.run_parse_pipeline", mock_pipeline),
        patch("app.services.qa_service.stream_llm_completion", _mock_stream_llm),
        patch("app.services.embedding_service.embed_texts", _mock_embed),
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            await _test_folder_binding(c)
            kb_id = await _test_folder_sync(c)
            await _test_txt_upload(c, kb_id)
            await _test_conversations(c, kb_id)
            await _test_course_info_endpoints(c, kb_id)
            await _test_deadline_recompute(kb_id)
            await _test_review_endpoints(c, kb_id)
            await _test_prompts(c)
            await _cleanup(c, kb_id)


async def _test_folder_binding(c: httpx.AsyncClient) -> None:
    print("\n[1] KB 创建（含 bound_folder_path）")
    # bound_folder_path 可以是空字符串
    r = await c.post("/api/kb", json={"name": "v120 test KB", "kb_type": "course", "bound_folder_path": ""})
    _record("POST /api/kb with bound_folder_path", r.status_code == 200)
    data = r.json()
    _record("response has kb_id", "kb_id" in data)
    _record("bound_folder_path field present", "bound_folder_path" in data)
    _record("bound_folder_path defaults empty", data.get("bound_folder_path") == "")
    # cleanup immediately
    await c.delete(f"/api/kb/{data['kb_id']}")


async def _test_folder_sync(c: httpx.AsyncClient) -> str:
    print("\n[2] 文件夹同步")
    # 创建临时目录模拟课程文件夹结构
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建目录结构
        rec_dir = Path(tmpdir) / "课堂录音" / "260101"
        rec_dir.mkdir(parents=True)
        (rec_dir / "数学物理方法260101第01节.txt").write_text("第一节课内容", encoding="utf-8")
        (rec_dir / "数学物理方法260101第02节.txt").write_text("第二节课内容", encoding="utf-8")

        r = await c.post("/api/kb", json={
            "name": "同步测试课程",
            "kb_type": "course",
            "bound_folder_path": tmpdir,
        })
        _record("POST /api/kb (with folder)", r.status_code == 200)
        kb_id = r.json()["kb_id"]

        # 同步
        r2 = await c.post(f"/api/kb/{kb_id}/sync-folder")
        _record("POST /api/kb/{id}/sync-folder → 200", r2.status_code == 200)
        diff = r2.json()
        _record("diff has added/removed/unchanged", all(k in diff for k in ("added", "removed", "unchanged")))
        _record("2 files added", len(diff.get("added", [])) == 2)

        # 验证文档状态
        r3 = await c.get(f"/api/documents/{kb_id}")
        docs = r3.json()["items"]
        _record("2 documents registered", len(docs) == 2)
        statuses = {d["status"] for d in docs}
        _record("all docs text_only", statuses == {"text_only"})
        categories = {d["folder_category"] for d in docs}
        _record("all folder_category=recording", categories == {"recording"})

        # 幂等测试（再同步一次应该 unchanged=2）
        r4 = await c.post(f"/api/kb/{kb_id}/sync-folder")
        diff2 = r4.json()
        _record("re-sync is idempotent (unchanged=2)", diff2.get("unchanged") == 2 and len(diff2.get("added", [])) == 0)

        # 删除一个文件，再同步 → missing
        (rec_dir / "数学物理方法260101第02节.txt").unlink()
        r5 = await c.post(f"/api/kb/{kb_id}/sync-folder")
        diff3 = r5.json()
        _record("removed 1 file → removed count=1", len(diff3.get("removed", [])) == 1)

        # 验证 missing 状态
        r6 = await c.get(f"/api/documents/{kb_id}")
        docs2 = r6.json()["items"]
        statuses2 = {d["status"] for d in docs2}
        _record("one doc becomes missing", "missing" in statuses2)

    # tmpdir 已销毁，但 KB 还在（bound_folder_path 指向不存在路径）
    # 重新创建 KB（不绑定）以备后续测试
    r7 = await c.post("/api/kb", json={"name": "v120-main-test", "kb_type": "course"})
    main_kb_id = r7.json()["kb_id"]
    await c.delete(f"/api/kb/{kb_id}")   # 清理临时 KB
    return main_kb_id


async def _test_txt_upload(c: httpx.AsyncClient, kb_id: str) -> None:
    print("\n[3] TXT/MD 上传与 raw-text")
    txt_content = "这是一段测试文本内容。\n第二行。"
    files = {"file": ("test_note.txt", io.BytesIO(txt_content.encode()), "text/plain")}
    r = await c.post(f"/api/documents/{kb_id}/upload", files=files)
    _record("POST upload .txt → 200", r.status_code == 200)
    doc = r.json()
    doc_id = doc["doc_id"]
    _record("status=text_only", doc.get("status") == "text_only")
    _record("source_format=txt", doc.get("source_format") == "txt")

    # txt 不可触发解析
    r2 = await c.post(f"/api/documents/{kb_id}/{doc_id}/parse")
    _record("parse txt → 400", r2.status_code == 400)

    # raw-text
    r3 = await c.get(f"/api/documents/{kb_id}/{doc_id}/raw-text")
    _record("GET raw-text → 200", r3.status_code == 200)
    data = r3.json()
    _record("raw-text has doc_id and text", "doc_id" in data and "text" in data)
    _record("text content correct", txt_content in data.get("text", ""))


async def _test_conversations(c: httpx.AsyncClient, kb_id: str) -> None:
    print("\n[4] 多轮会话 CRUD + Fork")

    # 创建
    r = await c.post("/api/conversations", json={
        "kb_id": kb_id, "scenario": "general",
        "title": "测试会话", "enable_thinking": False,
    })
    _record("POST /api/conversations → 200", r.status_code == 200)
    conv = r.json()
    conv_id = conv["conversation_id"]
    _record("response has conversation_id", "conversation_id" in conv)
    _record("messages list empty", conv.get("messages") == [])

    # GET
    r2 = await c.get(f"/api/conversations/{conv_id}")
    _record("GET /api/conversations/{id} → 200", r2.status_code == 200)

    # LIST
    r3 = await c.get(f"/api/conversations?kb_id={kb_id}")
    _record("GET /api/conversations?kb_id → 200", r3.status_code == 200)
    convs = r3.json()
    _record("list returns array with our conv", isinstance(convs, list) and any(c["conversation_id"] == conv_id for c in convs))

    # PATCH
    r4 = await c.patch(f"/api/conversations/{conv_id}", json={"title": "更新标题"})
    _record("PATCH /api/conversations/{id} → 200", r4.status_code == 200)

    # SEND (SSE mock)
    r5 = await c.post(f"/api/conversations/{conv_id}/send",
                      json={"content": "你好"})
    _record("POST /api/conversations/{id}/send → 200", r5.status_code == 200)
    events = _collect_sse(r5.text)
    types = {e.get("type") for e in events}
    _record("SSE has delta event", "delta" in types)
    _record("SSE has done event", "done" in types)
    _record("SSE has conversation event", "conversation" in types)
    _record("SSE has message_start", "message_start" in types)
    _record("SSE has message_end", "message_end" in types)

    # Verify messages persisted
    r6 = await c.get(f"/api/conversations/{conv_id}")
    msgs = r6.json().get("messages", [])
    _record("messages persisted (user+assistant)", len(msgs) >= 2)
    roles = {m["role"] for m in msgs}
    _record("has user and assistant messages", {"user", "assistant"}.issubset(roles))

    # Second message (multi-turn)
    r7 = await c.post(f"/api/conversations/{conv_id}/send", json={"content": "继续"})
    _record("second send → 200", r7.status_code == 200)

    # Fork
    first_asst = next((m["message_id"] for m in msgs if m["role"] == "assistant"), None)
    if first_asst:
        r8 = await c.post(f"/api/conversations/{conv_id}/fork",
                          json={"fork_after_message_id": first_asst, "new_title": "fork测试"})
        _record("POST /api/conversations/{id}/fork → 200", r8.status_code == 200)
        forked = r8.json()
        _record("fork has conversation_id", "conversation_id" in forked)
        new_conv_id = forked["conversation_id"]
        _record("fork has messages", len(forked.get("messages", [])) > 0)

        # Original conversation unchanged
        r9 = await c.get(f"/api/conversations/{conv_id}")
        orig_msgs = r9.json().get("messages", [])
        _record("original conv still intact", len(orig_msgs) >= 2)

        # Delete forked
        await c.delete(f"/api/conversations/{new_conv_id}")

    # DELETE
    r10 = await c.delete(f"/api/conversations/{conv_id}")
    _record("DELETE /api/conversations/{id} → 200", r10.status_code == 200)
    r11 = await c.get(f"/api/conversations/{conv_id}")
    _record("GET after delete → 404", r11.status_code == 404)


async def _test_course_info_endpoints(c: httpx.AsyncClient, kb_id: str) -> None:
    print("\n[5] 模块九：课程信息端点")

    # GET before generate → 404-like
    r = await c.get(f"/api/course-info/{kb_id}")
    _record("GET before generate → error", r.status_code in (404, 422))

    # Mock generate_card to return a fake card
    fake_card = {
        "kb_id": kb_id,
        "course_name": "测试课程",
        "instructor": "张教授",
        "contact": "zhang@bupt.edu.cn",
        "assessment": {"exam_ratio": 0.6, "hw_ratio": 0.3, "attendance_ratio": 0.1, "description": ""},
        "deadlines": [{"name": "实验报告", "date_text": "2026-06-10", "description": ""}],
        "important_notes": "注意提前准备",
        "deadlines_normalized": json.dumps([{
            "name": "实验报告", "date": "2026-06-10", "days_left": 19, "description": ""
        }]),
    }

    with patch("app.services.course_info_service.generate_card", AsyncMock(return_value=fake_card)):
        r2 = await c.post(f"/api/course-info/{kb_id}/generate")
        _record("POST /api/course-info/{id}/generate → 200", r2.status_code == 200)
        card = r2.json()
        _record("card has course_name", "course_name" in card)
        _record("card has instructor", card.get("instructor") == "张教授")

    # GET after generate (real DB)
    with patch("app.services.course_info_service.get_card", AsyncMock(return_value=fake_card)):
        r3 = await c.get(f"/api/course-info/{kb_id}")
        _record("GET /api/course-info/{id} → 200", r3.status_code == 200)

    # upcoming-deadlines
    with patch("app.services.course_info_service.upcoming_deadlines",
               AsyncMock(return_value=[{"name": "实验报告", "days_left": 5}])):
        r4 = await c.get(f"/api/course-info/{kb_id}/upcoming-deadlines")
        _record("GET upcoming-deadlines → 200", r4.status_code == 200)

    # Chat (SSE)
    with patch("app.services.course_info_service.get_card", AsyncMock(return_value=fake_card)):
        r5 = await c.post(f"/api/course-info/{kb_id}/chat",
                          json={"content": "考试怎么安排？"})
        _record("POST /api/course-info/{id}/chat → 200", r5.status_code == 200)
        events = _collect_sse(r5.text)
        types = {e.get("type") for e in events}
        _record("chat SSE has delta", "delta" in types)

    # Delete
    r6 = await c.delete(f"/api/course-info/{kb_id}")
    _record("DELETE /api/course-info/{id} → 200", r6.status_code == 200)


async def _test_deadline_recompute(kb_id: str) -> None:
    """回归：days_left 必须按当天从 ISO date 实时重算，而非沿用入库时的陈旧值。

    bug：卡片在生成日算好 days_left 入库，之后 banner/卡片一直显示过期天数；
    修复后 get_card 读取时按当天从权威 ISO `date` 重算。
    """
    print("\n[5b] 模块九：days_left 实时重算（回归）")
    from datetime import date, timedelta

    from app.db.database import get_db
    from app.services import course_info_service

    today = date.today()
    future = (today + timedelta(days=5)).isoformat()
    past = (today - timedelta(days=3)).isoformat()
    # 故意写入陈旧/错误的 days_left；ISO date 才是权威来源
    normalized = [
        {"name": "未来DL", "date": future, "days_left": 999, "description": ""},
        {"name": "已过DL", "date": past, "days_left": 999, "description": ""},
        {"name": "无日期DL", "date": "", "days_left": None, "description": ""},
    ]

    async def _reset_card(rows: str | None) -> None:
        db = await get_db()
        try:
            await db.execute("DELETE FROM course_info_cards WHERE kb_id=?", (kb_id,))
            if rows is not None:
                await db.execute(
                    """INSERT INTO course_info_cards
                       (card_id, kb_id, course_name, instructor, contact, assessment,
                        deadlines, important_notes, deadlines_normalized, source_doc_ids,
                        created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("regtest-card", kb_id, "回归课程", "", "", "{}",
                     "[]", "", rows, "[]",
                     "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
                )
            await db.commit()
        finally:
            await db.close()

    await _reset_card(json.dumps(normalized))
    card = await course_info_service.get_card(kb_id)
    dls = {d["name"]: d["days_left"] for d in (card or {}).get("deadlines_normalized", [])}
    _record("未来DL days_left 重算为 5", dls.get("未来DL") == 5, f"got {dls.get('未来DL')}")
    _record("已过DL days_left 重算为 -3", dls.get("已过DL") == -3, f"got {dls.get('已过DL')}")
    _record("无日期DL days_left 保持 None", dls.get("无日期DL") is None)

    upcoming = await course_info_service.upcoming_deadlines(kb_id, within_days=7)
    names = {d["name"] for d in upcoming}
    _record("upcoming 含未来7天内DL", "未来DL" in names)
    _record("upcoming 排除已过期DL", "已过DL" not in names)

    await _reset_card(None)  # 清理回归数据


async def _test_review_endpoints(c: httpx.AsyncClient, kb_id: str) -> None:
    print("\n[6] 模块七：课后复习端点")

    # list_dates (empty KB → empty list)
    r = await c.get(f"/api/review/{kb_id}/dates")
    _record("GET /api/review/{id}/dates → 200", r.status_code == 200)
    data = r.json()
    _record("dates returns list", isinstance(data.get("dates"), list))

    # list_sections (no documents → empty)
    r2 = await c.get(f"/api/review/{kb_id}/sections?date=260101")
    _record("GET /api/review/{id}/sections → 200", r2.status_code == 200)
    _record("sections returns list", isinstance(r2.json().get("sections"), list))

    # notes endpoint (empty)
    r3 = await c.get(f"/api/review/{kb_id}/notes?date=260101")
    _record("GET /api/review/{id}/notes → 200", r3.status_code == 200)
    _record("notes returns list", isinstance(r3.json().get("notes"), list))

    # conversations (empty)
    r4 = await c.get(f"/api/review/{kb_id}/conversations")
    _record("GET /api/review/{id}/conversations → 200", r4.status_code == 200)
    _record("conversations returns list", isinstance(r4.json().get("conversations"), list))

    # generate → 404 (no sections)
    r5 = await c.post(f"/api/review/{kb_id}/generate",
                      json={"date": "260101", "time_descriptor": "下午2节", "user_identity": "test"})
    _record("POST generate without sections → 404", r5.status_code == 404)

    # Full flow: sync folder → generate → save-notes → load-notes
    print("\n[6b] 模块七：完整流程（sync→generate→save→load）")
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建录音转写 txt 文件，同时模拟用户把音频源文件也放在同一目录
        rec_dir = Path(tmpdir) / "课堂录音" / "260505"
        rec_dir.mkdir(parents=True)
        txt1 = rec_dir / "测试课程260505第01节.txt"
        txt2 = rec_dir / "测试课程260505第02节.txt"
        # 模拟音频源文件（m4a/mp3），测试不被计入节次
        (rec_dir / "测试课程260505第01节.m4a").write_bytes(b"\x00\x01fake_audio")
        (rec_dir / "测试课程260505第02节.mp3").write_bytes(b"\x00\x01fake_audio")
        txt1.write_text("这是第一节课的录音转写内容，包含一些知识点。", encoding="utf-8")
        txt2.write_text("这是第二节课的录音转写内容，包含另一些知识点。", encoding="utf-8")

        # 创建绑定文件夹的 KB
        r_kb = await c.post("/api/kb", json={
            "name": "模七完整测试",
            "kb_type": "course",
            "bound_folder_path": tmpdir,
        })
        _record("创建绑定 KB → 200", r_kb.status_code == 200)
        review_kb_id = r_kb.json()["kb_id"]

        # 同步文件夹
        r_sync = await c.post(f"/api/kb/{review_kb_id}/sync-folder")
        _record("同步文件夹 → 200", r_sync.status_code == 200)
        diff = r_sync.json()
        _record("4个文件被同步（2 txt + 2 音频）", len(diff.get("added", [])) == 4)

        # 检查日期
        r_dates = await c.get(f"/api/review/{review_kb_id}/dates")
        dates_list = r_dates.json().get("dates", [])
        _record("dates 包含 260505", any(d["date"] == "260505" for d in dates_list))

        # 检查节次（音频文件不应被计入，只有 .txt 文件才算一节）
        r_secs = await c.get(f"/api/review/{review_kb_id}/sections?date=260505")
        secs = r_secs.json().get("sections", [])
        _record("sections 有 2 节（音频文件被过滤）", len(secs) == 2)

        # 检查 dates 里的 section_count 也是 2（不是 4）
        r_dates_check = await c.get(f"/api/review/{review_kb_id}/dates")
        dates_check = r_dates_check.json().get("dates", [])
        date_260505_check = next((d for d in dates_check if d["date"] == "260505"), None)
        _record("date section_count=2（音频文件不被计数）",
                date_260505_check is not None and date_260505_check.get("section_count") == 2)

        # 流式生成（mock LLM）
        r_gen = await c.post(f"/api/review/{review_kb_id}/generate",
                             json={"date": "260505", "time_descriptor": "下午2节",
                                   "user_identity": "北邮大二", "enable_thinking": False})
        _record("generate → 200 (SSE)", r_gen.status_code == 200)
        events = _collect_sse(r_gen.text)
        event_types = {e.get("type") for e in events}
        _record("generate 有 conversation 事件", "conversation" in event_types)
        _record("generate 有 message_start 事件", "message_start" in event_types)
        _record("generate 有 message_end 事件", "message_end" in event_types)
        _record("generate 有 done 事件", "done" in event_types)
        # 统一词汇：每节是一个 assistant message_start，section 元数据在 metadata
        sec_starts = [e for e in events if e.get("type") == "message_start" and e.get("role") == "assistant"]
        _record("有 2 个 section 的 assistant message_start", len(sec_starts) == 2)
        _record("section message_start 带 kind=section 元数据",
                all((e.get("metadata") or {}).get("kind") == "section" for e in sec_starts))

        # 拿到 conversation_id
        conv_ev = next((e for e in events if e.get("type") == "conversation"), None)
        _record("conversation 事件含 conversation_id", conv_ev is not None and "conversation_id" in conv_ev)
        gen_conv_id = conv_ev["conversation_id"] if conv_ev else None

        if gen_conv_id:
            # 保存讲义到磁盘
            r_save = await c.post(f"/api/review/{review_kb_id}/save-notes",
                                   json={"conversation_id": gen_conv_id})
            _record("save-notes → 200", r_save.status_code == 200)
            saved = r_save.json().get("saved", [])
            _record("save 返回已保存列表", isinstance(saved, list) and len(saved) > 0)

            # 加载已保存讲义
            r_notes = await c.get(f"/api/review/{review_kb_id}/notes?date=260505")
            _record("load notes after save → 200", r_notes.status_code == 200)
            notes = r_notes.json().get("notes", [])
            _record("notes 非空", len(notes) > 0)
            _record("notes 有 content_md", all("content_md" in n for n in notes))

            # Phase 2 / 问题3：保存后讲义 .md 自动索引；录音 .txt 永不索引
            r_docs = await c.get(f"/api/documents/{review_kb_id}")
            docs_list = r_docs.json().get("items", [])
            note_doc = next((d for d in docs_list if d.get("folder_category") == "review_note"), None)
            _record("讲义 .md 已登记", note_doc is not None)
            if note_doc:
                _record("讲义 .md 保存后自动索引 (status=indexed)", note_doc.get("status") == "indexed")
            rec_txt = next((d for d in docs_list
                            if d.get("folder_category") == "recording" and d.get("source_format") == "txt"), None)
            _record("录音 .txt 不被索引（保持 text_only）",
                    rec_txt is not None and rec_txt.get("status") == "text_only")
            if rec_txt:
                r_idx_rec = await c.post(f"/api/documents/{review_kb_id}/{rec_txt['doc_id']}/index-text")
                _record("录音 .txt index-text → 400（拒绝索引）", r_idx_rec.status_code == 400)
            if note_doc:
                r_idx_note = await c.post(f"/api/documents/{review_kb_id}/{note_doc['doc_id']}/index-text")
                _record("讲义 .md index-text → 200", r_idx_note.status_code == 200)

            # 追问 followup
            r_followup = await c.post(f"/api/review/{review_kb_id}/followup",
                                       json={"conversation_id": gen_conv_id, "content": "帮我总结一下"})
            _record("followup → 200", r_followup.status_code == 200)
            fup_events = _collect_sse(r_followup.text)
            fup_types = {e.get("type") for e in fup_events}
            _record("followup SSE has delta", "delta" in fup_types)
            _record("followup SSE has done", "done" in fup_types)
            # 追问消息也带 message_id（可 fork）
            fup_ends = [e for e in fup_events if e.get("type") == "message_end"]
            _record("followup assistant message 有 message_id（可 fork）",
                    len(fup_ends) > 0 and all("message_id" in e for e in fup_ends))

        # 日期有 has_notes 标记
        r_dates2 = await c.get(f"/api/review/{review_kb_id}/dates")
        dates2 = r_dates2.json().get("dates", [])
        date_260505 = next((d for d in dates2 if d["date"] == "260505"), None)
        _record("260505 日期 has_notes=True", date_260505 is not None and date_260505.get("has_notes") is True)

        # 清理
        await c.delete(f"/api/kb/{review_kb_id}")


async def _test_prompts(c: httpx.AsyncClient) -> None:
    print("\n[7] 提示词管理")
    r = await c.get("/api/settings/prompts")
    _record("GET /api/settings/prompts → 200", r.status_code == 200)
    data = r.json()
    _record("response has prompts key", "prompts" in data)
    prompts = data.get("prompts", {})
    _record("5 prompts loaded", len(prompts) == 5)
    expected = {
        "lecture_review_section_first",
        "lecture_review_section_subsequent",
        "lecture_review_followup_system",
        "course_info_extract_system",
        "course_info_chat_system",
    }
    _record("all expected prompts present", expected.issubset(prompts.keys()))

    r2 = await c.post("/api/settings/prompts/reload")
    _record("POST /api/settings/prompts/reload → 200", r2.status_code == 200)
    _record("reload returns count", "count" in r2.json())


async def _cleanup(c: httpx.AsyncClient, kb_id: str) -> None:
    await c.delete(f"/api/kb/{kb_id}")


# ──────────────────────────────────────────────────────────────

async def main() -> None:
    import os, sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        try: _sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass
    print("=" * 58)
    print("  Mini-NotebookLM  v1.2.0  New Feature Tests")
    print("=" * 58)

    await run_all_tests()

    print("\n" + "=" * 58)
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    if failed:
        print(f"  结果：{passed}/{total} 通过，{failed} 失败")
        for name, ok, detail in _results:
            if not ok:
                print(f"  {FAIL} {name} {detail}")
        sys.exit(1)
    else:
        print(f"  所有测试通过！{passed}/{total}")
    print("=" * 58)


if __name__ == "__main__":
    asyncio.run(main())
