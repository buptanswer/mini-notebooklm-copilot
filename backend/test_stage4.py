"""
test_stage4.py — Stage 4 完整流水线测试

测试步骤:
  Test 1: 向量检索（Qdrant 语义召回）
  Test 2: 关键词检索（SQLite FTS5 BM25）
  Test 3: 混合检索（RRF 融合）
  Test 4: 重排序（qwen3-rerank DashScope API）
  Test 5: 流式问答（qwen3.5-plus，收集完整回答）

前置条件（Stage 3 测试后满足）:
  - doc_id="test-sample-pdf" 已入库
  - kb_id="test-kb-stage3" 对应文档已索引
  - ALIBABA_CLOUD_ACCESS_KEY_SECRET 环境变量已设置
  - Qdrant child_chunks 集合已有向量数据
  - SQLite child_chunks_fts FTS5 索引已通过触发器填充

运行方式:
  cd backend
  python test_stage4.py
"""

import asyncio
import json
import os
import sys

# 确保 backend/ 在 Python 路径上
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.db.database import init_db
from app.db.qdrant_client import init_qdrant
from app.services.qa_service import stream_answer
from app.services.rerank_service import rerank
from app.services.retrieval_service import (
    fetch_parent_chunks,
    hybrid_search,
    keyword_search,
    vector_search,
)

# ── 测试配置 ────────────────────────────────────────────────
KB_ID = "test-kb-stage3"
QUERY = "本文档的主要内容是什么？请总结核心知识点。"
TOP_K = 5

PASS = "PASS ✓"
FAIL = "FAIL ✗"


# ═════════════════════════════════════════════════════════════
# Setup: 确保测试文档状态可检索
# ═════════════════════════════════════════════════════════════

async def _ensure_indexed(doc_id: str = "test-sample-pdf") -> None:
    """
    Stage 3 测试将 doc 状态设为 'parsing' 但不会再更新。
    Stage 4 检索服务只查 status IN ('indexed','needs_review','parsed')，
    因此在此将其提升为 'indexed'。
    仅当 child_chunks 表中确实有该文档的数据时才执行。
    """
    from app.db.database import get_db
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) FROM child_chunks WHERE doc_id=?", (doc_id,)
        )
        row = await cur.fetchone()
        chunk_count = row[0]
        if chunk_count == 0:
            raise RuntimeError(
                f"doc_id={doc_id!r} 在 child_chunks 中无数据——"
                "请先运行 test_stage3.py 完成数据入库。"
            )
        await db.execute(
            "UPDATE documents SET status='indexed' WHERE doc_id=? AND status='parsing'",
            (doc_id,),
        )
        await db.commit()
        print(f"  文档状态已更新为 'indexed'（child_chunks: {chunk_count} 条）")
    finally:
        await db.close()


# ═════════════════════════════════════════════════════════════
# Test 1: 向量检索
# ═════════════════════════════════════════════════════════════

async def test_vector_search() -> list:
    print("\n─── Test 1: 向量检索 ───────────────────────────────")
    results = await vector_search(QUERY, KB_ID, limit=10)

    assert len(results) > 0, (
        f"向量检索返回空结果。请确认 kb_id={KB_ID!r} 下有已索引文档，"
        "且 Qdrant child_chunks 集合已有数据。"
    )

    print(f"  召回 {len(results)} 条")
    for i, c in enumerate(results[:3]):
        hp = " > ".join(c.header_path[:2]) if c.header_path else "（无标题）"
        print(f"  [{i+1}] score={c.score:.4f}  pages={c.page_span_start}-{c.page_span_end}  {hp}")

    print(f"  {PASS}")
    return results


# ═════════════════════════════════════════════════════════════
# Test 2: 关键词检索
# ═════════════════════════════════════════════════════════════

async def test_keyword_search() -> list:
    print("\n─── Test 2: 关键词检索（FTS5） ──────────────────────")
    # 简单词语，任何文档都可能匹配
    results = await keyword_search("内容 介绍", KB_ID, limit=10)

    # 关键词搜索可能为空（文档词汇不同），不强制要求非空
    print(f"  召回 {len(results)} 条（FTS5 BM25，可为 0）")
    for i, c in enumerate(results[:3]):
        hp = " > ".join(c.header_path[:2]) if c.header_path else "（无标题）"
        print(f"  [{i+1}] score={c.score:.4f}  {hp!r}")

    print(f"  {PASS}")
    return results


# ═════════════════════════════════════════════════════════════
# Test 3: 混合检索
# ═════════════════════════════════════════════════════════════

