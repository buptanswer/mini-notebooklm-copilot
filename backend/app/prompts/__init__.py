"""
提示词加载器：从 backend/app/prompts/ 目录读取 .md 文件作为提示词。

约定：
- 每个 .md 文件名（不含扩展名）= prompt name
- 支持简单变量替换 {var}（Python str.format）
- 启动时一次性加载所有 .md 到内存
- 用户改了磁盘文件 → 调 reload_prompts() 重新加载（Settings 页提供按钮）

使用示例：
    from app.prompts import load_prompt
    text = load_prompt("lecture_review_section_first",
                       user_identity="北邮通信工程专业大二下",
                       time_descriptor="下午2节",
                       course_name="数学物理方法",
                       section_index=1)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_PROMPT_DIR = Path(__file__).parent
_cache: dict[str, str] = {}


def _load_all() -> None:
    _cache.clear()
    for p in _PROMPT_DIR.glob("*.md"):
        _cache[p.stem] = p.read_text(encoding="utf-8").rstrip("\n")


def load_prompt(name: str, **vars: Any) -> str:
    """读取并按需做变量替换。"""
    if not _cache:
        _load_all()
    if name not in _cache:
        raise KeyError(f"prompt '{name}' 不存在于 {_PROMPT_DIR}")
    template = _cache[name]
    if not vars:
        return template
    try:
        return template.format(**vars)
    except KeyError as exc:
        raise KeyError(
            f"prompt '{name}' 缺少变量 {exc}; 已传入: {list(vars)}"
        ) from exc


def list_prompts() -> dict[str, str]:
    """返回 {name: full_text}，供 Settings 页只读展示。"""
    if not _cache:
        _load_all()
    return dict(_cache)


def reload_prompts() -> None:
    """显式重载（用户在 Settings 页改文件后调用）。"""
    _load_all()
