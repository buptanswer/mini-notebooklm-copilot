"""中文分词（jieba）—— 为 FTS5 关键词检索提供中文支持。

背景：SQLite FTS5 的 `unicode61` tokenizer 不对中文分词——它把连续的 CJK 字符当作
**一个** token（"知识库系统" = 单 token），故中文 BM25 关键词检索几乎零召回（查询
"知识库" 无法命中 token "知识库系统"）。

方案：用 jieba 把文本切成「空格分隔的词」。
  - 索引侧：把 `embedding_text` 分词后写入 `child_chunks.fts_text`，FTS 索引该列，
    unicode61 据空格切出词 token（知识库 / 系统 / …）。
  - 查询侧：把关键词同样分词，构建 FTS MATCH（见 retrieval_service._build_fts_query）。
中英混合通用：jieba 对英文单词 / 数字按原样保留为 token。
"""

from __future__ import annotations

import logging
import re

import jieba

# 关掉 jieba 首次构建前缀词典时打到 stderr 的 INFO 噪声
jieba.setLogLevel(logging.WARNING)

# 纯标点 / 空白 token（分词后丢弃，避免污染 FTS 索引与查询）。
# 中文/英文/数字属于 \w（re.UNICODE），不会被判为纯标点而保留。
_PUNCT_ONLY = re.compile(r"[\s　\W_]+", re.UNICODE)


def _clean_tokens(text: str) -> list[str]:
    """jieba 搜索引擎模式分词（更细粒度、利于召回）+ 去标点/空白。"""
    out: list[str] = []
    for tok in jieba.cut_for_search(text or ""):
        tok = tok.strip()
        if tok and not _PUNCT_ONLY.fullmatch(tok):
            out.append(tok)
    return out


def segment(text: str) -> str:
    """分词 → 空格连接（写入 FTS 的 `fts_text`，让 unicode61 据空格切出词 token）。"""
    return " ".join(_clean_tokens(text))


def segment_tokens(text: str) -> list[str]:
    """分词去重 token 列表（保序），用于构建 FTS5 MATCH 查询。"""
    seen: list[str] = []
    for tok in _clean_tokens(text):
        if tok not in seen:
            seen.append(tok)
    return seen
