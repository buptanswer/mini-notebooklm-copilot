"""
Chat API — 混合检索 + 重排序 + 流式问答

端点：
  POST /api/chat/{kb_id}          → SSE StreamingResponse（text/event-stream）
  POST /api/chat/{kb_id}/search   → JSON（仅检索+重排，不生成，供调试）

SSE 事件格式（chat 端点）：
  {"type": "citations", "citations": [...]}
  {"type": "delta",     "content": "..."}
  {"type": "thinking",  "content": "..."}    # 仅 enable_thinking=true 时
  {"type": "end"}
  {"type": "error",     "message": "..."}
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.qa_service import stream_answer
from app.services.rerank_service import rerank
from app.services.retrieval_service import fetch_parent_chunks, hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ─────────────────────────────────────────────────────────────
# Request / Response 模型
# ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20, description="最终保留的 chunk 数量")
    enable_thinking: bool | None = Field(default=None, description="是否启用深度思考模式（None 时读取服务器配置）")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="检索查询")
    top_k: int = Field(default=5, ge=1, le=20, description="最终返回数量")


# ─────────────────────────────────────────────────────────────
# 流式问答端点
# ─────────────────────────────────────────────────────────────

@router.post("/{kb_id}", summary="流式 RAG 问答（SSE）")
async def chat_with_kb(kb_id: str, req: ChatRequest):
    """
    全流程 RAG 问答：混合检索 → 重排序 → 流式生成。
    响应为 text/event-stream，逐事件推送。
    """
    async def event_stream():
        try:
            # 1. 混合检索（向量 + 关键词 RRF）
            hybrid_results = await hybrid_search(
                req.query, kb_id,
                vector_limit=20, keyword_limit=20, top_k=15,
            )
            if not hybrid_results:
                yield (
                    f"data: {json.dumps({'type': 'error', 'message': '未找到相关内容，请检查知识库是否已完成索引'}, ensure_ascii=False)}\n\n"
                )
                yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"
                return

            # 2. 重排序
            reranked = await rerank(req.query, hybrid_results, top_n=req.top_k)

            # 3. 获取 parent chunk 元数据（header_path / 页码范围）
            parent_ids = list({c.parent_chunk_id for c in reranked})
            parent_map = await fetch_parent_chunks(parent_ids)

            # 4. 流式生成（内部已先发送 citations 事件）
            async for event in stream_answer(
                req.query, reranked, parent_map,
                enable_thinking=req.enable_thinking,
            ):
                yield event

        except Exception:
            logger.exception("chat_with_kb 内部错误 kb=%s", kb_id)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': '服务器内部错误'}, ensure_ascii=False)}\n\n"
            )
            yield f"data: {json.dumps({'type': 'end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────
# 非流式检索端点（调试 / 前端预览来源）
# ─────────────────────────────────────────────────────────────

@router.post("/{kb_id}/search", summary="检索 + 重排（不生成回答）")
async def search_kb(kb_id: str, req: SearchRequest):
    """
    仅执行混合检索 + 重排序，不调用 LLM，用于调试和前端预览来源。
    """
    hybrid_results = await hybrid_search(
        req.query, kb_id,
        vector_limit=20, keyword_limit=20, top_k=15,
    )

    if not hybrid_results:
        return {"query": req.query, "kb_id": kb_id, "total": 0, "results": []}

    reranked = await rerank(req.query, hybrid_results, top_n=req.top_k)

    return {
        "query": req.query,
        "kb_id": kb_id,
        "total": len(reranked),
        "results": [
            {
                "rank": i + 1,
                "child_chunk_id": c.child_chunk_id,
                "parent_chunk_id": c.parent_chunk_id,
                "doc_id": c.doc_id,
                "header_path": c.header_path,
                "page_span_start": c.page_span_start,
                "page_span_end": c.page_span_end,
                "bbox_norm1000": c.bbox_norm1000,
                "bbox_page": c.bbox_page,
                "anchor_origin_pdf_path": c.anchor_origin_pdf_path,
                "retrieval_text": c.retrieval_text[:400],
                "score": round(c.score, 4),
                "source": c.source,
            }
            for i, c in enumerate(reranked)
        ],
    }
