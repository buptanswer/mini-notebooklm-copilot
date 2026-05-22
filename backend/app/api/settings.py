"""
Settings API — 提示词管理端点
"""
from __future__ import annotations

from fastapi import APIRouter

from app.prompts import list_prompts, reload_prompts

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/prompts")
async def get_prompts():
    """返回所有已加载的提示词（名称 → 内容）。"""
    return {"prompts": list_prompts()}


@router.post("/prompts/reload")
async def reload():
    """重载磁盘上的提示词文件（用户手动编辑后调用）。"""
    reload_prompts()
    prompts = list_prompts()
    return {"detail": "已重载", "count": len(prompts), "names": sorted(prompts.keys())}
