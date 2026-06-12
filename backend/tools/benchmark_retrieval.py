"""检索质量评测脚本 —— 把「效果不弱于大厂」做成可复现的数字。

本脚本服务于结题文档对「检索质量」的量化展示，提供两种模式：

  1) 离线消融（--ablation，默认）：**无需任何 API Key**。
     直接读已索引的 SQLite（child_chunks），在内存里建两套 FTS5 索引——
       · raw  ：对 embedding_text 原样建 unicode61 索引（中文整段当一个 token）
       · jieba：对 jieba 分词后的文本建索引（与项目线上一致）
     用 gold set 的问题分别查两套索引，对比中文 BM25 召回——复现
     「中文关键词召回 0 → N」这一真机修复。这是最诚实、最容易复现的硬数字。

  2) 完整评测（--full）：**需要 API Key + 已索引知识库**，运行前必须停掉 uvicorn
     （Qdrant 本地文件模式单进程文件锁）。复用项目线上检索服务，跑 5 种配置：
       BM25(jieba) / 向量 / 混合 RRF / 混合+重排
     对每条 gold 问题计算 Hit@k / Recall@k / MRR / nDCG@k，输出可粘回 PPT 的表格。

Gold set（人工标注的小评测集）格式见 benchmark_gold_set.example.json：
  [
    {"query": "考核方式是什么", "kb_id": "<kb_id>",
     "relevant_doc_ids": ["<doc_id>", ...],          // 文档级标注（推荐，省事）
     "relevant_child_chunk_ids": ["<child_id>", ...]}  // 片段级标注（可选，更精）
  ]
一条结果被判为「相关」：命中 doc_id ∈ relevant_doc_ids 或 child_chunk_id ∈ relevant_child_chunk_ids。

用法（在 backend/ 下）：
  uv run python tools/benchmark_retrieval.py --ablation --gold tools/benchmark_gold_set.json
  uv run python tools/benchmark_retrieval.py --full     --gold tools/benchmark_gold_set.json
  uv run python tools/benchmark_retrieval.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows 控制台 / 管道默认 gbk，中文输出会 UnicodeEncodeError —— 统一切到 UTF-8
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 允许以 `python tools/benchmark_retrieval.py` 方式运行（把 backend/ 加入 import 路径）
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.cn_tokenizer import segment, segment_tokens  # noqa: E402

_DEFAULT_KS = (1, 3, 5, 10)


# ─────────────────────────────────────────────────────────────
# Gold set
# ─────────────────────────────────────────────────────────────

@dataclass
class GoldItem:
    query: str
    kb_id: str
    relevant_doc_ids: list[str] = field(default_factory=list)
    relevant_child_chunk_ids: list[str] = field(default_factory=list)

    def is_relevant(self, doc_id: str, child_chunk_id: str) -> bool:
        return bool(doc_id and doc_id in self.relevant_doc_ids) or bool(
            child_chunk_id and child_chunk_id in self.relevant_child_chunk_ids
        )

    @property
    def n_relevant(self) -> int:
        # 评测的相关项总数：优先用片段级，否则用文档级
        n = len(self.relevant_child_chunk_ids) or len(self.relevant_doc_ids)
        return max(n, 1)


def load_gold(path: Path) -> list[GoldItem]:
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 gold set: {path}\n"
            f"请先复制 tools/benchmark_gold_set.example.json 为 {path.name} 并按你的课程资料填写。"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[GoldItem] = []
    for i, obj in enumerate(raw):
        if not obj.get("query") or not obj.get("kb_id"):
            raise ValueError(f"gold set 第 {i} 条缺少 query 或 kb_id")
        items.append(GoldItem(
            query=str(obj["query"]),
            kb_id=str(obj["kb_id"]),
            relevant_doc_ids=[str(x) for x in obj.get("relevant_doc_ids", [])],
            relevant_child_chunk_ids=[str(x) for x in obj.get("relevant_child_chunk_ids", [])],
        ))
    if not items:
        raise ValueError("gold set 为空")
    return items


# ─────────────────────────────────────────────────────────────
# 指标
# ─────────────────────────────────────────────────────────────

def _relevance_flags(ranked: list[tuple[str, str]], gold: GoldItem) -> list[int]:
    """ranked = [(doc_id, child_chunk_id), ...]（已按相关性降序）→ 0/1 相关标记。

    **按相关性判定单元去重**：同一相关文档（或片段）只在首次出现处计 1，
    后续重复命中计 0。否则文档级标注下「一个相关文档的多个子块都进 top-k」
    会让命中数超过 n_relevant，导致 Recall / nDCG > 1。
    """
    flags: list[int] = []
    seen: set[tuple[str, str]] = set()
    for doc_id, cid in ranked:
        key: tuple[str, str] | None = None
        if gold.relevant_child_chunk_ids and cid in gold.relevant_child_chunk_ids:
            key = ("c", cid)
        elif doc_id in gold.relevant_doc_ids:
            key = ("d", doc_id)
        if key is not None and key not in seen:
            seen.add(key)
            flags.append(1)
        else:
            flags.append(0)
    return flags


def hit_at_k(flags: list[int], k: int) -> float:
    return 1.0 if any(flags[:k]) else 0.0


def recall_at_k(flags: list[int], n_relevant: int, k: int) -> float:
    return min(sum(flags[:k]), n_relevant) / n_relevant if n_relevant else 0.0


def mrr(flags: list[int]) -> float:
    for rank, f in enumerate(flags, start=1):
        if f:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(flags: list[int], n_relevant: int, k: int) -> float:
    dcg = sum(f / math.log2(i + 2) for i, f in enumerate(flags[:k]))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(n_relevant, k)))
    return dcg / ideal if ideal else 0.0


@dataclass
class ConfigMetrics:
    name: str
    n_queries: int = 0
    hit: dict[int, float] = field(default_factory=dict)
    recall: dict[int, float] = field(default_factory=dict)
    mrr_sum: float = 0.0
    ndcg: dict[int, float] = field(default_factory=dict)

    def add(self, flags: list[int], n_relevant: int, ks: tuple[int, ...]) -> None:
        self.n_queries += 1
        self.mrr_sum += mrr(flags)
        for k in ks:
            self.hit[k] = self.hit.get(k, 0.0) + hit_at_k(flags, k)
            self.recall[k] = self.recall.get(k, 0.0) + recall_at_k(flags, n_relevant, k)
            self.ndcg[k] = self.ndcg.get(k, 0.0) + ndcg_at_k(flags, n_relevant, k)

    def avg_mrr(self) -> float:
        return self.mrr_sum / self.n_queries if self.n_queries else 0.0

    def avg(self, table: dict[int, float], k: int) -> float:
        return table.get(k, 0.0) / self.n_queries if self.n_queries else 0.0


def print_metrics_table(configs: list[ConfigMetrics], ks: tuple[int, ...]) -> None:
    cols = ["配置"] + [f"Hit@{k}" for k in ks] + [f"Recall@{k}" for k in ks] + ["MRR"] + [f"nDCG@{k}" for k in ks]
    rows: list[list[str]] = []
    for c in configs:
        row = [c.name]
        row += [f"{c.avg(c.hit, k):.3f}" for k in ks]
        row += [f"{c.avg(c.recall, k):.3f}" for k in ks]
        row += [f"{c.avg_mrr():.3f}"]
        row += [f"{c.avg(c.ndcg, k):.3f}" for k in ks]
        rows.append(row)
    _print_grid(cols, rows)


def _print_grid(header: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in header]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(header))
    print(line)
    print("  ".join("-" * widths[i] for i in range(len(header))))
    for r in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))


# ─────────────────────────────────────────────────────────────
# 模式一：离线 jieba 分词消融（无需 API Key）
# ─────────────────────────────────────────────────────────────

def _fts_phrase(text: str) -> str:
    """把整条查询当一个短语 MATCH（raw 路：中文整段=一个 token，几乎零召回）。"""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text).strip()
    return f'"{cleaned}"' if cleaned else '""'


def _fts_or(tokens: list[str]) -> str:
    """jieba 路：分词 token 以 OR 连接，命中任一即可。"""
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else '""'


def run_ablation(gold: list[GoldItem], ks: tuple[int, ...]) -> int:
    db_path = settings.sqlite_path
    if not db_path.exists():
        print(f"[错误] 找不到 SQLite：{db_path}，请先启动后端并至少索引一篇文档。")
        return 1

    src = sqlite3.connect(str(db_path))
    src.row_factory = sqlite3.Row
    chunks = src.execute(
        "SELECT child_chunk_id, doc_id, embedding_text FROM child_chunks"
    ).fetchall()
    src.close()
    if not chunks:
        print("[错误] child_chunks 为空：还没有任何已索引的子块。")
        return 1
    print(f"[离线消融] 载入 {len(chunks)} 个子块，构建 raw / jieba 两套 FTS5 索引…")

    mem = sqlite3.connect(":memory:")
    mem.execute("CREATE VIRTUAL TABLE raw_fts USING fts5(cid, doc, txt, tokenize='unicode61')")
    mem.execute("CREATE VIRTUAL TABLE jb_fts  USING fts5(cid, doc, txt, tokenize='unicode61')")
    for ch in chunks:
        text = ch["embedding_text"] or ""
        mem.execute("INSERT INTO raw_fts(cid, doc, txt) VALUES (?,?,?)",
                    (ch["child_chunk_id"], ch["doc_id"], text))
        mem.execute("INSERT INTO jb_fts(cid, doc, txt) VALUES (?,?,?)",
                    (ch["child_chunk_id"], ch["doc_id"], segment(text)))
    mem.commit()

    limit = max(ks)
    raw_cfg = ConfigMetrics(name="BM25 · 无 jieba")
    jb_cfg = ConfigMetrics(name="BM25 · jieba（项目线上）")

    for item in gold:
        raw_q = _fts_phrase(item.query)
        jb_q = _fts_or(segment_tokens(item.query))
        raw_hits = _query_mem(mem, "raw_fts", raw_q, limit)
        jb_hits = _query_mem(mem, "jb_fts", jb_q, limit)
        raw_cfg.add(_relevance_flags(raw_hits, item), item.n_relevant, ks)
        jb_cfg.add(_relevance_flags(jb_hits, item), item.n_relevant, ks)
    mem.close()

    print(f"\n=== 中文 BM25 分词消融（{len(gold)} 条查询，仅 SQLite，无 API）===")
    print_metrics_table([raw_cfg, jb_cfg], ks)
    print("\n说明：raw 路把中文整段当一个 token，故中文查询几乎零召回；jieba 分词后召回显著提升——"
          "复现结题文档「关键词召回 0 → N」的真机修复。")
    return 0


def _query_mem(conn: sqlite3.Connection, table: str, match: str, limit: int) -> list[tuple[str, str]]:
    try:
        rows = conn.execute(
            f"SELECT doc, cid FROM {table} WHERE {table} MATCH ? ORDER BY bm25({table}) LIMIT ?",
            (match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r[0], r[1]) for r in rows]


# ─────────────────────────────────────────────────────────────
# 模式二：完整管线评测（需 API Key + 已索引数据，运行前停 uvicorn）
# ─────────────────────────────────────────────────────────────

async def run_full(gold: list[GoldItem], ks: tuple[int, ...], top_n: int) -> int:
    # 延迟导入：避免离线消融模式也加载 Qdrant / embedding 依赖
    from app.services.rerank_service import rerank
    from app.services.retrieval_service import (
        RetrievedChunk,
        hybrid_search,
        keyword_search,
        vector_search,
    )

    limit = max(max(ks), top_n)
    cfgs = {
        "BM25 · jieba": ConfigMetrics(name="BM25 · jieba"),
        "向量": ConfigMetrics(name="向量"),
        "混合 RRF": ConfigMetrics(name="混合 RRF"),
        "混合 + 重排": ConfigMetrics(name="混合 + 重排"),
    }

    def flags(hits: list[RetrievedChunk], item: GoldItem) -> list[int]:
        return _relevance_flags([(h.doc_id, h.child_chunk_id) for h in hits], item)

    for idx, item in enumerate(gold, start=1):
        print(f"[完整评测] ({idx}/{len(gold)}) {item.query[:30]}…")
        try:
            kw = await keyword_search(item.query, item.kb_id, limit=limit, match_mode="or")
            vec = await vector_search(item.query, item.kb_id, limit=limit)
            hyb = await hybrid_search(item.query, item.kb_id, top_k=limit)
            rer = await rerank(item.query, hyb, top_n=top_n)
        except Exception as exc:  # 真机依赖外部 API，单条失败不中断整轮
            print(f"  [跳过] 检索失败：{exc}")
            continue
        cfgs["BM25 · jieba"].add(flags(kw, item), item.n_relevant, ks)
        cfgs["向量"].add(flags(vec, item), item.n_relevant, ks)
        cfgs["混合 RRF"].add(flags(hyb, item), item.n_relevant, ks)
        cfgs["混合 + 重排"].add(flags(rer, item), item.n_relevant, ks)

    print(f"\n=== 完整管线检索质量（{len(gold)} 条查询）===")
    print_metrics_table(list(cfgs.values()), ks)
    print("\n说明：把表中数字粘回结题 PPT 的「检索质量评测」页即可。"
          "混合 / 重排相对向量的增益随语料规模与噪声增大而显现；小而干净的评测集上向量往往已接近上限——"
          "请按实测如实呈现，不必为「重排一定更好」而调数。")
    return 0


# ─────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mini-NotebookLM 检索质量评测（离线 jieba 消融 / 完整管线）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ablation", action="store_true", help="离线 jieba 分词消融（默认，无需 API Key）")
    mode.add_argument("--full", action="store_true", help="完整管线评测（需 Key + 已索引，先停 uvicorn）")
    parser.add_argument("--gold", type=Path, default=_BACKEND_ROOT / "tools" / "benchmark_gold_set.json",
                        help="gold set JSON 路径（默认 tools/benchmark_gold_set.json）")
    parser.add_argument("--k", type=int, nargs="+", default=list(_DEFAULT_KS), help="评测的 k 值（默认 1 3 5 10）")
    parser.add_argument("--top-n", type=int, default=5, help="重排后保留条数（默认 5）")
    args = parser.parse_args(argv)

    ks = tuple(sorted(set(int(k) for k in args.k)))
    try:
        gold = load_gold(args.gold)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[错误] {exc}")
        return 2

    print(f"已载入 gold set：{len(gold)} 条查询（{args.gold}）\n")
    if args.full:
        return asyncio.run(run_full(gold, ks, args.top_n))
    return run_ablation(gold, ks)


if __name__ == "__main__":
    raise SystemExit(main())
