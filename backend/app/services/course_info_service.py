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
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import AsyncIterator

from app.db.database import get_db
from app.prompts import load_prompt
from app.services.qa_service import call_llm_json
from app.services.retrieval_service import RetrievedChunk, hybrid_search

logger = logging.getLogger(__name__)

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
    同步收集 stream 事件，最后返回 final card 字典。
    """
    card = None
    async for evt in generate_card_stream(kb_id):
        if evt["type"] == "card":
            card = evt["card"]
    if not card:
        raise ValueError("生成课程卡片失败")
    return card


async def generate_card_stream(kb_id: str) -> AsyncIterator[dict]:
    """
    触发课程信息卡片生成（或重新生成）的流式生成器。
    采用多轮迭代检索 Agent 架构，最大进行 2 轮搜索，查漏补缺并流式向前端汇报各步骤状态。
    """
    # 1. 并行 5 查询
    import asyncio
    yield {
        "type": "progress",
        "round": 1,
        "step": "retrieving",
        "message": "正在启动第一轮检索：并行检索5个课程核心维度...",
        "queries": _QUERIES,
    }
    all_chunks_lists = await asyncio.gather(
        *[hybrid_search(q, kb_id, top_k=5) for q in _QUERIES]
    )

    # 2. 去重合并（以 child_chunk_id 为 key）
    seen: dict[str, RetrievedChunk] = {}
    for chunks in all_chunks_lists:
        for c in chunks:
            if c.child_chunk_id not in seen:
                seen[c.child_chunk_id] = c

    all_chunks = list(seen.values())
    yield {
        "type": "progress",
        "round": 1,
        "step": "merging",
        "message": f"第一轮检索完成，共检索并去重合并了 {len(all_chunks)} 个参考片段。",
        "total_chunks": len(all_chunks),
    }

    if not all_chunks:
        raise ValueError("该知识库暂无可检索内容，请先上传并解析文档")

    # Agent 多轮迭代查漏补缺 (最多进行 2 轮)
    max_rounds = 2
    current_round = 1
    
    while current_round < max_rounds:
        # 构建当前检索到的上下文以供评估
        context_parts = []
        for i, c in enumerate(all_chunks, 1):
            context_parts.append(f"[来源{i}]\n{c.retrieval_text or c.embedding_text}")
        context_text = "\n---\n".join(context_parts)

        yield {
            "type": "progress",
            "round": current_round,
            "step": "evaluating",
            "message": f"Agent 正在执行第 {current_round} 轮信息完整度评估...",
        }

        eval_system_prompt = load_prompt("course_info_eval_system")
        eval_user_content = f"【当前已检索到的参考资料】\n{context_text}\n\n请评估以上资料，判断找齐了核心课程信息吗？返回 JSON。"

        try:
            eval_raw = await call_llm_json([
                {"role": "system", "content": eval_system_prompt},
                {"role": "user", "content": eval_user_content},
            ])
            eval_data = json.loads(_strip_code_fence(eval_raw))
            status = eval_data.get("status", "complete")
            missing_analysis = eval_data.get("missing_info_analysis", "")
            new_queries_spec = eval_data.get("new_queries") or []
            
            logger.info(
                f"[CourseInfoAgent] 第 {current_round} 轮检索评估结果: status={status}, 分析={missing_analysis}"
            )
            
            yield {
                "type": "progress",
                "round": current_round,
                "step": "eval_result",
                "status": status,
                "missing_analysis": missing_analysis,
                "new_queries": new_queries_spec,
                "message": f"第 {current_round} 轮评估结果：{'完整' if status == 'complete' else '尚不完整'}。分析：{missing_analysis}",
            }
            
            if status == "complete" or not new_queries_spec:
                yield {
                    "type": "progress",
                    "round": current_round,
                    "step": "eval_complete",
                    "message": "信息已完整，无需继续补充检索。",
                }
                break
                
            # 如果不完整，且有新的检索意图，跑第二轮检索（加大 top_k=10 以覆盖更多边缘内容）
            yield {
                "type": "progress",
                "round": current_round + 1,
                "step": "planning",
                "message": f"启动查漏补缺检索。新规划了 {len(new_queries_spec)} 个定向检索词：",
                "new_queries": new_queries_spec,
            }

            search_tasks = []
            for spec in new_queries_spec:
                q_text = spec.get("query")
                keywords = spec.get("keywords") or []
                # 拼接关键词和陈述句，交给双路检索
                combined_query = f"{' '.join(keywords)} {q_text}".strip()
                if combined_query:
                    search_tasks.append(hybrid_search(combined_query, kb_id, top_k=10))
            
            if not search_tasks:
                break
                
            yield {
                "type": "progress",
                "round": current_round + 1,
                "step": "retrieving",
                "message": "正在并行执行第二轮深挖检索...",
                "queries": [spec.get("query") for spec in new_queries_spec],
            }
            
            new_chunks_lists = await asyncio.gather(*search_tasks)
            added_count = 0
            for chunks in new_chunks_lists:
                for c in chunks:
                    if c.child_chunk_id not in seen:
                        seen[c.child_chunk_id] = c
                        all_chunks.append(c)
                        added_count += 1
            
            logger.info(f"[CourseInfoAgent] 第 {current_round} 轮查漏补缺检索完成，补充了 {added_count} 个新切片")
            
            yield {
                "type": "progress",
                "round": current_round + 1,
                "step": "merging",
                "message": f"第二轮检索完成。新增 {added_count} 个相关切片，共计 {len(all_chunks)} 个参考切片。",
                "added_count": added_count,
                "total_chunks": len(all_chunks),
            }

            if added_count == 0:
                break
                
        except Exception as e:
            logger.warning(f"[CourseInfoAgent] 评估检索完整性失败，跳过迭代: {e}")
            yield {
                "type": "progress",
                "round": current_round,
                "step": "eval_result",
                "status": "complete",
                "missing_analysis": f"评估异常，跳过迭代：{str(e)}",
                "message": f"完整性评估遇到异常: {str(e)}。跳过后续检索轮次。",
            }
            break
            
        current_round += 1

    # 3. 构建最终 LLM messages 用于结构化提取
    yield {
        "type": "progress",
        "round": "final",
        "step": "extracting",
        "message": "整合全部检索到的参考资料，启动 LLM 课程卡片内容结构化提取...",
    }

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
        logger.warning("课程信息 JSON 解析失败，原始响应前 300 字符: %s", json_text[:300])
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

    card = await get_card(kb_id)
    yield {
        "type": "progress",
        "round": "final",
        "step": "done",
        "message": "课程卡片生成完毕！",
    }
    yield {
        "type": "card",
        "card": card,
    }


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
        # days_left 会随时间过期：按当天从权威的 ISO `date` 字段实时重算，
        # 否则卡片生成日之后 banner / 卡片会一直显示陈旧甚至已过期的天数。
        today = date.today()
        for d in r["deadlines_normalized"]:
            iso = d.get("date") if isinstance(d, dict) else None
            if iso:
                try:
                    d["days_left"] = (date.fromisoformat(iso) - today).days
                except (ValueError, TypeError):
                    pass
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
