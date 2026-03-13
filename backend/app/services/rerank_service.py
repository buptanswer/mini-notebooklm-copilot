"""
Rerank Service — 调用 qwen3-rerank 对召回结果二次打分

接口：DashScope 原生 API（rerank 模型不走 OpenAI-compatible 路径）
端点：POST https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank

请求体：
  {
    "model": "qwen3-rerank",
    "input": {"query": "...", "documents": ["doc1", "doc2", ...]},
    "parameters": {"return_documents": false, "top_n": N}
  }

响应：
  {"output": {"results": [{"index": 2, "relevance_score": 0.95}, ...]}}

说明：
  - top_n 限制最终返回条数
  - 返回 index 对应原始 documents 数组下标
  - relevance_score 范围 [0, 1]
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.retrieval_service import RetrievedChunk

logger = logging.getLogger(__name__)

_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
_MAX_DOCS = 50   # qwen3-rerank 单次最多文档数（保守限制）


async def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int = 5,
) -> list[RetrievedChunk]:
    """
    调用 qwen3-rerank 对 chunks 重排序，返回 top_n 个结果。

    Args:
        query:  用户查询原文
        chunks: 待重排序的 RetrievedChunk 列表
        top_n:  重排后保留数量

    Returns:
        top_n 个 RetrievedChunk，score 已更新为 relevance_score，降序排列
    """
    if not chunks:
        return []

    # 截断文档数
    candidates = chunks[:_MAX_DOCS]

    # 将 retrieval_text 送入重排（含 header_path 前缀）
    documents = [
        f"{' > '.join(c.header_path)}\n{c.retrieval_text}" if c.header_path
        else c.retrieval_text
        for c in candidates
    ]

    payload = {
        "model": settings.rerank_model,
        "input": {
            "query": query,
            "documents": documents,
        },
        "parameters": {
            "return_documents": False,
            "top_n": min(top_n, len(candidates)),
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_RERANK_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Rerank API 失败: HTTP {resp.status_code}\n{resp.text[:400]}"
        )

    body = resp.json()
    raw_results = body.get("output", {}).get("results", [])

    # 重排后按 relevance_score 降序
    sorted_results = sorted(raw_results, key=lambda x: x["relevance_score"], reverse=True)

    reranked: list[RetrievedChunk] = []
    for r in sorted_results:
        idx = r["index"]
        score = float(r["relevance_score"])
        if 0 <= idx < len(candidates):
            c = candidates[idx]
            c.score = score
            reranked.append(c)

    logger.info(
        "重排序: 输入 %d 条 → top_%d, top_score=%.4f",
        len(candidates), len(reranked),
        reranked[0].score if reranked else 0.0,
    )
    return reranked
