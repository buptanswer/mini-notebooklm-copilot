"""
Index Builder Service — 父块「自定义索引」真功能（v1.5.0）

每个父块除常规子块索引外，可挂额外索引，提升检索召回的角度：
  - summary        摘要索引（LLM 依据父块全文生成一段摘要）
  - hypo_question  推测问题索引（LLM 推测读者会问的问题，可附预答；耗 API，默认关闭）
  - custom         自定义索引（用户手填的检索文本）

注：图片/表格的描述**不在此处单列索引**——基础切片管线已让每张图/表各成一个独立子块，
    retrieval_text=`[图片: VLM描述]`/`[表格: VLM摘要]`，且 text_for_generation 把描述 inline 在原位，
    故图/表描述天然参与常规子块检索；无需再造冗余的合并描述索引（曾经的 image_desc/table_desc 已废弃）。

存储与检索（关键设计）：
  parent_extra_indexes 表是「管理层 / source of truth」（定义、开关、可编辑文本、payload）。
  enabled 时把 index_text **物化**成 child_chunks 里一行虚拟子块（index_kind=kind），
  复用同一 embedding / FTS / Qdrant / RRF / 重排 / Small-to-Big 管线参与检索；
  disabled 时移除该虚拟行（连同 Qdrant 点与 FTS 行，由触发器同步）。
  → 检索侧零并行管线；命中后经 parent_chunk_id 天然回到父块（Small-to-Big）。

幂等：重解析时 index_service._purge_doc 会按 doc_id 清掉本表定义行与其物化虚拟子块，
      自定义索引随文档一起重建（父块边界会因粒度变化而变，强行保留映射会错乱）。
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from qdrant_client.models import PointStruct

from app.config import settings
from app.db.database import get_db
from app.db.qdrant_client import get_qdrant
from app.prompts import load_prompt
from app.services.cn_tokenizer import segment as _cn_segment
from app.services.embedding_service import embed_texts
from app.services.qa_service import call_llm_json

logger = logging.getLogger(__name__)

# 索引种类 → 中文展示名（前端可覆盖）
KIND_TITLE: dict[str, str] = {
    "summary": "摘要索引",
    "hypo_question": "推测问题索引",
    "custom": "自定义索引",
}
VALID_KINDS = frozenset(KIND_TITLE)

# 调 LLM 的种类（耗 API）；其余从解析阶段已有产物提取，不额外触网
_LLM_KINDS = frozenset({"summary", "hypo_question"})

_PARENT_TEXT_MAX = 6000  # 喂给 LLM 的父块正文上限（防超长）


class IndexBuildError(Exception):
    """生成失败（如父块内无图/表可提取描述、LLM 返回不可用等）。"""


# ─────────────────────────────────────────────────────────────
# 读取辅助
# ─────────────────────────────────────────────────────────────

async def _get_parent(parent_chunk_id: str) -> dict | None:
    """从 parent_chunks 表读父块（含 block_ids / text_full / header_path / page_span）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT parent_chunk_id, doc_id, section_id, header_path, title,
                      COALESCE(text_full,'') AS text_full, block_ids,
                      page_span_start, page_span_end
               FROM parent_chunks WHERE parent_chunk_id=?""",
            (parent_chunk_id,),
        )
        row = await cur.fetchone()
    finally:
        await db.close()
    if not row:
        return None
    r = dict(row)
    r["header_path"] = _loads_list(r.get("header_path"))
    r["block_ids"] = _loads_list(r.get("block_ids"))
    return r


def _loads_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _strip_code_fence(text: str) -> str:
    """剥去 LLM 可能套上的 ```json ... ``` 围栏。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


# ─────────────────────────────────────────────────────────────
# 各种索引文本生成
# ─────────────────────────────────────────────────────────────

async def _gen_summary(parent: dict) -> tuple[str, dict]:
    body = (parent.get("text_full") or "").strip()
    if not body:
        raise IndexBuildError("父块正文为空，无法生成摘要索引")
    messages = [
        {"role": "system", "content": load_prompt("index_summary_system")},
        {"role": "user", "content": body[:_PARENT_TEXT_MAX]},
    ]
    text = (await call_llm_json(messages)).strip()
    if not text:
        raise IndexBuildError("摘要索引生成结果为空")
    return text, {}


