"""
Settings API — 提示词管理 + 应用配置读写端点
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import BACKEND_ROOT, settings
from app.prompts import list_prompts, reload_prompts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

# ── 用户可写配置持久化文件 ──────────────────────────────────
_USER_CONFIG_PATH = BACKEND_ROOT / ".user_config.json"


def _load_user_config() -> dict[str, Any]:
    """读取用户通过 UI 保存的配置覆盖项。"""
    try:
        if _USER_CONFIG_PATH.is_file():
            return json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("读取 user_config 失败，使用空配置", exc_info=True)
    return {}


def _save_user_config(data: dict[str, Any]) -> None:
    """保存用户配置覆盖项到磁盘。"""
    _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 模型 ────────────────────────────────────────────────────

class UserConfigUpdate(BaseModel):
    """前端可提交的配置更新（全部可选，只更新提交的字段）。"""
    qa_model: str | None = Field(default=None, description="QA 模型名")
    qa_base_url: str | None = Field(default=None, description="QA Provider base URL")
    qa_api_key: str | None = Field(default=None, description="QA API Key")
    qa_enable_thinking: bool | None = Field(default=None, description="是否开启思维链")
    qa_enable_multimodal: bool | None = Field(default=None, description="是否开启多模态问答")
    qa_multimodal_model: str | None = Field(default=None, description="多模态问答模型名")
    vlm_model: str | None = Field(default=None, description="图片/表格描述 VLM 模型")
    mineru_api_key: str | None = Field(default=None, description="MinerU API Key")
    dashscope_api_key: str | None = Field(default=None, description="阿里云百炼 API Key")


# ── 端点 ────────────────────────────────────────────────────

@router.get("")
async def get_config():
    """返回当前生效的应用配置（合并 env + 用户 UI 覆盖）。"""
    uc = _load_user_config()

    def _val(env_val: str, ui_key: str) -> str:
        """返回当前生效值：UI 覆盖 > 环境变量。掩码处理 API key。"""
        v = uc.get(ui_key) or env_val
        return v

    return {
        # QA 模型
        "qa_model": _val(settings.qa_model, "qa_model"),
        "qa_base_url": _val(settings.qa_base_url, "qa_base_url"),
        "qa_api_key": _mask_key(_val(settings.qa_api_key, "qa_api_key")),
        "qa_enable_thinking": uc.get("qa_enable_thinking", settings.qa_enable_thinking),
        "qa_enable_multimodal": uc.get("qa_enable_multimodal", settings.qa_enable_multimodal),
        "qa_multimodal_model": _val(settings.qa_multimodal_model, "qa_multimodal_model"),
        # VLM
        "vlm_model": _val(settings.vlm_model, "vlm_model"),
        # API Keys
        "mineru_api_key": _mask_key(_val(settings.mineru_api_key, "mineru_api_key")),
        "dashscope_api_key": _mask_key(_val(settings.dashscope_api_key, "dashscope_api_key")),
        # 嵌入式服务（不可切换）
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "embedding_dim": settings.embedding_dim,
        # 解析
        "parent_chunk_heading_level": settings.parent_chunk_heading_level,
        "max_concurrent_parses": settings.max_concurrent_parses,
        "mineru_model_version": settings.mineru_model_version,
        "mineru_office_use_ocr": settings.mineru_office_use_ocr,
    }


@router.post("")
async def update_config(body: UserConfigUpdate):
    """更新用户配置（持久化到 backend/.user_config.json，重启后生效）。"""
    uc = _load_user_config()
    updates = body.model_dump(exclude_none=True)

    # API key 特殊处理：前端传空字符串视为"不更新"，传非空才覆盖
    for key_field in ("qa_api_key", "mineru_api_key", "dashscope_api_key"):
        if key_field in updates and not updates[key_field]:
            del updates[key_field]

    uc.update(updates)
    _save_user_config(uc)
    logger.info("用户配置已更新: %s", sorted(updates.keys()))
    return {"detail": "配置已保存，重启后端生效", "updated_fields": sorted(updates.keys())}


# ── 提示词管理（不变）─────────────────────────────────────

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


# ── 辅助 ─────────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    """掩码 API key，只显示前 4 位 + 后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:4] + "****" + key[-4:]