async def test_hybrid_search() -> list:
    print("\n─── Test 3: 混合检索（RRF 融合） ───────────────────")
    results = await hybrid_search(QUERY, KB_ID, vector_limit=20, keyword_limit=20, top_k=15)

    assert len(results) > 0, "混合检索返回空结果（向量路应有结果）"

    print(f"  融合后 {len(results)} 条")
    for i, c in enumerate(results[:3]):
        hp = " > ".join(c.header_path[:2]) if c.header_path else "（无标题）"
        print(f"  [{i+1}] rrf={c.score:.6f}  source={c.source}  {hp!r}")

    print(f"  {PASS}")
    return results


# ═════════════════════════════════════════════════════════════
# Test 4: 重排序
# ═════════════════════════════════════════════════════════════

async def test_rerank(hybrid_results: list) -> list:
    print("\n─── Test 4: 重排序（qwen3-rerank） ─────────────────")
    candidates = hybrid_results[:10]   # 送入最多 10 条
    reranked = await rerank(QUERY, candidates, top_n=TOP_K)

    assert len(reranked) > 0, "重排序返回空结果"
    assert len(reranked) <= TOP_K, f"返回数量 {len(reranked)} 超过 top_k={TOP_K}"

    print(f"  输入 {len(candidates)} → top_{TOP_K} → 实际返回 {len(reranked)} 条")
    for i, c in enumerate(reranked):
        hp = " > ".join(c.header_path[:2]) if c.header_path else "（无标题）"
        print(f"  [{i+1}] relevance={c.score:.4f}  {hp!r}")

    print(f"  {PASS}")
    return reranked


# ═════════════════════════════════════════════════════════════
# Test 5: 流式问答
# ═════════════════════════════════════════════════════════════

async def test_qa_streaming(reranked: list):
    print("\n─── Test 5: 流式问答（qwen3.5-plus） ───────────────")

    # 获取 parent 元数据（header_path / 页码）
    parent_ids = list({c.parent_chunk_id for c in reranked})
    parent_map = await fetch_parent_chunks(parent_ids)
    print(f"  加载 {len(parent_map)} 个 parent chunks 元数据")

    got_citations = False
    got_end = False
    delta_parts: list[str] = []
    error_msg: str | None = None

    async for event in stream_answer(QUERY, reranked, parent_map, enable_thinking=False):
        line = event.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        try:
            obj = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        t = obj.get("type")
        if t == "citations":
            got_citations = True
            print(f"  citations 事件: {len(obj.get('citations', []))} 条来源")
        elif t == "delta":
            delta_parts.append(obj.get("content", ""))
        elif t == "thinking":
            pass   # 思考内容，不计入最终回答
        elif t == "end":
            got_end = True
        elif t == "error":
            error_msg = obj.get("message", "未知错误")

    if error_msg:
        print(f"  QA API 返回错误: {error_msg}")
        raise AssertionError(f"QA 生成失败: {error_msg}")

    answer = "".join(delta_parts)

    assert got_citations, "未收到 citations 事件"
    assert got_end, "未收到 end 事件"
    assert len(answer) > 10, f"回答内容过短（{len(answer)} 字）: {answer!r}"

    preview = answer[:200].replace("\n", " ")
    print(f"  回答总长 {len(answer)} 字")
    print(f"  预览: {preview}{'...' if len(answer) > 200 else ''}")
    print(f"  {PASS}")


# ═════════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════════

async def main():
    print("=" * 55)
    print("  Mini-NotebookLM  Stage 4 Pipeline 测试")
    print("=" * 55)
    print(f"  KB_ID : {KB_ID}")
    print(f"  QUERY : {QUERY[:60]}")
    print(f"  API   : {settings.dashscope_base_url}")
    print(f"  Key   : {'✓ 已设置' if settings.dashscope_api_key else '✗ 未设置！'}")

    if not settings.dashscope_api_key:
        print("\n[ERROR] ALIBABA_CLOUD_ACCESS_KEY_SECRET 未设置，无法调用外部 API")
        sys.exit(1)

    # 初始化
    settings.ensure_dirs()
    await init_db()
    init_qdrant()

    # 确保测试文档状态为 indexed（Stage 3 遗留 parsing 状态）
    print("\n─── Setup: 检查测试数据 ─────────────────────────────")
    await _ensure_indexed("test-sample-pdf")

    failed = False
    try:
        vec_results        = await test_vector_search()
        _kw_results        = await test_keyword_search()
        hybrid_results     = await test_hybrid_search()
        reranked           = await test_rerank(hybrid_results)
        await test_qa_streaming(reranked)
    except AssertionError as e:
        print(f"\n{FAIL}  断言失败: {e}")
        failed = True
    except Exception as e:
        import traceback
        print(f"\n{FAIL}  未预期异常: {e}")
        traceback.print_exc()
        failed = True

    print("\n" + "=" * 55)
    if failed:
        print("  部分测试未通过，请查看上方错误信息")
        sys.exit(1)
    else:
        print("  所有测试通过！Stage 4 混合检索问答闭环实现完成 ✓")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
