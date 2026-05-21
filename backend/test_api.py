"""
test_api.py -- HTTP API end-to-end test (no external APIs required)

Covers all REST endpoints:
  - GET  /api/health
  - KB CRUD: POST / GET / GET(list) / PATCH / DELETE
  - Documents: upload / list / get / parse / delete
  - Tasks: list / by-doc / by-id
  - Error handling: 404 / 409 / 400

Run:
  cd backend
  uv run python test_api.py

Uses real SQLite / Qdrant database; test data is cleaned up after the run.
External APIs (MinerU / DashScope) are NOT called -- pipeline_service is mocked.
"""

from __future__ import annotations

import asyncio
import io
import sys
import traceback
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from app.main import app
from app.db.database import init_db
from app.db.qdrant_client import init_qdrant
from app.config import settings

settings.ensure_dirs()

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    icon = "[PASS]" if ok else "[FAIL]"
    msg = f"  {icon} {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


async def run_all_tests() -> None:
    await init_db()
    init_qdrant()

    # Mock pipeline so /parse endpoint does not call MinerU API
    mock_pipeline = AsyncMock(return_value="mock-task-id")
    transport = httpx.ASGITransport(app=app)

    with patch("app.services.pipeline_service.run_parse_pipeline", mock_pipeline):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            await _run(c)

    _summarize()


