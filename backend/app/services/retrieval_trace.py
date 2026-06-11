"""
Retrieval Trace —— 全链路检索编排 + 可观测 trace（v1.4.0「检索透视」）

把整条隐藏链路跑通并产出结构化 trace：
  问题 → LLM 查询规划(query_planner) → 关键词(BM25,OR)+向量(语义) 双路召回
       → RRF 融合 → qwen3-rerank 重排 → top_k

trace 同时服务三方：
  - 前端「检索透视」可视化（演示态动画 + 开发态数据表）；
  - 真实问答 conversation_service 复用同一条改进检索（build_trace=False）；
  - 开发者评估检索算法效果（看到底召回了什么、各路分数、融合与重排怎么变）。

健壮性：query_planner 内部已对 LLM 失败回退；本编排对 rerank 失败再降级到融合序，
保证 trace 端点与真实问答都不因单点 API 抖动而整体失败。
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field, replace

from app.services.retrieval_service import (
    RetrievedChunk,
    fetch_parent_chunks,
    keyword_search,
    rrf_merge,
    vector_search,
)

logger = logging.getLogger(__name__)

_SNIPPET = 400   # trace 中文本片段截断长度


# ─────────────────────────────────────────────────────────────
# trace / 结果结构
# ─────────────────────────────────────────────────────────────

@dataclass
class RetrievalTrace:
    plan: dict = field(default_factory=dict)
    vector_hits: list[dict] = field(default_factory=list)
    keyword_hits: list[dict] = field(default_factory=list)
    fusion: list[dict] = field(default_factory=list)
    reranked: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    timings_ms: dict = field(default_factory=dict)
    rerank_degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "plan": self.plan,
            "vector_hits": self.vector_hits,
            "keyword_hits": self.keyword_hits,
            "fusion": self.fusion,
            "reranked": self.reranked,
            "counts": self.counts,
            "timings_ms": self.timings_ms,
            "rerank_degraded": self.rerank_degraded,
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]            # 最终 top_k（重排后）
    parent_map: dict                         # parent_chunk_id -> {...}
    trace: RetrievalTrace | None = None
    plan: object = None                      # QueryPlan（关键词 + 语义查询），供 Agent 透视展示实际检索词


# ─────────────────────────────────────────────────────────────
# 主编排
# ─────────────────────────────────────────────────────────────

async def run_retrieval_pipeline(
    question: str,
    kb_id: str,
    *,
    top_k: int = 5,
    fused_k: int = 15,
    vector_limit: int = 20,
    keyword_limit: int = 20,
    build_trace: bool = True,
) -> RetrievalResult:
    """跑「规划→双路→RRF→重排」全链路。build_trace=False 时省去 trace 组装开销。"""
    # 惰性导入，避免 retrieval_service ← qa_service ← query_planner / rerank_service 循环
    from app.services.query_planner import plan_query
    from app.services.rerank_service import rerank

    t0 = time.perf_counter()
    plan = await plan_query(question)
    t_plan = time.perf_counter()

    # 双路并行召回：向量用 semantic_query；关键词用 keywords（OR 召回）
    keyword_query = " ".join(plan.keywords) or question
    vec_results, kw_results = await asyncio.gather(
        vector_search(plan.semantic_query or question, kb_id, limit=vector_limit),
        keyword_search(keyword_query, kb_id, limit=keyword_limit, match_mode="or"),
    )
    t_recall = time.perf_counter()

    # child_chunk_id → chunk（向量优先保留完整 payload）
    chunk_map: dict[str, RetrievedChunk] = {}
    for c in vec_results:
        chunk_map[c.child_chunk_id] = c
    for c in kw_results:
        chunk_map.setdefault(c.child_chunk_id, c)

    # 记录每路 rank/原始分（在 RRF 改写 score 之前）
    vec_rank = {c.child_chunk_id: (i, c.score) for i, c in enumerate(vec_results)}
    kw_rank = {c.child_chunk_id: (i, c.score) for i, c in enumerate(kw_results)}

    # RRF 融合
    merged = rrf_merge([
        [(c.child_chunk_id, c.score) for c in vec_results],
        [(c.child_chunk_id, c.score) for c in kw_results],
    ])
    merged_top = merged[:fused_k]
    fused_chunks: list[RetrievedChunk] = []
    for cid, rrf in merged_top:
        c = chunk_map.get(cid)
        if c:
            fc = replace(c, score=rrf, source="hybrid")
            fused_chunks.append(fc)
    t_fuse = time.perf_counter()

    # 重排（输入 fused，top_n=top_k）。rerank 会原地改 score，故传副本隔离 fusion 记录。
    rerank_query = plan.rewritten_question or question
    rerank_degraded = False
    try:
        final_chunks = await rerank(rerank_query, [replace(c) for c in fused_chunks], top_n=top_k)
    except Exception as exc:
        logger.warning("重排失败，降级用融合序前 %d 条: %s", top_k, exc)
        final_chunks = [replace(c) for c in fused_chunks[:top_k]]
        rerank_degraded = True
    t_rerank = time.perf_counter()

    # parent 补全
    parent_ids = list({c.parent_chunk_id for c in final_chunks})
    parent_map = await fetch_parent_chunks(parent_ids)

    trace: RetrievalTrace | None = None
    if build_trace:
        trace = _build_trace(
            plan=plan,
            vec_results=vec_results,
            kw_results=kw_results,
            vec_rank=vec_rank,
            kw_rank=kw_rank,
            merged_top=merged_top,
            chunk_map=chunk_map,
            fused_chunks=fused_chunks,
            final_chunks=final_chunks,
            rerank_degraded=rerank_degraded,
            timings_ms={
                "plan": round((t_plan - t0) * 1000, 1),
                "recall": round((t_recall - t_plan) * 1000, 1),
                "fuse": round((t_fuse - t_recall) * 1000, 1),
                "rerank": round((t_rerank - t_fuse) * 1000, 1),
                "total": round((t_rerank - t0) * 1000, 1),
            },
        )

    return RetrievalResult(chunks=final_chunks, parent_map=parent_map, trace=trace, plan=plan)


# ─────────────────────────────────────────────────────────────
# trace 组装
# ─────────────────────────────────────────────────────────────

def _snip(text: str) -> str:
    text = text or ""
    return text[:_SNIPPET] + ("…" if len(text) > _SNIPPET else "")


# 关键词命中按「token 粒度」算，对齐 FTS5 的分词：LLM 常给出复合关键词
# （如 "for 循环" / "in 关键字"），FTS5 实际匹配的是其中的 token（for / 循环 / in）。
# 整短语 substring 检查几乎永远命中不了，故拆成 token 再判，命中信息才真实可用。
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]{2,}")


def _keyword_token(tok: str) -> re.Pattern[str] | None:
    """单个候选 token → 匹配正则；ASCII 用词边界（避免 in 命中 printing），CJK 直接子串。"""
    if re.fullmatch(r"[A-Za-z]", tok):       # 丢弃单字母 ASCII 噪音
        return None
    if re.fullmatch(r"[A-Za-z0-9]+", tok):
        return re.compile(rf"\b{re.escape(tok)}\b", re.IGNORECASE)
    return re.compile(re.escape(tok))        # CJK：无词边界概念，直接子串


def _kw_tokens_of(keyword: str) -> list[str]:
    """关键词 → 高亮/命中判断用的 token：ASCII 词（去单字母）+ jieba 中文子词（去单字）。

    与召回侧对齐：检索用 jieba 子词 OR 召回（"需求分析"→需求/分析/需求分析），
    高亮也按 jieba 子词判断，中文命中才能在检索透视里点亮（否则整词子串几乎不命中）。
    """
    from app.services.cn_tokenizer import segment_tokens
    out: list[str] = []
    seen: set[str] = set()
    for tok in list(_TOKEN_RE.findall(keyword or "")) + segment_tokens(keyword or ""):
        if re.fullmatch(r"[A-Za-z]", tok):      # 单字母 ASCII 噪音
            continue
        if re.fullmatch(r"[一-鿿]", tok):        # 单字中文噪音
            continue
        low = tok.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(tok)
    return out


def _kw_token_patterns(keywords: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """规划关键词 → [(token, 正则)]，去重、过滤噪音。"""
    out: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for k in keywords:
        for tok in _kw_tokens_of(k):
            low = tok.lower()
            if low in seen:
                continue
            pat = _keyword_token(tok)
            if pat is None:
                continue
            seen.add(low)
            out.append((tok, pat))
    return out


def _hit_brief(c: RetrievedChunk, rank: int, score: float) -> dict:
    return {
        "rank": rank,
        "child_chunk_id": c.child_chunk_id,
        "parent_chunk_id": c.parent_chunk_id,
        "doc_id": c.doc_id,
        "chunk_type": c.chunk_type,
        "index_kind": c.index_kind,   # 非空=命中父块自定义索引（检索透视标注来源）
        "header_path": c.header_path,
        "text": _snip(c.retrieval_text or c.embedding_text),
        "score": round(float(score), 4),
    }


def _build_trace(
    *,
    plan,
    vec_results: list[RetrievedChunk],
    kw_results: list[RetrievedChunk],
    vec_rank: dict[str, tuple[int, float]],
    kw_rank: dict[str, tuple[int, float]],
    merged_top: list[tuple[str, float]],
    chunk_map: dict[str, RetrievedChunk],
    fused_chunks: list[RetrievedChunk],
    final_chunks: list[RetrievedChunk],
    rerank_degraded: bool,
    timings_ms: dict,
) -> RetrievalTrace:
    keywords = plan.keywords
    token_patterns = _kw_token_patterns(keywords)
    # 每个规划关键词 → 它包含的 token（小写，含 jieba 中文子词），用于判断"该关键词是否命中"
    kw_tokens = {k: {t.lower() for t in _kw_tokens_of(k)} for k in keywords}

    # 向量路
    vector_hits = [_hit_brief(c, i, c.score) for i, c in enumerate(vec_results)]

    # 关键词路：token 粒度命中（对齐 FTS5），同时给出
    #   matched_tokens   —— 实际命中的 token（前端按词边界高亮）
    #   matched_keywords —— 含 ≥1 命中 token 的规划关键词（前端点亮对应 chip）
    keyword_hits = []
    for i, c in enumerate(kw_results):
        brief = _hit_brief(c, i, c.score)
        haystack = (c.retrieval_text or "") + "\n" + (c.embedding_text or "")
        matched_tokens = [tok for tok, pat in token_patterns if pat.search(haystack)]
        matched_low = {t.lower() for t in matched_tokens}
        brief["matched_tokens"] = matched_tokens
        brief["matched_keywords"] = [
            k for k in keywords if kw_tokens.get(k, set()) & matched_low
        ]
        keyword_hits.append(brief)

    # 融合表
    fused_order = {c.child_chunk_id: i for i, c in enumerate(fused_chunks)}
    fusion = []
    for cid, rrf in merged_top:
        c = chunk_map.get(cid)
        if not c:
            continue
        vr = vec_rank.get(cid)
        kr = kw_rank.get(cid)
        fusion.append({
            "rank": fused_order.get(cid, -1),
            "child_chunk_id": cid,
            "doc_id": c.doc_id,
            "index_kind": c.index_kind,
            "header_path": c.header_path,
            "text": _snip(c.retrieval_text or c.embedding_text),
            "vec_rank": vr[0] if vr else None,
            "vec_score": round(vr[1], 4) if vr else None,
            "kw_rank": kr[0] if kr else None,
            "kw_score": round(kr[1], 4) if kr else None,
            "rrf_score": round(float(rrf), 5),
        })

    # 重排：相对融合序的位次变化
    reranked = []
    for i, c in enumerate(final_chunks):
        prev = fused_order.get(c.child_chunk_id)
        reranked.append({
            "rank": i,
            "prev_rank": prev,
            "delta": (prev - i) if prev is not None else None,
            "child_chunk_id": c.child_chunk_id,
            "parent_chunk_id": c.parent_chunk_id,
            "doc_id": c.doc_id,
            "chunk_type": c.chunk_type,
            "index_kind": c.index_kind,
            "header_path": c.header_path,
            "text": _snip(c.retrieval_text or c.embedding_text),
            "rerank_score": round(float(c.score), 4),
        })

    return RetrievalTrace(
        plan=plan.to_dict(),
        vector_hits=vector_hits,
        keyword_hits=keyword_hits,
        fusion=fusion,
        reranked=reranked,
        counts={
            "vector": len(vec_results),
            "keyword": len(kw_results),
            "fused": len(fused_chunks),
            "final": len(final_chunks),
        },
        timings_ms=timings_ms,
        rerank_degraded=rerank_degraded,
    )
