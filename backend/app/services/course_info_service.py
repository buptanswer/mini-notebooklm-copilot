"""
课程管家服务（模块九）

核心流程：
  1. 用 5 条固定查询对 KB 做 hybrid_search
  2. 汇总去重检索结果
  3. 单次 LLM 调用做 JSON 结构化抽取
  4. 规范化 deadlines（解析日期 + 计算 days_left）
  5. 存入 course_info_cards 表
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone

from app.db.database import get_db
from app.prompts import load_prompt
from app.services.qa_service import call_llm_json
from app.services.retrieval_service import hybrid_search

_QUERIES = [
    "考核方式 评分标准 成绩比例 平时分 期末分",
    "作业要求 截止时间 提交方式",
    "考试时间 期中 期末 时间安排",
    "老师 联系方式 答疑时间 邮箱 微信 QQ",
    "重要通知 注意事项 教材",
]


async def generate_card(kb_id: str) -> dict:
    """
    触发课程信息卡片生成（或重新生成）。
    同步等待 LLM 返回，前端可显示加载动画。
    """
    # 1. 并行 5 查询
    import asyncio
    all_chunks_lists = await asyncio.gather(
        *[hybrid_search(q, kb_id, top_k=5) for q in _QUERIES]
    )

    # 2. 去重合并（以 child_chunk_id 为 key）
    seen: dict[str, object] = {}
    for chunks in all_chunks_lists:
        for c in chunks:
            if c.child_chunk_id not in seen:
                seen[c.child_chunk_id] = c

    all_chunks = list(seen.values())

    if not all_chunks:
        raise ValueError("该知识库暂无可检索内容，请先上传并解析文档")

    # 3. 构建 LLM messages
    context_parts = []
    for i, c in enumerate(all_chunks, 1):
        context_parts.append(f"[来源{i}]\n{c.retrieval_text or c.embedding_text}")
    context_text = "\n---\n".join(context_parts)

    system_prompt = load_prompt("course_info_extract_system")
    user_content = f"【参考资料】\n{context_text}\n\n请根据上述资料提取课程信息，返回 JSON。"

    # 4. 调用 LLM（非流式）
    raw_response = await call_llm_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ])

    # 5. 解析 JSON（去掉 markdown 代码块包裹）
    json_text = _strip_code_fence(raw_response)
    try:
        extracted = json.loads(json_text)
    except json.JSONDecodeError:
        extracted = {}

    # 6. 规范化 deadlines
    today = date.today()
    deadlines_raw = extracted.get("deadlines") or []
    deadlines_normalized = []
    for dl in deadlines_raw:
        name = dl.get("name", "")
        date_text = dl.get("date_text", "")
        desc = dl.get("description", "")
        parsed_date = parse_natural_date(date_text, today)
        entry: dict = {"name": name, "date_text": date_text, "description": desc}
        if parsed_date:
            entry["date"] = parsed_date.isoformat()
            entry["days_left"] = (parsed_date - today).days
        else:
            entry["date"] = ""
            entry["days_left"] = None
        deadlines_normalized.append(entry)

    # 7. 存入 DB（UPSERT：同一 kb_id 只保留一条卡片）
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        cur = await db.execute("SELECT card_id FROM course_info_cards WHERE kb_id=?", (kb_id,))
        existing = await cur.fetchone()
        source_ids = json.dumps([c.doc_id for c in all_chunks], ensure_ascii=False)

        if existing:
            card_id = dict(existing)["card_id"]
            await db.execute(
                """UPDATE course_info_cards
                   SET course_name=?, instructor=?, contact=?, assessment=?,
                       deadlines=?, important_notes=?, deadlines_normalized=?,
                       source_doc_ids=?, updated_at=?
                   WHERE card_id=?""",
                (
                    extracted.get("course_name", ""),
                    extracted.get("instructor", ""),
                    extracted.get("contact", ""),
                    json.dumps(extracted.get("assessment", {}), ensure_ascii=False),
                    json.dumps(deadlines_raw, ensure_ascii=False),
                    extracted.get("important_notes", ""),
                    json.dumps(deadlines_normalized, ensure_ascii=False),
                    source_ids,
                    now,
                    card_id,
                ),
            )
        else:
            card_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO course_info_cards
                   (card_id, kb_id, course_name, instructor, contact, assessment,
                    deadlines, important_notes, deadlines_normalized, source_doc_ids,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    card_id, kb_id,
                    extracted.get("course_name", ""),
                    extracted.get("instructor", ""),
                    extracted.get("contact", ""),
                    json.dumps(extracted.get("assessment", {}), ensure_ascii=False),
                    json.dumps(deadlines_raw, ensure_ascii=False),
                    extracted.get("important_notes", ""),
                    json.dumps(deadlines_normalized, ensure_ascii=False),
                    source_ids,
                    now, now,
                ),
            )
        await db.commit()
    finally:
        await db.close()

    return await get_card(kb_id)  # type: ignore[return-value]


async def get_card(kb_id: str) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM course_info_cards WHERE kb_id=?", (kb_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        r = dict(row)
        for f in ("assessment", "deadlines", "deadlines_normalized", "source_doc_ids"):
            r[f] = json.loads(r.get(f) or ("[]" if f != "assessment" else "{}"))
        return r
    finally:
        await db.close()


async def upcoming_deadlines(kb_id: str, within_days: int = 7) -> list[dict]:
    """返回 days_left in [0, within_days] 的 deadline，按 days_left 升序。"""
    card = await get_card(kb_id)
    if not card:
        return []
    dls = card.get("deadlines_normalized") or []
    result = [
        d for d in dls
        if isinstance(d.get("days_left"), int) and 0 <= d["days_left"] <= within_days
    ]
    return sorted(result, key=lambda d: d["days_left"])


def parse_natural_date(text: str, today: date | None = None) -> date | None:
    """
    把常见日期表述转为 date 对象。
    支持：ISO "2026-06-10"、中文"6月10日"、"6/10"等。
    失败返回 None。
    """
    if not text:
        return None
    today = today or date.today()

    # ISO
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 中文月日，如 "6月10日"
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        try:
            d = date(year, month, day)
            # 如果已过，推到明年
            if d < today:
                d = date(year + 1, month, day)
            return d
        except ValueError:
            pass

    # 斜线格式 "6/10"
    m = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            d = date(today.year, month, day)
            if d < today:
                d = date(today.year + 1, month, day)
            return d
        except ValueError:
            pass

    return None


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 输出中的 markdown 代码块包裹。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉第一行（```json 或 ```）和最后一行（```）
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner)
    return text.strip()
