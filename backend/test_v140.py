"""
test_v140.py — v1.4.0「检索透视」新功能单元测试（mock，无需 Qdrant/真实 API）

覆盖：
  1. query_planner：LLM 正常 / JSON 非法 / 抛异常 三种路径
  2. 多模态助手：image_to_data_url / collect_image_paths / build_multimodal_user_content
  3. Small-to-Big：conversation_service._build_rag_content 格式
  4. retrieval_trace.run_retrieval_pipeline：trace 结构 + 重排降级

运行（可与 uvicorn 并存，本测试不打开 Qdrant）：
  cd backend && uv run python test_v140.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from app.services.retrieval_service import RetrievedChunk

PASS, FAIL = "[PASS]", "[FAIL]"
_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {PASS if ok else FAIL} {name}" + (f"  ({detail})" if detail else ""))


def _chunk(cid: str, *, ptext: str = "", rtext: str = "", assets: list[str] | None = None,
           ctype: str = "paragraph", pid: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        child_chunk_id=cid, parent_chunk_id=pid or f"p-{cid}", doc_id="doc1",
        section_id="s0", chunk_type=ctype, retrieval_text=rtext or f"text-{cid}",
        embedding_text=ptext or f"emb-{cid}", header_path=["第一章", "1.1"],
        asset_paths=assets or [],
    )


# ──────────────────────────────────────────────────────────────

async def test_query_planner() -> None:
    print("\n[1] query_planner")
    from app.services import query_planner

    good = '{"rewritten_question":"补全问句","keywords":["平时分","考核方式"],"semantic_query":"本课程平时成绩由作业与考勤构成"}'
    with patch.object(query_planner, "call_llm_json", AsyncMock(return_value=good)):
        p = await query_planner.plan_query("平时分怎么算")
    _record("LLM 正常 → source=llm", p.source == "llm")
    _record("解析出 keywords", p.keywords == ["平时分", "考核方式"])
    _record("解析出 semantic_query", "平时成绩" in p.semantic_query)

    with patch.object(query_planner, "call_llm_json", AsyncMock(return_value="这不是JSON")):
        p2 = await query_planner.plan_query("期末考试时间")
    _record("JSON 非法 → 回退 fallback", p2.source == "fallback")
    _record("回退 semantic_query=问题原文", p2.semantic_query == "期末考试时间")
    _record("回退 keywords 非空", len(p2.keywords) >= 1)

    with patch.object(query_planner, "call_llm_json", AsyncMock(side_effect=RuntimeError("api down"))):
        p3 = await query_planner.plan_query("作业截止")
    _record("LLM 抛异常 → 回退", p3.source == "fallback")

    p4 = await query_planner.plan_query("")
    _record("空问题安全返回", p4.source == "fallback" and p4.keywords == [])


def test_multimodal_helpers() -> None:
    print("\n[2] 多模态助手")
    from app.services import qa_service

    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "fig.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
        url = qa_service.image_to_data_url(str(img))
        _record("image_to_data_url → data:image/png", bool(url) and url.startswith("data:image/png;base64,"))
        _record("不存在文件 → None", qa_service.image_to_data_url(str(Path(td) / "nope.png")) is None)

        # collect：去重 + 存在性 + 限量
        chunks = [
            _chunk("c1", assets=[str(img), str(img)], ctype="image"),
            _chunk("c2", assets=[str(Path(td) / "missing.png")], ctype="image"),
            _chunk("c3", assets=[], ctype="paragraph"),
        ]
        paths = qa_service.collect_image_paths(chunks, limit=5)
        _record("collect 去重且只留存在文件", paths == [str(img)])
        _record("collect 限量生效", len(qa_service.collect_image_paths([_chunk("x", assets=[str(img)], ctype="image")], limit=0)) == 0)

        content = qa_service.build_multimodal_user_content("正文上下文", [str(img)])
        _record("多模态 content 首段是文本", content[0] == {"type": "text", "text": "正文上下文"})
        _record("多模态 content 含 image_url", any(p.get("type") == "image_url" for p in content))


def test_small_to_big() -> None:
    print("\n[3] Small-to-Big 上下文格式")
    from app.services.conversation_service import _build_rag_content

    sources = [
        {"header_path": ["第二章", "2.1 方法"], "page_span_start": 2, "page_span_end": 4, "text": "父块完整正文……"},
        {"header_path": [], "page_span_start": 0, "page_span_end": 0, "text": "另一段"},
    ]
    out = _build_rag_content("我的问题在此", sources)
    _record("含 [来源1]/[来源2]", "[来源1]" in out and "[来源2]" in out)
    _record("页码 1-indexed 区间", "第3-5页" in out)
    _record("无标题回退占位", "（无标题）" in out)
    _record("含父块全文", "父块完整正文" in out)
    _record("问题在末尾", out.strip().endswith("我的问题在此"))


async def test_retrieval_trace() -> None:
    print("\n[4] retrieval_trace.run_retrieval_pipeline")
    from app.services import query_planner, rerank_service, retrieval_trace
    from app.services.query_planner import QueryPlan

    plan = QueryPlan(original_question="Q", rewritten_question="Q?", keywords=["MinerU", "API"],
                     semantic_query="MinerU 提供在线 API", source="llm")
    vec = [_chunk("v1", rtext="向量命中A"), _chunk("v2", rtext="共同命中"), _chunk("v3", rtext="向量命中C")]
    kw = [_chunk("k1", rtext="含 API 的关键词命中", pid="p-v2"), _chunk("v2", rtext="共同命中")]
    # rerank：把 v3 提到第一（制造位次变化）
    async def fake_rerank(q, chunks, top_n=5):
        order = {"v3": 0.9, "v1": 0.8, "v2": 0.7}
        out = sorted(chunks, key=lambda c: order.get(c.child_chunk_id, 0.0), reverse=True)[:top_n]
        for c in out:
            c.score = order.get(c.child_chunk_id, 0.0)
        return out

    with (
        patch.object(query_planner, "plan_query", AsyncMock(return_value=plan)),
        patch.object(retrieval_trace, "vector_search", AsyncMock(return_value=vec)),
        patch.object(retrieval_trace, "keyword_search", AsyncMock(return_value=kw)),
        patch.object(retrieval_trace, "fetch_parent_chunks", AsyncMock(return_value={})),
        patch.object(rerank_service, "rerank", fake_rerank),
    ):
        res = await retrieval_trace.run_retrieval_pipeline("Q", "kb1", top_k=3, build_trace=True)

    t = res.trace.to_dict()
    _record("trace.plan 带 keywords", t["plan"]["keywords"] == ["MinerU", "API"])
    _record("向量路记录 3 条", len(t["vector_hits"]) == 3)
    _record("关键词路带 matched_keywords", any("API" in (h.get("matched_keywords") or []) for h in t["keyword_hits"]))
    _record("关键词路带 matched_tokens", any("API" in (h.get("matched_tokens") or []) for h in t["keyword_hits"]))
    _record("RRF 融合表非空且含双路 rank", len(t["fusion"]) > 0 and any(f["vec_rank"] is not None for f in t["fusion"]))
    _record("重排把 v3 提到第 0 位", t["reranked"][0]["child_chunk_id"] == "v3")
    _record("重排记录 prev_rank/delta", t["reranked"][0]["prev_rank"] is not None)
    _record("counts 正确", t["counts"]["final"] == 3 and t["counts"]["vector"] == 3)
    _record("最终 chunks=3", len(res.chunks) == 3)

    # 重排降级：rerank 抛异常 → 用融合序，rerank_degraded=True
    with (
        patch.object(query_planner, "plan_query", AsyncMock(return_value=plan)),
        patch.object(retrieval_trace, "vector_search", AsyncMock(return_value=vec)),
        patch.object(retrieval_trace, "keyword_search", AsyncMock(return_value=kw)),
        patch.object(retrieval_trace, "fetch_parent_chunks", AsyncMock(return_value={})),
        patch.object(rerank_service, "rerank", AsyncMock(side_effect=RuntimeError("rerank down"))),
    ):
        res2 = await retrieval_trace.run_retrieval_pipeline("Q", "kb1", top_k=3, build_trace=True)
    _record("rerank 失败 → degraded=True", res2.trace.rerank_degraded is True)
    _record("rerank 失败仍返回结果", len(res2.chunks) > 0)


def test_keyword_token_match() -> None:
    """回归：复合关键词（'for 循环'）须按 token 命中，ASCII 走词边界、CJK 走子串。

    旧实现用整短语 substring 检查，对 LLM 给的复合关键词几乎永远命中不了，
    导致关键词高亮形同虚设。这里锁定 token 粒度命中与词边界行为。
    """
    print("\n[5] retrieval_trace 关键词 token 命中")
    from app.services.retrieval_trace import _kw_token_patterns

    pats = _kw_token_patterns(["for 循环", "in 关键字", "API", "二维数组"])

    def matched(haystack: str) -> list[str]:
        return [tok for tok, pat in pats if pat.search(haystack)]

    _record("复合关键词按 token 命中 for", "for" in matched("for pdf in folder:"))
    _record("CJK token 子串命中 循环", "循环" in matched("这是 for 循环 结构"))
    _record("CJK token 命中 二维数组", "二维数组" in matched("定义二维数组的语法"))
    _record("ASCII 词边界：in 不误命中 printing", "in" not in matched("printing values only"))
    _record("ASCII 词边界：独立 in 命中", "in" in matched("x in y"))
    _record("单字母 ASCII 噪音被过滤", _kw_token_patterns(["a b c"]) == [])


def _ir_title(bid: str, order: int, text: str, level: int, page: int = 0):
    from app.models.models_ir import BboxNorm1000, BlockMetadata, IRBlock
    return IRBlock(
        block_id=bid, page_idx=page, order_in_page=order, order_in_doc=order,
        section_id="", type="title", bbox_norm1000=BboxNorm1000(coords=[0, 0, 200, 40]),
        text=text, metadata=BlockMetadata(title_level=level),
    )


def _ir_para(bid: str, order: int, text: str, page: int = 0):
    from app.models.models_ir import BboxNorm1000, IRBlock
    return IRBlock(
        block_id=bid, page_idx=page, order_in_page=order, order_in_doc=order,
        section_id="", type="paragraph", bbox_norm1000=BboxNorm1000(coords=[0, 50, 300, 120]),
        text=text,
    )


def test_heuristic_levels() -> None:
    print("\n[6] doc_tree 启发式层级")
    from app.services.doc_tree_service import heuristic_title_levels
    got = heuristic_title_levels(
        ["第一章 绪论", "1.1 背景", "1.2.1 细节", "（1）小项", "第二节 方法", "概述"]
    )
    _record("数字前缀深度: 1.1→2, 1.2.1→3", got[1] == 2 and got[2] == 3)
    _record("第一章→1 / 第二节→2", got[0] == 1 and got[4] == 2)
    _record("（1）→3 / 无编号→1", got[3] == 3 and got[5] == 1)


async def test_doc_tree_assign() -> None:
    print("\n[7] doc_tree 层级写回（LLM mock + 兜底）")
    from app.services import doc_tree_service

    def blocks5():
        return [
            _ir_title("t0", 0, "第一章 绪论", 1),
            _ir_title("t1", 1, "1.1 背景", 1),
            _ir_title("t2", 2, "1.2 目标", 1),
            _ir_title("t3", 3, "第二章 设计", 1),
            _ir_title("t4", 4, "2.1 架构", 1),
        ]

    # LLM 正常：返回 items（索引回填）→ 写回
    items_json = '{"items":[{"i":0,"level":1},{"i":1,"level":2},{"i":2,"level":2},{"i":3,"level":1},{"i":4,"level":2}]}'
    with patch.object(doc_tree_service, "call_llm_json", AsyncMock(return_value=items_json)):
        bs = await doc_tree_service.assign_title_levels(blocks5())
    levels = [b.metadata.title_level for b in bs if b.type == "title"]
    _record("LLM 层级写回 [1,2,2,1,2]", levels == [1, 2, 2, 1, 2])

    # LLM 漏报部分索引（覆盖率≥0.6）→ 缺口用启发式补（第二章→1, 2.1→2）
    partial = '{"items":[{"i":0,"level":1},{"i":1,"level":2},{"i":2,"level":2}]}'
    with patch.object(doc_tree_service, "call_llm_json", AsyncMock(return_value=partial)):
        bs3 = await doc_tree_service.assign_title_levels(blocks5())
    levels3 = [b.metadata.title_level for b in bs3 if b.type == "title"]
    _record("LLM 部分覆盖 → 缺口启发式补", levels3 == [1, 2, 2, 1, 2])

    # LLM 失败 → 启发式兜底（第一章→1, 1.1→2 ...）
    with patch.object(doc_tree_service, "call_llm_json",
                      AsyncMock(side_effect=RuntimeError("llm down"))):
        bs2 = await doc_tree_service.assign_title_levels(blocks5())
    levels2 = [b.metadata.title_level for b in bs2 if b.type == "title"]
    _record("LLM 失败 → 启发式兜底", levels2 == [1, 2, 2, 1, 2])

    # ≤1 标题：跳过（保持现状 level）
    one = [_ir_title("t0", 0, "唯一标题", 1)]
    with patch.object(doc_tree_service, "call_llm_json",
                      AsyncMock(side_effect=AssertionError("不该被调用"))):
        await doc_tree_service.assign_title_levels(one)
    _record("≤1 标题不调 LLM", True)


def test_chunker_hierarchy() -> None:
    print("\n[8] 层级树 → 父/子切片（无退化父块 / 无孤儿 / 标题不单列）")
    from app.adapters.dom_builder import build_dom
    from app.chunkers.child_chunker import build_child_chunks
    from app.chunkers.parent_chunker import build_parent_chunks
    from app.models.models_ir import IRPage

    # 模拟 doc_tree 重建后的层级（第一章/第二章=1，子节=2）
    blocks = [
        _ir_title("t0", 0, "第一章 绪论", 1),
        _ir_title("t1", 1, "1.1 背景", 2),
        _ir_para("p1", 2, "这是背景段落正文。"),
        _ir_title("t2", 3, "1.2 目标", 2),
        _ir_para("p2", 4, "这是目标段落正文。"),
        _ir_title("t3", 5, "第二章 设计", 1, page=1),
        _ir_title("t4", 6, "2.1 架构", 2, page=1),
        _ir_para("p3", 7, "这是架构段落正文。", page=1),
    ]
    blocks, sections = build_dom(blocks)
    pages = [IRPage(page_id="pg0", page_idx=0), IRPage(page_id="pg1", page_idx=1)]
    parents = build_parent_chunks(sections, blocks, pages, "docX")
    children = build_child_chunks(parents, blocks, pages, "docX")

    parent_titles = {p.title for p in parents}
    _record("容器章节不出父块（第一章/第二章 跳过）",
            "第一章 绪论" not in parent_titles and "第二章 设计" not in parent_titles)
    _record("叶子小节出父块（1.1/1.2/2.1）", len(parents) == 3)

    p11 = next((p for p in parents if p.title == "1.1 背景"), None)
    _record("层级 header_path 正确",
            p11 is not None and p11.header_path == ["第一章 绪论", "1.1 背景"])

    parent_ids = {p.parent_chunk_id for p in parents}
    _record("无孤儿 child（parent_chunk_id 都有效）",
            all(c.parent_chunk_id in parent_ids for c in children))
    title_texts = {"第一章 绪论", "1.1 背景", "1.2 目标", "第二章 设计", "2.1 架构"}
    _record("标题不单列为 child", all(c.retrieval_text not in title_texts for c in children))
    _record("child 仅来自正文段落（3 条）", len(children) == 3)


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 58)
    print("  Mini-NotebookLM  v1.4.0  Retrieval X-Ray Tests")
    print("=" * 58)

    await test_query_planner()
    test_multimodal_helpers()
    test_small_to_big()
    await test_retrieval_trace()
    test_keyword_token_match()
    test_heuristic_levels()
    await test_doc_tree_assign()
    test_chunker_hierarchy()

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
    print(f"  所有测试通过！{passed}/{total}")
    print("=" * 58)


if __name__ == "__main__":
    asyncio.run(main())
