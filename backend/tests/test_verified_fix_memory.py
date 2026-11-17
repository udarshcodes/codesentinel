import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from tools.fix_memory import verified_fix_records, retrieve_worker_memory


def verified_state():
    return {"validation_results": [{"passed": True, "tests_executed": True}],
            "security_verified": True, "pr_url": "https://github.com/example/project/pull/1",
            "material_files": ["app.py"], "confidence_score": 0.9,
            "investigated_issues": [{"id": 1, "description": "SQL injection"}],
            "patches": [{"patch_id": 1, "file": "app.py", "applied": True,
                         "patch_text": "db.execute(query, parameters)"}]}


def test_records_use_material_patch_instead_of_validation_payload():
    state = verified_state()
    # An unrelated unresolved advisory may make the overall PR a draft while
    # the independently tested source change remains useful verified memory.
    state["investigated_issues"].append({"id": 2, "severity": "critical", "remediation_mode": "manual_review"})
    records = verified_fix_records(state)
    assert records == [{"issue": "SQL injection", "patch": "db.execute(query, parameters)", "confidence": 0.9}]


@pytest.mark.parametrize("change", [
    {"validation_results": [{"passed": True, "tests_executed": False}]},
    {"validation_results": [{"passed": True, "tests_executed": True, "suite_failed": True}]},
    {"security_verified": False}, {"scanners_failed": True}, {"pr_url": ""},
    {"material_files": []}, {"pipeline_error": "failed"},
    {"patches": [{"patch_id": 1, "file": "app.py", "applied": True, "patch_text": " "}]},
])
def test_unverified_or_empty_records_are_excluded(change):
    state = verified_state()
    state.update(change)
    assert verified_fix_records(state) == []


def test_failed_latest_patch_cannot_reuse_old_success():
    state = verified_state()
    state["patches"].append({"patch_id": 1, "file": "app.py", "applied": False, "patch_text": "broken"})
    assert verified_fix_records(state) == []


def test_live_worker_uses_signed_api_memory(monkeypatch):
    from tools import auth
    monkeypatch.setattr(auth, "TASK_ID", "task-memory")
    response = type("Response", (), {"raise_for_status": lambda self: None,
                                     "json": lambda self: {"status": "success", "fixes": []}})()
    post = AsyncMock(return_value=response)
    monkeypatch.setattr(auth, "authenticated_post", post)
    result = asyncio.run(retrieve_worker_memory("https://github.com/example/project", "SQL injection", task_id="task-memory"))
    assert result["status"] == "success"
    post.assert_awaited_once_with("/api/v1/job/task-memory/fix-memory/query", {"query": "SQL injection"}, timeout=120.0)


def test_chroma_rehydrates_verified_history_and_isolates_repositories(tmp_path, monkeypatch):
    from tools import vector_store
    from tools.fix_memory import query_repository_memory
    from api.job_manager import JobManager
    monkeypatch.setattr(vector_store, "CHROMA_PERSIST_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(vector_store, "client", None)
    monkeypatch.setattr(vector_store, "fixes_collection", None)
    repo = "https://github.com/example/project"
    monkeypatch.setattr(JobManager, "get_repository_fix_states",
                        lambda url: [deepcopy(verified_state())] if url == repo else [])
    result = query_repository_memory(repo, "SQL injection")
    assert result["records_available"] == 1
    assert result["fixes"][0]["patch"] == "db.execute(query, parameters)"
    assert query_repository_memory("https://github.com/another/project", "SQL injection")["fixes"] == []
    # Simulate an API restart. Durable snapshots also support rebuilding an
    # entirely new Chroma filesystem after container replacement.
    vector_store.close_vector_store()
    monkeypatch.setattr(vector_store, "CHROMA_PERSIST_PATH", str(tmp_path / "replacement"))
    assert query_repository_memory(repo, "SQL injection")["fixes"]
    vector_store.close_vector_store()


def test_source_chunks_have_real_newlines_and_remove_deleted_files(tmp_path, monkeypatch):
    from tools import vector_store
    monkeypatch.setattr(vector_store, "CHROMA_PERSIST_PATH", str(tmp_path / "vectors"))
    monkeypatch.setattr(vector_store, "client", None)
    monkeypatch.setattr(vector_store, "fixes_collection", None)
    source = tmp_path / "repo"
    source.mkdir()
    component = source / "App.tsx"
    component.write_text("export function App() {\n  return <main>Hello</main>;\n}\n")
    repo = "https://github.com/example/ui"
    assert vector_store.index_codebase(repo, str(source))["documents_indexed"] == 1
    snippets = vector_store.query_codebase(repo, "App main component")
    assert snippets[0]["file"] == "App.tsx"
    assert "\n  return" in snippets[0]["content"]
    component.unlink()
    assert vector_store.index_codebase(repo, str(source))["documents_indexed"] == 0
    assert vector_store.query_codebase(repo, "App main component") == []
    vector_store.close_vector_store()


def test_memory_api_rejects_unsigned_requests(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setenv("WORKER_WEBHOOK_SECRET", "test-only-secret")
    monkeypatch.setenv("WORKER_AUTH_BYPASS", "false")
    response = TestClient(app).post("/api/v1/job/any-task/fix-memory/query", json={"query": "SQL injection"})
    assert response.status_code == 403


def test_memory_api_derives_repository_from_authenticated_job(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from tools import fix_memory
    from api import worker_auth
    validate = AsyncMock(return_value={"repo_url": "https://github.com/owner/trusted"})
    monkeypatch.setattr(worker_auth, "validate_worker_attempt", validate)
    calls = []
    def query(repo, text):
        calls.append((repo, text))
        return {"status": "success", "records_available": 1, "fixes": [{"patch": "verified"}]}
    monkeypatch.setattr(fix_memory, "query_repository_memory", query)
    response = TestClient(app).post("/api/v1/job/task/fix-memory/query",
                                    json={"query": "bug", "repo_url": "https://github.com/attacker/other"})
    assert response.status_code == 200
    assert calls == [("https://github.com/owner/trusted", "bug")]