async def _gen_hypo_question(parent: dict, *, with_answer: bool) -> tuple[str, dict]:
    body = (parent.get("text_full") or "").strip()
    if not body:
        raise IndexBuildError("父块正文为空，无法生成推测问题索引")
    user = body[:_PARENT_TEXT_MAX]
    if with_answer:
        user += "\n\n（请附带答案：以 {\"questions\":[...], \"answers\":[...]} 格式输出。）"
    messages = [
        {"role": "system", "content": load_prompt("index_hypo_question_system")},
        {"role": "user", "content": user},
    ]
    raw = _strip_code_fence(await call_llm_json(messages))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IndexBuildError(f"推测问题索引返回非 JSON：{raw[:120]}") from exc

    questions = [str(q).strip() for q in (data.get("questions") or []) if str(q).strip()]
    if not questions:
        raise IndexBuildError("推测问题索引未生成任何问题")
    answers = [str(a).strip() for a in (data.get("answers") or [])]

    # 索引文本 = 推测问题逐行拼接（用户问类似问题时向量近邻命中）
    index_text = "\n".join(questions)
    payload: dict = {"questions": questions}
    if answers:
        payload["answers"] = answers
    return index_text, payload


# ─────────────────────────────────────────────────────────────
# 物化 / 反物化（虚拟子块 ↔ child_chunks + Qdrant + FTS）
# ─────────────────────────────────────────────────────────────

