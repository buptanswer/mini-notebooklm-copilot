"""
test_v180.py — v1.8.0 新增功能与接口单元测试

测试覆盖：
1. RAG 双路多轮 Agent 检索与评估机制（2-round evaluation loop）
2. Pandoc PDF/MD 讲义导出及其降级机制（XeLaTeX -> wkhtmltopdf -> 500 Fallback）
3. 课后复习查看已有讲义下，追问自动会话初始化（auto-warmup）逻辑

运行：
  cd backend
  .venv\\Scripts\\python test_v180.py
"""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from fastapi import HTTPException
from app.main import app
from app.db.database import init_db, get_db
from app.db.qdrant_client import init_qdrant
from app.config import settings
from app.services import conversation_service, lecture_review_service
from app.services.conversation_service import _fetch_rag_context
from app.services.retrieval_service import RetrievedChunk

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
# 1. RAG 2-round Agent Loop 测试
# ──────────────────────────────────────────────────────────────

async def test_rag_agent_loop() -> None:
    print("\n[1] RAG 双路多轮 Agent 评估与补漏规划逻辑")
    
    # 模拟首轮返回的 Chunk
    c1 = RetrievedChunk(
        child_chunk_id="c1", parent_chunk_id="p1", doc_id="doc1",
        section_id="s0", chunk_type="paragraph", retrieval_text="首轮检索召回的数学物理方法偏微分方程概念。",
        embedding_text="", header_path=["偏微分方程"], score=0.9
    )
    
    # 模拟第二轮返回的 Chunk
    c2 = RetrievedChunk(
        child_chunk_id="c2", parent_chunk_id="p2", doc_id="doc1",
        section_id="s0", chunk_type="paragraph", retrieval_text="第二轮检索补充的偏微分方程边界条件公式。",
        embedding_text="", header_path=["偏微分方程"], score=0.85
    )

    from app.services.retrieval_trace import RetrievalResult
    mock_result_round1 = RetrievalResult(
        chunks=[c1],
        parent_map={"p1": {"header_path": ["偏微分方程"], "page_span_start": 1, "page_span_end": 1, "text_full": "首轮检索召回的数学物理方法偏微分方程概念全文。"}}
    )

    # Mock 流程：
    # 1. run_retrieval_pipeline 返回 mock_result_round1
    # 2. 首轮 call_llm_json 评估：判断为 incomplete，规划补漏词 "边界条件"
    # 3. 触发第二轮检索 hybrid_search 返回 [c2]
    # 4. 第二轮 fetch_parent_chunks 返回 p2 的 parent 数据
    # 5. 第二轮 call_llm_json 评估：判断为 complete，结束检索
    
    # Mock LLM 返回
    eval_responses = [
        # 第一轮评估返回 incomplete 状态及新 queries
        '{"status": "incomplete", "missing_info_analysis": "缺失边界条件细节", "new_queries": [{"query": "边界条件", "keywords": ["边界", "条件"]}]}',
        # 第二轮评估返回 complete
        '{"status": "complete", "missing_info_analysis": "已补齐边界条件", "new_queries": []}'
    ]
    
    call_count = 0
    async def mock_call_llm_json(messages, **kwargs):
        nonlocal call_count
        res = eval_responses[call_count]
        call_count += 1
        return res

    mock_run_retrieval = AsyncMock(return_value=mock_result_round1)
    mock_hybrid_search = AsyncMock(return_value=[c2])
    mock_fetch_parent = AsyncMock(return_value={
        "p2": {"header_path": ["偏微分方程"], "page_span_start": 2, "page_span_end": 2, "text_full": "第二轮检索补充的偏微分方程边界条件公式全文。"}
    })

    with (
        patch("app.services.retrieval_trace.run_retrieval_pipeline", mock_run_retrieval),
        patch("app.services.qa_service.call_llm_json", mock_call_llm_json),
        patch("app.services.retrieval_service.hybrid_search", mock_hybrid_search),
        patch("app.services.retrieval_service.fetch_parent_chunks", mock_fetch_parent),
    ):
        events = []
        async for evt in _fetch_rag_context("如何求解偏微分方程？", "kb123", top_k=5):
            events.append(evt)

        # 验证 progress 事件序列
        progress_msgs = [e["message"] for e in events if e["type"] == "progress"]
        _record("包含首轮检索提示", any("【Agent 检索首轮】" in m for m in progress_msgs))
        _record("包含信息评估提示", any("【Agent 评估中】" in m for m in progress_msgs))
        _record("评估结果包含 incomplete 状态分析", any("缺失边界条件细节" in m for m in progress_msgs))
        _record("包含规划补漏提示", any("【Agent 规划补漏】" in m for m in progress_msgs))
        _record("包含第二轮检索提示", any("【Agent 定向检索完成】" in m for m in progress_msgs))
        _record("评估结果包含结束检索决策", any("【Agent 检索决策】现有信息已足够回答" in m for m in progress_msgs))

        # 验证最终融合的 result
        result_ev = next((e for e in events if e["type"] == "result"), None)
        _record("产生最终 result 事件", result_ev is not None)
        if result_ev:
            citations = result_ev.get("citations") or []
            _record("citations 包含 2 个引用来源", len(citations) == 2)
            cids = {c["child_chunk_id"] for c in citations}
            _record("引用包含 c1 (首轮) 与 c2 (第二轮)", cids == {"c1", "c2"})
            _record("图片检测标记正确 (False)", result_ev.get("has_image") is False)


