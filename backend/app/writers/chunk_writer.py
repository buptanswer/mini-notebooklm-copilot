"""
Chunk Writer — 将 ParentChunk / ChildChunk 序列化为 JSONL 文件

输出：
  {rag_output_dir}/{doc_id}/parent_chunks.jsonl
  {rag_output_dir}/{doc_id}/child_chunks.jsonl

格式：每行一个 JSON 对象，UTF-8，无 BOM
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.models.models_chunk import ChildChunk, ParentChunk

logger = logging.getLogger(__name__)


def write_chunks(
    doc_id: str,
    parent_chunks: list[ParentChunk],
    child_chunks: list[ChildChunk],
) -> tuple[Path, Path]:
    """
    写出 parent_chunks.jsonl 和 child_chunks.jsonl。

    Returns:
        (parent_path, child_path)
    """
    out_dir = settings.rag_output_dir / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)

    parent_path = out_dir / "parent_chunks.jsonl"
    child_path = out_dir / "child_chunks.jsonl"

    with open(parent_path, "w", encoding="utf-8") as f:
        for pc in parent_chunks:
            f.write(pc.model_dump_json() + "\n")

    with open(child_path, "w", encoding="utf-8") as f:
        for cc in child_chunks:
            f.write(cc.model_dump_json() + "\n")

    logger.info(
        "写出 chunks: %d parent → %s | %d child → %s",
        len(parent_chunks), parent_path,
        len(child_chunks), child_path,
    )
    return parent_path, child_path