async def _materialize(index_row: dict, parent: dict) -> dict:
    """把 enabled 的索引文本落成 child_chunks 虚拟行 + Qdrant 单点，回写 id。"""
    index_text = (index_row.get("index_text") or "").strip()
    if not index_text:
        raise IndexBuildError("索引文本为空，无法启用")

    vectors = await embed_texts([index_text], text_type="document")
    vec = vectors[0]

    child_chunk_id = index_row.get("child_chunk_id") or f"ci-{uuid.uuid4().hex[:12]}"
    point_id = index_row.get("qdrant_point_id") or str(uuid.uuid4())
    doc_id = index_row["doc_id"]
    kind = index_row["kind"]
    header_path = parent.get("header_path") or []
    page_start = parent.get("page_span_start") or 0
    page_end = parent.get("page_span_end") or 0

    # Qdrant 单点 upsert（payload 与常规子块同构，仅 index_kind 非空）
    client = get_qdrant()
    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[PointStruct(
            id=point_id,
            vector=vec,
            payload={
                "child_chunk_id": child_chunk_id,
                "parent_chunk_id": index_row["parent_chunk_id"],
                "doc_id": doc_id,
                "section_id": index_row.get("section_id", ""),
                "chunk_type": "paragraph",
                "header_path": header_path,
                "embedding_text": index_text,
                "retrieval_text": index_text,
                "page_span_start": page_start,
                "page_span_end": page_end,
                "bbox_norm1000": [],
                "bbox_page": [],
                "anchor_origin_pdf_path": "",
                "asset_paths": [],
                "index_kind": kind,
            },
        )],
    )

    # child_chunks 虚拟行（INSERT OR REPLACE → 触发器同步 FTS）
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO child_chunks
               (child_chunk_id, parent_chunk_id, doc_id, section_id, chunk_type,
                header_path, embedding_text, retrieval_text,
                page_span_start, page_span_end,
                bbox_norm1000, bbox_page, anchor_origin_pdf_path,
                qdrant_point_id, asset_paths, index_kind, fts_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                child_chunk_id, index_row["parent_chunk_id"], doc_id,
                index_row.get("section_id", ""), "paragraph",
                json.dumps(header_path, ensure_ascii=False), index_text, index_text,
                page_start, page_end,
                "[]", "[]", "",
                point_id, "[]", kind, _cn_segment(index_text),
            ),
        )
        await db.execute(
            """UPDATE parent_extra_indexes
               SET enabled=1, child_chunk_id=?, qdrant_point_id=?, updated_at=datetime('now')
               WHERE index_id=?""",
            (child_chunk_id, point_id, index_row["index_id"]),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info("物化索引 %s(kind=%s) → child=%s", index_row["index_id"], kind, child_chunk_id)
    index_row = {**index_row, "enabled": 1, "child_chunk_id": child_chunk_id, "qdrant_point_id": point_id}
    return index_row


async def _dematerialize(index_row: dict) -> dict:
    """移除 enabled 索引的物化虚拟行 + Qdrant 点（FTS 由触发器同步）。"""
    child_chunk_id = index_row.get("child_chunk_id") or ""
    point_id = index_row.get("qdrant_point_id") or ""

    if point_id:
        try:
            get_qdrant().delete(
                collection_name=settings.qdrant_collection,
                points_selector=[point_id],
            )
        except Exception as exc:
            logger.warning("删除索引 Qdrant 点失败（继续）: %s", exc)

    db = await get_db()
    try:
        if child_chunk_id:
            await db.execute("DELETE FROM child_chunks WHERE child_chunk_id=?", (child_chunk_id,))
        await db.execute(
            """UPDATE parent_extra_indexes
               SET enabled=0, child_chunk_id='', qdrant_point_id='', updated_at=datetime('now')
               WHERE index_id=?""",
            (index_row["index_id"],),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info("反物化索引 %s(kind=%s)", index_row["index_id"], index_row.get("kind"))
    return {**index_row, "enabled": 0, "child_chunk_id": "", "qdrant_point_id": ""}


# ─────────────────────────────────────────────────────────────
# 对外 API
# ─────────────────────────────────────────────────────────────

async def list_doc_indexes(doc_id: str) -> list[dict]:
    """列出该文档全部自定义索引（按 parent_chunk_id 聚合由调用方处理）。"""
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT index_id, doc_id, parent_chunk_id, section_id, kind, title,
                      index_text, payload, enabled, source, child_chunk_id,
                      qdrant_point_id, created_at, updated_at
               FROM parent_extra_indexes WHERE doc_id=?
               ORDER BY parent_chunk_id, kind, created_at""",
            (doc_id,),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()
    return [_row_to_public(dict(r)) for r in rows]


async def _get_index_row(index_id: str) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT index_id, doc_id, parent_chunk_id, section_id, kind, title,
                      index_text, payload, enabled, source, child_chunk_id, qdrant_point_id
               FROM parent_extra_indexes WHERE index_id=?""",
            (index_id,),
        )
        row = await cur.fetchone()
    finally:
        await db.close()
    return dict(row) if row else None


def _row_to_public(r: dict) -> dict:
    """DB 行 → 对外 dict（payload 解析为对象，enabled 转 bool）。"""
    payload = r.get("payload") or "{}"
    try:
        payload_obj = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError:
        payload_obj = {}
    return {
        "index_id": r["index_id"],
        "doc_id": r["doc_id"],
        "parent_chunk_id": r["parent_chunk_id"],
        "section_id": r.get("section_id", ""),
        "kind": r["kind"],
        "title": r.get("title") or KIND_TITLE.get(r["kind"], r["kind"]),
        "index_text": r.get("index_text", ""),
        "payload": payload_obj if isinstance(payload_obj, dict) else {},
        "enabled": bool(r.get("enabled")),
        "source": r.get("source", "auto"),
        "child_chunk_id": r.get("child_chunk_id", ""),
        "created_at": r.get("created_at", ""),
        "updated_at": r.get("updated_at", ""),
    }


async def generate_index(
    doc_id: str,
    parent_chunk_id: str,
    kind: str,
    *,
    custom_text: str | None = None,
    title: str | None = None,
    with_answer: bool = False,
    enable: bool = False,
) -> dict:
    """生成（或对 custom 手填）一条父块索引；enable=True 时立即物化参与检索。"""
    if kind not in VALID_KINDS:
        raise IndexBuildError(f"未知索引类型：{kind}")
    parent = await _get_parent(parent_chunk_id)
    if not parent or parent["doc_id"] != doc_id:
        raise IndexBuildError("父块不存在或不属于该文档")

    # 生成索引文本 + payload
    if kind == "summary":
        index_text, payload = await _gen_summary(parent)
        source = "auto"
    elif kind == "hypo_question":
        index_text, payload = await _gen_hypo_question(parent, with_answer=with_answer)
        source = "auto"
    else:  # custom
        index_text = (custom_text or "").strip()
        if not index_text:
            raise IndexBuildError("自定义索引文本不能为空")
        payload = {}
        source = "user"

    index_id = f"idx-{uuid.uuid4().hex[:12]}"
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO parent_extra_indexes
               (index_id, doc_id, parent_chunk_id, section_id, kind, title,
                index_text, payload, enabled, source)
               VALUES (?,?,?,?,?,?,?,?,0,?)""",
            (
                index_id, doc_id, parent_chunk_id, parent.get("section_id", ""),
                kind, title or KIND_TITLE.get(kind, kind),
                index_text, json.dumps(payload, ensure_ascii=False), source,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    row = await _get_index_row(index_id)
    assert row is not None
    if enable:
        row = await _materialize(row, parent)
        row = (await _get_index_row(index_id)) or row
    return _row_to_public(row)


async def set_index_enabled(index_id: str, enabled: bool) -> dict:
    """开关一条索引：启用→物化参与检索；停用→移除虚拟行。"""
    row = await _get_index_row(index_id)
    if not row:
        raise IndexBuildError("索引不存在")
    currently = bool(row.get("enabled"))
    if enabled and not currently:
        parent = await _get_parent(row["parent_chunk_id"])
        if not parent:
            raise IndexBuildError("父块不存在，无法启用索引")
        row = await _materialize(row, parent)
    elif not enabled and currently:
        row = await _dematerialize(row)
    fresh = await _get_index_row(index_id)
    return _row_to_public(fresh or row)


async def update_index(
    index_id: str,
    *,
    index_text: str | None = None,
    title: str | None = None,
    payload: dict | None = None,
) -> dict:
    """编辑索引文本/标题/payload；若当前启用则重新物化（重嵌入 + 刷新 Qdrant/FTS）。"""
    row = await _get_index_row(index_id)
    if not row:
        raise IndexBuildError("索引不存在")

    sets: list[str] = []
    vals: list[object] = []
    if index_text is not None:
        cleaned = index_text.strip()
        if not cleaned:
            raise IndexBuildError("索引文本不能为空")
        sets.append("index_text=?")
        vals.append(cleaned)
    if title is not None:
        sets.append("title=?")
        vals.append(title.strip())
    if payload is not None:
        sets.append("payload=?")
        vals.append(json.dumps(payload, ensure_ascii=False))
    if not sets:
        return _row_to_public(row)

    sets.append("updated_at=datetime('now')")
    db = await get_db()
    try:
        await db.execute(
            f"UPDATE parent_extra_indexes SET {', '.join(sets)} WHERE index_id=?",
            (*vals, index_id),
        )
        await db.commit()
    finally:
        await db.close()

    fresh = await _get_index_row(index_id)
    assert fresh is not None
    # 启用中且改了文本 → 重新物化（先反物化再物化，保证向量/FTS 与新文本一致）
    if bool(fresh.get("enabled")) and index_text is not None:
        parent = await _get_parent(fresh["parent_chunk_id"])
        if parent:
            await _dematerialize(fresh)
            fresh2 = await _get_index_row(index_id)
            if fresh2:
                await _materialize(fresh2, parent)
        fresh = await _get_index_row(index_id) or fresh
    return _row_to_public(fresh)


async def regenerate_index(index_id: str, *, with_answer: bool = False) -> dict:
    """对 auto 类索引重新生成文本（保持启用状态：启用中的会重新物化）。"""
    row = await _get_index_row(index_id)
    if not row:
        raise IndexBuildError("索引不存在")
    kind = row["kind"]
    if kind == "custom":
        raise IndexBuildError("自定义索引无法自动重生成，请直接编辑")
    parent = await _get_parent(row["parent_chunk_id"])
    if not parent:
        raise IndexBuildError("父块不存在")

    if kind == "summary":
        index_text, payload = await _gen_summary(parent)
    elif kind == "hypo_question":
        index_text, payload = await _gen_hypo_question(parent, with_answer=with_answer)
    else:
        raise IndexBuildError(f"该索引类型不支持自动重生成：{kind}")

    return await update_index(index_id, index_text=index_text, payload=payload)


async def delete_index(index_id: str) -> None:
    """删除一条索引（先反物化清理虚拟行/Qdrant，再删定义行）。"""
    row = await _get_index_row(index_id)
    if not row:
        raise IndexBuildError("索引不存在")
    if bool(row.get("enabled")):
        await _dematerialize(row)
    db = await get_db()
    try:
        await db.execute("DELETE FROM parent_extra_indexes WHERE index_id=?", (index_id,))
        await db.commit()
    finally:
        await db.close()
    logger.info("删除索引 %s", index_id)