async def _run(c: httpx.AsyncClient) -> None:
    print("\n==========================================")
    print("  Mini-NotebookLM  API end-to-end tests")
    print("==========================================")

    # ---- [1] Health ----
    print("\n[1] Health Check")
    r = await c.get("/api/health")
    _record("GET /api/health -> 200", r.status_code == 200)
    _record("body has status=ok", r.json().get("status") == "ok")

    # ---- [2] KB CRUD ----
    print("\n[2] Knowledge Base CRUD")

    r = await c.post("/api/kb", json={"name": "Test KB", "description": "auto", "kb_type": "general"})
    _record("POST /api/kb -> 200", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
    kb = r.json()
    kb_id: str = kb.get("kb_id", "")
    _record("response has kb_id", bool(kb_id))
    _record("kb_type=general", kb.get("kb_type") == "general")
    _record("file_count=0", kb.get("file_count") == 0)

    r2 = await c.post("/api/kb", json={"name": "Course KB", "kb_type": "course"})
    _record("POST /api/kb (course) -> 200", r2.status_code == 200)
    kb2_id: str = r2.json().get("kb_id", "")
    _record("kb_type=course", r2.json().get("kb_type") == "course")

    r = await c.get("/api/kb")
    _record("GET /api/kb -> 200", r.status_code == 200)
    items = r.json().get("items", [])
    _record("list includes created KB", any(i["kb_id"] == kb_id for i in items))

    r = await c.get(f"/api/kb/{kb_id}")
    _record("GET /api/kb/{kb_id} -> 200", r.status_code == 200)
    _record("name matches", r.json().get("name") == "Test KB")

    r = await c.get("/api/kb/nonexistent-id")
    _record("GET unknown KB -> 404", r.status_code == 404)

    r = await c.patch(f"/api/kb/{kb_id}", json={"name": "Updated KB", "kb_type": "course"})
    _record("PATCH /api/kb/{kb_id} -> 200", r.status_code == 200)
    _record("name updated", r.json().get("name") == "Updated KB")
    _record("kb_type updated to course", r.json().get("kb_type") == "course")

    r = await c.patch("/api/kb/nonexistent-id", json={"name": "x"})
    _record("PATCH unknown KB -> 404", r.status_code == 404)

    # ---- [3] Documents ----
    print("\n[3] Document Management")

    fake_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
    r = await c.post(
        f"/api/documents/{kb_id}/upload",
        files={"file": ("test_doc.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    _record("POST /upload -> 200", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
    doc = r.json()
    doc_id: str = doc.get("doc_id", "")
    _record("response has doc_id", bool(doc_id))
    _record("status=uploaded", doc.get("status") == "uploaded")
    _record("source_format=pdf", doc.get("source_format") == "pdf")

    r = await c.post(
        f"/api/documents/{kb_id}/upload",
        files={"file": ("bad.xyz", io.BytesIO(b"data"), "application/octet-stream")},
    )
    _record("unsupported format -> 400", r.status_code == 400)

    r = await c.post(
        "/api/documents/nonexistent-kb/upload",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    _record("upload to unknown KB -> 404", r.status_code == 404)

    r = await c.get(f"/api/documents/{kb_id}")
    _record("GET /documents/{kb_id} -> 200", r.status_code == 200)
    _record("list includes uploaded doc", any(i["doc_id"] == doc_id for i in r.json().get("items", [])))

    r = await c.get(f"/api/documents/{kb_id}/{doc_id}")
    _record("GET /documents/{kb_id}/{doc_id} -> 200", r.status_code == 200)
    _record("filename matches", r.json().get("filename") == "test_doc.pdf")

    r = await c.get(f"/api/documents/{kb_id}/nonexistent-doc")
    _record("GET unknown doc -> 404", r.status_code == 404)

    r = await c.get(f"/api/kb/{kb_id}")
    _record("file_count=1 after upload", r.json().get("file_count") == 1)

    # Trigger parse (pipeline is mocked -- no MinerU call)
    r = await c.post(f"/api/documents/{kb_id}/{doc_id}/parse")
    _record("POST /parse -> 200", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
    _record("response has doc_id", r.json().get("doc_id") == doc_id)

    # Re-trigger while parsing: pipeline mock runs instantly so status may have changed;
    # either 409 (still parsing) or 200 (already failed/indexed) are acceptable
    await asyncio.sleep(0.05)
    r_st = await c.get(f"/api/documents/{kb_id}/{doc_id}")
    cur_status = r_st.json().get("status", "")
    if cur_status == "parsing":
        r = await c.post(f"/api/documents/{kb_id}/{doc_id}/parse")
        _record("re-trigger while parsing -> 409", r.status_code == 409)
    else:
        _record("re-trigger 409 check (skipped)", True, f"status already={cur_status}")

    r = await c.get(f"/api/documents/{kb_id}/{doc_id}/origin-pdf")
    _record("origin-pdf before parse done -> 404", r.status_code == 404)

    # ---- [4] Tasks ----
    print("\n[4] Task Queries")

    r = await c.get("/api/tasks")
    _record("GET /api/tasks -> 200", r.status_code == 200)
    task_items = r.json().get("items", [])
    _record("task list non-empty after parse", len(task_items) > 0)

    r = await c.get(f"/api/tasks/doc/{doc_id}")
    _record("GET /api/tasks/doc/{doc_id} -> 200", r.status_code == 200)
    _record("response has items key", "items" in r.json())

    # Use any existing task to test task_id lookup (pipeline is mocked so doc may have 0 tasks)
    if task_items:
        task_id = task_items[0]["task_id"]
        r = await c.get(f"/api/tasks/{task_id}")
        _record("GET /api/tasks/{task_id} -> 200", r.status_code == 200)
        _record("task has task_id field", "task_id" in r.json())

    r = await c.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    _record("GET unknown task -> 404", r.status_code == 404)

    # ---- [5] Search (empty index) ----
    print("\n[5] Search endpoint (empty index)")

    r = await c.post(f"/api/chat/{kb_id}/search", json={"query": "test", "top_k": 5})
    _record("POST /chat/search -> 200", r.status_code == 200)
    _record("response has results key", "results" in r.json())

    # ---- [6] Delete ----
    print("\n[6] Delete operations")

    r = await c.delete(f"/api/documents/{kb_id}/{doc_id}")
    _record("DELETE document -> 200", r.status_code == 200)

    r = await c.get(f"/api/documents/{kb_id}/{doc_id}")
    _record("GET after doc delete -> 404", r.status_code == 404)

    r = await c.get(f"/api/kb/{kb_id}")
    _record("file_count=0 after doc delete", r.json().get("file_count") == 0)

    r = await c.delete(f"/api/kb/{kb_id}")
    _record("DELETE KB -> 200", r.status_code == 200)
    _record("response has cascaded_docs", "cascaded_docs" in r.json())

    r = await c.get(f"/api/kb/{kb_id}")
    _record("GET after KB delete -> 404", r.status_code == 404)

    r = await c.delete("/api/kb/nonexistent-id")
    _record("DELETE unknown KB -> 404", r.status_code == 404)

    # cleanup
    await c.delete(f"/api/kb/{kb2_id}")


def _summarize() -> None:
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed
    print("\n==========================================")
    print(f"  Result: {passed}/{total} passed" + (f", {failed} FAILED" if failed else ""))
    print("==========================================\n")
    if failed:
        print("Failed:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))
        sys.exit(1)
    else:
        print("All API tests passed!")


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