# ──────────────────────────────────────────────────────────────
# 2. Pandoc PDF/MD 导出及其降级机制测试
# ──────────────────────────────────────────────────────────────

async def test_pandoc_export(c: httpx.AsyncClient, kb_id: str, conv_id: str) -> None:
    print("\n[2] Pandoc PDF/MD 导出及引擎降级逻辑")

    # 导出 Markdown 格式
    r_md = await c.post(
        f"/api/review/{kb_id}/export",
        json={"conversation_id": conv_id, "format": "md"}
    )
    _record("导出 Markdown 格式成功 → 200", r_md.status_code == 200)
    _record("返回 text/markdown Content-Type", "text/markdown" in r_md.headers.get("content-type", ""))
    _record("包含文件名 Content-Disposition 响应头", "Content-Disposition" in r_md.headers)

    # Mock subprocess.run 用于测试 PDF 转换流程
    import subprocess
    
    # 场景 A: xelatex 直接转换成功
    mock_run_success = MagicMock()
    mock_run_success.returncode = 0
    
    def side_effect_a(cmd, *args, **kwargs):
        try:
            o_idx = cmd.index("-o")
            out_file = Path(cmd[o_idx + 1])
            out_file.write_bytes(b"%PDF-1.4 mock pdf content")
        except Exception:
            pass
        return mock_run_success

    with patch("subprocess.run", MagicMock(side_effect=side_effect_a)) as mock_sub:
        r_pdf_a = await c.post(
            f"/api/review/{kb_id}/export",
            json={"conversation_id": conv_id, "format": "pdf"}
        )
        _record("xelatex 成功时导出 PDF → 200", r_pdf_a.status_code == 200)
        # 确认使用了 --pdf-engine=xelatex
        called_args = mock_sub.call_args[0][0]
        _record("首选编译引擎为 xelatex", "--pdf-engine=xelatex" in called_args)

    # 场景 B: xelatex 失败，wkhtmltopdf 降级转换成功
    mock_run_fail = MagicMock()
    mock_run_fail.returncode = 1
    mock_run_fail.stderr = "xelatex not found"
    
    def side_effect_b(cmd, *args, **kwargs):
        if "--pdf-engine=xelatex" in cmd:
            return mock_run_fail
        elif "--pdf-engine=wkhtmltopdf" in cmd:
            try:
                o_idx = cmd.index("-o")
                out_file = Path(cmd[o_idx + 1])
                out_file.write_bytes(b"%PDF-1.4 mock pdf content")
            except Exception:
                pass
            return mock_run_success
        return mock_run_fail

    with patch("subprocess.run", MagicMock(side_effect=side_effect_b)):
        r_pdf_b = await c.post(
            f"/api/review/{kb_id}/export",
            json={"conversation_id": conv_id, "format": "pdf"}
        )
        _record("xelatex 失败后成功降级至 wkhtmltopdf → 200", r_pdf_b.status_code == 200)

    # 场景 C: 两种引擎全部失败
    with patch("subprocess.run", MagicMock(return_value=mock_run_fail)):
        r_pdf_c = await c.post(
            f"/api/review/{kb_id}/export",
            json={"conversation_id": conv_id, "format": "pdf"}
        )
        _record("两种引擎全失败时返回服务器 500 错误", r_pdf_c.status_code == 500)
        _record("500 错误描述中指明了安装说明", "xelatex" in r_pdf_c.json()["detail"] or "pandoc" in r_pdf_c.json()["detail"])


