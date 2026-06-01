"""
Embedding Service — 调用阿里云百炼 text-embedding-v4 生成向量

接口：OpenAI 兼容模式（dashscope compatible-mode/v1）
模型：text-embedding-v4（默认 1024 维，支持 text_type 参数）

批量策略（官方文档规格）：
  - text-embedding-v4 单次请求最多 10 条文本（批次大小 = 10）
  - 每条文本最多 8,192 Token
  - 超出时自动分批，每批 10 条，之间加 0.2s 间隔避免限流
  - 返回向量顺序与输入顺序一致

text_type 说明（官方建议区分 query/document 以获得最佳检索效果）：
  - "document"  存入向量库时使用（默认值）
  - "query"     检索时使用
  注：该参数官方文档称仅 DashScope SDK/API 支持，但实测
      OpenAI 兼容接口通过 parameters.text_type 传入同样生效。

reference:
  https://help.aliyun.com/zh/model-studio/developer-reference/text-embedding-v4
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import httpx

from app.config import settings
from app.services.http_retry import retry_async

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10      # text-embedding-v4 单批上限（实测最大 10）
_BATCH_INTERVAL = 0.2  # 批间间隔（秒），避免触发限流


async def embed_texts(
    texts: list[str],
    text_type: Literal["document", "query"] = "document",
) -> list[list[float]]:
    """
    批量生成文本向量。

    Args:
        texts: 文本列表，返回向量顺序与之一一对应
        text_type: "document"（入库）或 "query"（检索）

    Returns:
        list[list[float]]，每个元素是一条文本的 1024 维向量
    """
    if not texts:
        return []

    all_vectors: list[list[float]] = []

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start: batch_start + _BATCH_SIZE]
        vectors = await _embed_batch(batch, text_type)
        all_vectors.extend(vectors)

        if batch_start + _BATCH_SIZE < len(texts):
            await asyncio.sleep(_BATCH_INTERVAL)

    logger.info("embed_texts: %d 条文本 → %d 个向量", len(texts), len(all_vectors))
    return all_vectors


async def _embed_batch(
    texts: list[str],
    text_type: str,
) -> list[list[float]]:
    """单批调用，返回有序向量列表。"""
    url = f"{settings.dashscope_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.embedding_model,
        "input": texts,
        "parameters": {
            "text_type": text_type,
        },
    }

    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Embedding API 请求失败: HTTP {resp.status_code}\n{resp.text[:400]}"
            )
        return resp.json()

    body = await retry_async(_call, what="Embedding API")

    # 兼容 OpenAI 格式：body["data"] 是按 index 排好序的列表
    data = body.get("data", [])
    if not data:
        raise RuntimeError(f"Embedding API 返回空 data: {body}")

    # 按 index 排序（防止乱序）
    data_sorted = sorted(data, key=lambda d: d["index"])
    vectors = [d["embedding"] for d in data_sorted]

    if len(vectors) != len(texts):
        raise RuntimeError(
            f"向量数量 ({len(vectors)}) 与输入文本数量 ({len(texts)}) 不一致"
        )

    return vectors
