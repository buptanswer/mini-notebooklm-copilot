"""
共享的瞬时网络故障重试（指数退避）。

MinerU / DashScope 等外部 HTTP 调用统一复用，避免批量任务突发期出现
"All connection attempts failed" 这类瞬时连接失败直接导致任务失败。

只重试**连接级**瞬时故障（连接失败、超时、网络错误、读错误）；
HTTP 4xx/5xx 等应用级错误不重试（交由调用方处理）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

# 瞬时网络故障（可重试）
RETRYABLE_EXC = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ReadError,
)

_T = TypeVar("_T")


async def retry_async(
    coro_fn: Callable[[], Awaitable[_T]],
    *,
    what: str = "外部 API",
    max_retries: int = 3,
    base_delay: float = 1.5,
) -> _T:
    """
    指数退避重试，仅对瞬时网络故障重试。delays: base_delay * 2^attempt。
    超过 max_retries 仍失败则抛 RuntimeError（含原始错误）。
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except RETRYABLE_EXC as exc:
            if attempt >= max_retries:
                raise RuntimeError(
                    f"{what} 网络连接失败，已重试 {max_retries} 次，最后错误: {exc}"
                ) from exc
            delay = base_delay * (2**attempt)
            logger.warning(
                "%s 连接失败（第 %d/%d 次），%.1fs 后重试: %s",
                what, attempt + 1, max_retries, delay, exc,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")