# ──────────────────────────────────────────────────────────────
# 3. 追问自动会话初始化（auto-warmup）测试
# ──────────────────────────────────────────────────────────────

async def test_auto_warmup_followup(c: httpx.AsyncClient, kb_id: str) -> None:
    print("\n[3] 课后复习自动会话初始化 (auto-warmup) 逻辑")

    # 1. 创建临时讲义文件并写入内容，写入 documents 登记表
    temp_dir = tempfile.mkdtemp()
    temp_note_file = Path(temp_dir) / "测试课程260808第01节课堂要点.md"
    temp_note_file.write_text("# 第一节课堂要点\n这里是偏微分方程基本定义。", encoding="utf-8")

    db = await get_db()
    try:
        await db.execute("DELETE FROM documents WHERE kb_id=? AND filename=?", (kb_id, "测试课程260808第01节课堂要点.md"))
        await db.execute(
            """INSERT INTO documents (doc_id, kb_id, filename, relative_path, source_format, bound_file_path, folder_category, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("doc-warmup-1", kb_id, "测试课程260808第01节课堂要点.md", "课堂录音/260808/测试课程260808第01节课堂要点.md", "md", str(temp_note_file), "review_note", "indexed")
        )
        await db.commit()
    finally:
        await db.close()

    try:
        # 2. 调用 followup，不传 conversation_id，但传 date="260808"
        # 同时开启 RAG 和 思考
        r = await c.post(
            f"/api/review/{kb_id}/followup",
            json={
                "date": "260808",
                "content": "刚才这节课讲了偏微分方程什么定义？",
                "enable_rag": True,
                "enable_thinking": True
            }
        )
        _record("追问未带 conversation_id 发送成功 → 200", r.status_code == 200)
        
        events = _collect_sse(r.text)
        
        # 3. 验证事件流中返回的会话 ID 已经自动创建
        conv_event = next((e for e in events if e.get("type") == "conversation"), None)
        _record("事件流中包含自动创建的 conversation 事件", conv_event is not None)
        auto_conv_id = conv_event.get("conversation_id") if conv_event else None
        _record("自动分配了 conversation_id", auto_conv_id is not None)

        if auto_conv_id:
            # 4. 验证已存讲义内容是否已被成功灌入该会话的 messages 历史中
            messages = await conversation_service.list_messages(auto_conv_id)
            _record("会话中包含了灌入的讲义消息 (数量 >= 2)", len(messages) >= 2)
            # 第一条应该是灌入的 assistant 讲义
            讲义_msgs = [m for m in messages if m["role"] == "assistant" and (m.get("metadata") or {}).get("kind") == "section"]
            _record("历史消息中成功包含 section kind 的讲义消息", len(讲义_msgs) == 1)
            _record("讲义消息内容正确", "偏微分方程基本定义" in 讲义_msgs[0]["content"])

            # 5. 验证 followup 的新问题与回答是否已追加落库
            user_msgs = [m for m in messages if m["role"] == "user"]
            _record("历史消息中包含了追问的 user 问题", len(user_msgs) == 1 and user_msgs[0]["content"] == "刚才这节课讲了偏微分方程什么定义？")
            
            # 清理该临时会话
            await conversation_service.delete_conversation(auto_conv_id)

    # 6. 不带 conversation_id 且不带 date 应该返回 400
        r_bad = await c.post(
            f"/api/review/{kb_id}/followup",
            json={
                "content": "无效提问"
            }
        )
        _record("不带 conversation_id 且不带 date 的追问返回 400 错误", r_bad.status_code == 400)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        db = await get_db()
        try:
            await db.execute("DELETE FROM documents WHERE kb_id=? AND filename=?", (kb_id, "测试课程260808第01节课堂要点.md"))
            await db.commit()
        finally:
            await db.close()


# ──────────────────────────────────────────────────────────────
# 主执行入口
# ──────────────────────────────────────────────────────────────

async def main() -> None:
    import os
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
            
    print("=" * 58)
    print("  Mini-NotebookLM  v1.8.0  New Feature Integration Tests")
    print("=" * 58)

    await init_db()
    init_qdrant()

    # 创建一个测试用的 KB 和会话以测试导出 API
    db = await get_db()
    try:
        # 清理级联残留
        await db.execute("DELETE FROM messages WHERE conversation_id IN (SELECT conversation_id FROM conversations WHERE kb_id='test-kb-180')")
        await db.execute("DELETE FROM conversations WHERE kb_id='test-kb-180'")
        await db.execute("DELETE FROM review_notes WHERE kb_id='test-kb-180'")
        await db.execute("DELETE FROM documents WHERE kb_id='test-kb-180'")
        await db.execute("DELETE FROM knowledge_bases WHERE kb_id='test-kb-180'")
        await db.execute(
            "INSERT INTO knowledge_bases (kb_id, name, kb_type, bound_folder_path, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            ("test-kb-180", "测试课程180", "course", "", "2026-06-11T00:00:00Z", "2026-06-11T00:00:00Z")
        )
        await db.commit()
    finally:
        await db.close()

    conv_id = await conversation_service.create_conversation(
        kb_id="test-kb-180",
        scenario="lecture_review",
        title="测试讲义180",
        metadata={"date": "260808", "course_name": "测试课程180"}
    )
    
    # 向会话添加讲义内容消息
    await conversation_service.append_message(
        conv_id, "assistant", "这是第一节的讲义，关于偏微分方程。",
        metadata={"kind": "section", "section_num": 1}
    )

    # 1. 运行 RAG 2-round Agent Loop 测试
    await test_rag_agent_loop()

    # 准备 HTTPX 客户端
    async def _mock_stream_llm(messages, *, enable_thinking=False, model=None, multimodal=False):
        yield {"type": "delta", "content": "这是对追问的测试回答。"}
        yield {"type": "end"}

    transport = httpx.ASGITransport(app=app)
    with patch("app.services.qa_service.stream_llm_completion", _mock_stream_llm):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # 2. 运行 Pandoc PDF/MD 导出测试
            await test_pandoc_export(c, "test-kb-180", conv_id)
            
            # 3. 运行追问自动会话初始化测试
            await test_auto_warmup_followup(c, "test-kb-180")

    # 清理
    await conversation_service.delete_conversation(conv_id)
    db = await get_db()
    try:
        await db.execute("DELETE FROM review_notes WHERE kb_id='test-kb-180'")
        await db.execute("DELETE FROM documents WHERE kb_id='test-kb-180'")
        await db.execute("DELETE FROM knowledge_bases WHERE kb_id='test-kb-180'")
        await db.commit()
    finally:
        await db.close()

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
