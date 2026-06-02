"""
Doc Tree Service — LLM 文档树层级重建（v1.4.0 Phase 2）

问题：MinerU 解析器无法判断标题层级，**永远返回 title_level=1**（或 None），
导致 dom_builder 建出的 section 树是**扁平**的（所有标题都是根的兄弟节点）。

本服务在 dom_builder 之前介入：把全部标题（按出现顺序）喂给 LLM，让它推断每个
标题的大纲层级，写回 `block.metadata.title_level`；dom_builder 不变（它已读
title_level），就能自然建出层级树。

健壮性：
  - LLM 失败 / 返回长度或范围非法 → 回退**数字前缀/编号启发式**（"1.2.1"→3 级等）。
  - 启发式再不行 → 全 1 级（即退回 MinerU 现状），**绝不阻断解析流水线**。
  - 标题数 ≤1 或超过上限时跳过 LLM（无意义 / 控制 prompt 体积与成本）。
"""
from __future__ import annotations

import json
import logging
import re

from app.models.models_ir import IRBlock
from app.prompts import load_prompt
from app.services.qa_service import call_llm_json

logger = logging.getLogger(__name__)

# 标题数超过此上限时跳过 LLM，只用启发式（避免超长 prompt / 高成本）
_MAX_TITLES_FOR_LLM = 120
_MAX_LEVEL = 6

# ── 启发式：编号前缀 → 层级 ──────────────────────────────────
_NUM_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)")          # 1 / 1.2 / 1.2.3
_CN_CHAPTER = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+\s*[章篇部]")  # 第一章 / 第1篇
_CN_SECTION = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+\s*节")        # 第一节
_CN_ENUM = re.compile(r"^\s*[一二三四五六七八九十]+\s*[、.．]")               # 一、二、
_PAREN_ENUM = re.compile(r"^\s*[（(]\s*\d+\s*[)）]")                          # （1）(1)
_CIRCLED = re.compile(r"^\s*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫]")                           # ①②


def heuristic_title_levels(titles: list[str]) -> list[int]:
    """仅凭编号/措辞推断层级（LLM 兜底）。无明显信号 → 1 级。"""
    levels: list[int] = []
    for raw in titles:
        t = (raw or "").strip()
        m = _NUM_PREFIX.match(t)
        if m:
            levels.append(min(m.group(1).count(".") + 1, _MAX_LEVEL))
            continue
        if _CN_CHAPTER.match(t):
            levels.append(1)
            continue
        if _CN_SECTION.match(t):
            levels.append(2)
            continue
        if _PAREN_ENUM.match(t) or _CIRCLED.match(t):
            levels.append(3)
            continue
        if _CN_ENUM.match(t):
            levels.append(1)
            continue
        levels.append(1)
    return levels


async def assign_title_levels(blocks: list[IRBlock]) -> list[IRBlock]:
    """
    推断标题层级并写回 `block.metadata.title_level`（原地修改，返回同一列表）。

    在 pipeline_service 步骤 [G] 的 `build_dom` 之前调用。
    """
    sorted_blocks = sorted(blocks, key=lambda b: b.order_in_doc)
    title_blocks = [b for b in sorted_blocks if b.type == "title" and (b.text or "").strip()]

    if len(title_blocks) <= 1:
        return blocks  # 0/1 个标题：层级无意义，保持现状

    texts = [b.text.strip() for b in title_blocks]

    heuristic = heuristic_title_levels(texts)
    levels: list[int] | None = None
    if len(title_blocks) <= _MAX_TITLES_FOR_LLM:
        levels = await _llm_levels(title_blocks, heuristic)
    if levels is None:
        levels = heuristic
        logger.info("[doc_tree] 用启发式层级（%d 个标题）", len(title_blocks))

    for b, lvl in zip(title_blocks, levels):
        b.metadata.title_level = int(lvl)

    return blocks


# LLM 索引覆盖率低于此比例 → 判定不可信，整体回退启发式
_MIN_COVERAGE = 0.6


async def _llm_levels(title_blocks: list[IRBlock], heuristic: list[int]) -> list[int] | None:
    """
    调 LLM 推断层级；失败 / 覆盖率过低 → None（交由启发式兜底）。

    用「索引回填」格式 {"items":[{"i":idx,"level":lvl}]} 而非定长数组——LLM 在长标题列表上
    常多/漏几项导致定长数组错位，按 i 取在范围内的项、缺口用启发式补，对 LLM 漂移更鲁棒。
    """
    n = len(title_blocks)
    try:
        lines = [
            f"[{i}] (第{b.page_idx + 1}页) {b.text.strip()}"
            for i, b in enumerate(title_blocks)
        ]
        system_prompt = load_prompt("doc_tree_system")
        raw = await call_llm_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"共 {n} 个标题，请逐个给出层级：\n" + "\n".join(lines)},
        ])
        data = json.loads(_strip_code_fence(raw))
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError("items 不是数组")

        by_index: dict[int, int] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            i = it.get("i")
            if not isinstance(i, int) or not (0 <= i < n):
                continue
            try:
                lvl = int(it.get("level"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            by_index[i] = min(max(lvl, 1), _MAX_LEVEL)

        if len(by_index) < n * _MIN_COVERAGE:
            raise ValueError(f"覆盖率过低 {len(by_index)}/{n}")

        merged = [by_index.get(i, heuristic[i]) for i in range(n)]
        logger.info("[doc_tree] LLM 推断层级成功（覆盖 %d/%d，其余启发式补）", len(by_index), n)
        return merged
    except Exception as exc:
        logger.warning("[doc_tree] LLM 层级推断失败，回退启发式: %s", exc)
        return None


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 输出中的 ```json ... ``` 代码块包裹。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner)
    return text.strip()
