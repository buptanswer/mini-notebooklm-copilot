"""
Query Planner — 检索查询规划（v1.4.0）

直接拿用户问题原文做 BM25 + 向量检索效果不好。本服务先让 LLM 把问题改写成更适合
检索的形式，产出「检索计划」：
  - keywords:        用于 BM25 关键词检索的核心词（去停用词 + 适度扩展同义词）
  - semantic_query:  用于语义向量检索的一句"假设答案"陈述句（HyDE 思路，比疑问句更贴正文）
  - rewritten_question: 补全后的独立问句（消指代/补上下文）

设计要点：
  - 提示词外置 prompts/query_plan_system.md（遵循 prompts/ 约定）。
  - LLM 失败 / JSON 非法 → 回退用问题原文（keywords 走朴素分词），**绝不阻断检索**。
  - 这是「检索透视」可视化的第一步，也是真实问答检索质量的来源。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.prompts import load_prompt
from app.services.qa_service import call_llm_json

logger = logging.getLogger(__name__)

# 简单中文/英文停用词（仅用于回退分词，不追求完备）
_STOPWORDS = frozenset({
    "的", "了", "吗", "呢", "吧", "啊", "是", "在", "和", "与", "及", "或",
    "怎么", "怎样", "如何", "什么", "哪些", "哪个", "请问", "我", "你", "他",
    "这", "那", "这门", "这个", "一下", "可以", "需要", "有没有", "为什么",
    "the", "a", "an", "is", "are", "of", "to", "and", "or", "how", "what",
    "which", "do", "does", "can", "i", "you", "for", "在于",
})
_TOKEN_SPLIT = re.compile(r"[\s,，。、？?!！；;:：（）()\[\]【】\"'\-—/\\]+")


@dataclass
class QueryPlan:
    """检索查询规划结果。"""
    original_question: str
    rewritten_question: str
    keywords: list[str] = field(default_factory=list)
    semantic_query: str = ""
    source: str = "llm"          # "llm" | "fallback"

    def to_dict(self) -> dict:
        return {
            "original_question": self.original_question,
            "rewritten_question": self.rewritten_question,
            "keywords": self.keywords,
            "semantic_query": self.semantic_query,
            "source": self.source,
        }


async def plan_query(question: str) -> QueryPlan:
    """把用户问题规划为检索计划。LLM 失败时回退到朴素分词。"""
    question = (question or "").strip()
    if not question:
        return QueryPlan(original_question="", rewritten_question="", keywords=[], semantic_query="", source="fallback")

    try:
        system_prompt = load_prompt("query_plan_system")
        raw = await call_llm_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户问题：{question}"},
        ])
        data = json.loads(_strip_code_fence(raw))
        keywords = _clean_keywords(data.get("keywords"))
        semantic_query = (data.get("semantic_query") or "").strip()
        rewritten = (data.get("rewritten_question") or "").strip()
        if not keywords or not semantic_query:
            # LLM 返回结构不完整 → 用回退补齐缺的部分
            raise ValueError("LLM 检索计划字段不完整")
        return QueryPlan(
            original_question=question,
            rewritten_question=rewritten or question,
            keywords=keywords,
            semantic_query=semantic_query,
            source="llm",
        )
    except Exception as exc:
        logger.warning("查询规划失败，回退用问题原文: %s", exc)
        return _fallback_plan(question)


def _fallback_plan(question: str) -> QueryPlan:
    """LLM 不可用时的回退：朴素分词作关键词，问题原文作语义查询。"""
    return QueryPlan(
        original_question=question,
        rewritten_question=question,
        keywords=_naive_keywords(question) or [question],
        semantic_query=question,
        source="fallback",
    )


def _naive_keywords(text: str, limit: int = 8) -> list[str]:
    """朴素分词：去停用词与过短 token，保留前 limit 个。"""
    tokens = [t for t in _TOKEN_SPLIT.split(text) if t]
    out: list[str] = []
    for t in tokens:
        if t.lower() in _STOPWORDS:
            continue
        if len(t) < 2 and not t.isalnum():
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _clean_keywords(value: object, limit: int = 8) -> list[str]:
    """规整 LLM 返回的 keywords：转字符串、去空、去重、限量。"""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


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
