"""
MinerU SaaS API 异步 HTTP 客户端

支持两类上传方式：

1. 批量本地文件上传（推荐用于本地文件）
   endpoint: POST /api/v4/file-urls/batch
   流程：申请预签名 URL → PUT 文件 → 自动提交解析
   轮询：GET /api/v4/extract-results/batch/{batch_id}

2. 单文件 URL 解析
   endpoint: POST /api/v4/extract/task
   轮询：GET /api/v4/extract/task/{task_id}
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

from app.config import settings
from app.services.http_retry import retry_async

logger = logging.getLogger(__name__)


_T = TypeVar("_T")


async def _retry(
    coro_fn: Callable[[], Awaitable[_T]],
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> _T:
    """MinerU API 专用瞬时重试（委托给共享 retry_async，delays: 2s → 4s → 8s）。"""
    return await retry_async(
        coro_fn, what="MinerU API", max_retries=max_retries, base_delay=base_delay
    )

_BASE = settings.mineru_api_base   # "https://mineru.net/api/v4"

# ── API 响应已知字段集合（用于未知字段 WARNING 检测）─────────────────────
_KNOWN_TOP_RESP_KEYS         = frozenset({"code", "msg", "data", "trace_id"})
_KNOWN_BATCH_UPLOAD_DATA_KEYS = frozenset({"batch_id", "file_urls"})
_KNOWN_POLL_BATCH_DATA_KEYS  = frozenset({"batch_id", "extract_result"})
_KNOWN_EXTRACT_RESULT_KEYS   = frozenset({
    "file_name", "state", "full_zip_url", "err_msg", "data_id", "extract_progress",
})
_KNOWN_SINGLE_TASK_DATA_KEYS = frozenset({"task_id"})
_KNOWN_SINGLE_POLL_DATA_KEYS = frozenset({
    "task_id", "state", "full_zip_url", "err_msg", "data_id", "extract_progress",
})


def _warn_api_extra(d: dict, known: frozenset, ctx: str) -> None:
    """若 API 响应 dict 中存在 known 以外的键，输出 WARNING。"""
    if not isinstance(d, dict):
        return
    extra = set(d.keys()) - known
    if extra:
        logger.warning(
            "[MinerU API 未知字段] %s 发现未预期键: %s"
            " — API 格式可能已更新，请检查并更新解析逻辑以避免信息丢失",
            ctx,
            sorted(extra),
        )


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.mineru_api_key}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────────────────
# 批量本地文件上传
# ─────────────────────────────────────────────────────────────

async def request_batch_upload_urls(
    files_info: list[dict],          # [{"name": "demo.pdf", "data_id": "..."}]
    model_version: str = "vlm",
) -> tuple[str, list[str]]:
    """
    申请批量预签名上传链接。

    Returns:
        (batch_id, file_urls)  — file_urls 的索引与 files_info 一一对应
    """
    payload: dict[str, Any] = {
        "files": files_info,
        "model_version": model_version,
    }

    async def _call():
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE}/file-urls/batch",
                headers=_auth_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    body = await _retry(_call)

    if body.get("code") != 0:
        raise RuntimeError(f"申请上传链接失败: code={body.get('code')}, msg={body.get('msg')}")

    _warn_api_extra(body, _KNOWN_TOP_RESP_KEYS, "file-urls/batch response")
    data = body["data"]
    _warn_api_extra(data, _KNOWN_BATCH_UPLOAD_DATA_KEYS, "file-urls/batch data")
    batch_id: str = data["batch_id"]
    file_urls: list[str] = data["file_urls"]
    logger.info("申请到 %d 个预签名 URL，batch_id=%s", len(file_urls), batch_id)
    return batch_id, file_urls


async def upload_file_to_presigned_url(presigned_url: str, local_path: Path) -> None:
    """
    将本地文件 PUT 到预签名 URL。
    注意：上传时不需要设置 Content-Type（MinerU 文档明确要求）。
    """
    with open(local_path, "rb") as f:
        data = f.read()

    async def _call():
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.put(presigned_url, content=data)
        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"预签名上传失败 {local_path.name}: HTTP {resp.status_code}, body={resp.text[:200]}"
            )
        return resp

    await _retry(_call)
    logger.info("上传完成: %s (%d bytes)", local_path.name, len(data))


async def poll_batch_results(
    batch_id: str,
    poll_interval: float = 5.0,
    max_wait: float = 600.0,
) -> list[dict[str, Any]]:
    """
    轮询批量任务，直到所有文件均达到终态（done/failed）。

    Returns:
        extract_result 列表，每个元素包含 state / full_zip_url / err_msg 等
    """
    terminal = {"done", "failed"}
    elapsed = 0.0

    while elapsed < max_wait:
        bid = batch_id

        async def _call_batch():
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{_BASE}/extract-results/batch/{bid}",
                    headers=_auth_headers(),
                )
                resp.raise_for_status()
                return resp.json()

        body = await _retry(_call_batch)

        if body.get("code") != 0:
            raise RuntimeError(f"查询批量结果失败: {body}")

        _warn_api_extra(body, _KNOWN_TOP_RESP_KEYS, "extract-results/batch response")
        batch_data: dict = body["data"]
        _warn_api_extra(batch_data, _KNOWN_POLL_BATCH_DATA_KEYS, "extract-results/batch data")
        results: list[dict] = batch_data.get("extract_result", [])
        for _r in results:
            _warn_api_extra(
                _r,
                _KNOWN_EXTRACT_RESULT_KEYS,
                f"extract_result[{_r.get('file_name', '?')}]",
            )
        states = [r.get("state", "?") for r in results]
        logger.info("batch %s … states: %s", batch_id[:8], states)

        if results and all(s in terminal for s in states):
            return results

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"批量任务 {batch_id} 在 {max_wait}s 内未完成")


# ─────────────────────────────────────────────────────────────
# 单文件 URL 解析
# ─────────────────────────────────────────────────────────────

async def submit_single_url_task(
    file_url: str,
    data_id: str = "",
    model_version: str = "vlm",
) -> str:
    """提交单文件（URL）解析任务，返回 task_id"""
    payload: dict[str, Any] = {
        "url": file_url,
        "model_version": model_version,
    }
    if data_id:
        payload["data_id"] = data_id

    async def _call():
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE}/extract/task",
                headers=_auth_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    body = await _retry(_call)

    if body.get("code") != 0:
        raise RuntimeError(f"提交单文件任务失败: {body}")

    _warn_api_extra(body, _KNOWN_TOP_RESP_KEYS, "extract/task response")
    _warn_api_extra(body["data"], _KNOWN_SINGLE_TASK_DATA_KEYS, "extract/task data")
    task_id: str = body["data"]["task_id"]
    logger.info("提交单任务成功，task_id=%s", task_id)
    return task_id


async def poll_single_task(
    task_id: str,
    poll_interval: float = 5.0,
    max_wait: float = 600.0,
) -> dict[str, Any]:
    """轮询单个任务直到完成，返回最终的 data 字段"""
    terminal = {"done", "failed"}
    elapsed = 0.0

    while elapsed < max_wait:
        tid = task_id

        async def _call_single():
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{_BASE}/extract/task/{tid}",
                    headers=_auth_headers(),
                )
                resp.raise_for_status()
                return resp.json()

        body = await _retry(_call_single)

        if body.get("code") != 0:
            raise RuntimeError(f"查询单任务失败: {body}")

        _warn_api_extra(body, _KNOWN_TOP_RESP_KEYS, f"extract/task/{task_id[:8]} response")
        data: dict = body["data"]
        _warn_api_extra(data, _KNOWN_SINGLE_POLL_DATA_KEYS, f"extract/task/{task_id[:8]} data")
        state: str = data.get("state", "")
        logger.info("task %s … state=%s", task_id[:8], state)

        if state in terminal:
            return data

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"任务 {task_id} 在 {max_wait}s 内未完成")


# ─────────────────────────────────────────────────────────────
# 下载 ZIP
# ─────────────────────────────────────────────────────────────

async def download_zip(zip_url: str, dest_path: Path) -> None:
    """流式下载解析结果 zip 包到 dest_path（含连接失败重试）"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    async def _call():
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", zip_url) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

    await _retry(_call)
    logger.info("下载完成: %s (%d bytes)", dest_path, dest_path.stat().st_size)
