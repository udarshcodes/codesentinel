import pytest
import sqlite3
import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

import os
os.environ["WORKER_AUTH_BYPASS"] = "true"

from main import app
from api.job_manager import JobManager, DB_PATH, init_db

client = TestClient(app)

from tools import auth
# Mock auth tools to use TestClient
def _sign_request(method, path, body_bytes=b""):
    import hmac
    import hashlib
    from datetime import datetime, timezone
    
    # task_id is usually in the path, e.g. /api/v1/job/{task_id}/...
    task_id = path.split("/job/")[1].split("/")[0] if "/job/" in path else ""
    timestamp = str(datetime.now(timezone.utc).timestamp())
    secret = os.getenv("WORKER_WEBHOOK_SECRET", "dummy_secret")
    if "WORKER_WEBHOOK_SECRET" not in os.environ:
        os.environ["WORKER_WEBHOOK_SECRET"] = secret

    msg = f"{method}:{path}:{task_id}:{timestamp}:mock_attempt::test_repo:".encode() + body_bytes
    sig = "sha256=" + hmac.HMAC(secret.encode(), msg, hashlib.sha256).hexdigest()
    return sig, timestamp

async def mock_post(path, json_payload):
    body_bytes = json.dumps(json_payload).encode() if json_payload else b""
    sig, ts = _sign_request("POST", path, body_bytes)
    res = client.post(path, content=body_bytes, headers={
        "X-Worker-Attempt-Id": "mock_attempt", 
        "X-Repo-Url": "test_repo",
        "X-Worker-Signature": sig,
        "X-Timestamp": ts,
        "Content-Type": "application/json"
    })
    if res.status_code >= 400: print("POST ERROR:", res.text)
    class MockRes:
        def __init__(self, r): self.status_code = r.status_code; self.text = r.text; self._r = r
        def json(self): return self._r.json()
    return MockRes(res)

async def mock_get(path):
    sig, ts = _sign_request("GET", path)
    res = client.get(path, headers={
        "X-Worker-Attempt-Id": "mock_attempt", 
        "X-Repo-Url": "test_repo",
        "X-Worker-Signature": sig,
        "X-Timestamp": ts
    })
    if res.status_code >= 400: print("GET ERROR:", res.text)
    class MockRes:
        def __init__(self, r): self.status_code = r.status_code; self.text = r.text; self._r = r
        def json(self): return self._r.json()
    return MockRes(res)

auth.authenticated_post = mock_post
auth.authenticated_get = mock_get

def _create_job_state(task_id, repair_plan, approval_payload, cycle_id):
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    p_state = {
        "awaiting_approval": True,
        "approval_state": "pending",
        "approval_payload": approval_payload,
        "repair_plan": repair_plan,
        "approval_cycle_id": cycle_id,
        "completed_nodes": ["repair_planner"],
        "last_completed_node": "repair_planner",
        "current_stage": "WAITING_FOR_APPROVAL"
    }
    
    import hashlib
    view_token = "view123"
    hashed_view = hashlib.sha256(view_token.encode()).hexdigest()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, updated_at, pipeline_state, view_token, worker_attempt_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, "test_repo", "WAITING_FOR_APPROVAL", datetime.now(timezone.utc).isoformat(), json.dumps(p_state), hashed_view, "mock_attempt")
    )
    conn.commit()
    conn.close()

def setup_worker_env(task_id):
    os.environ["TASK_ID"] = task_id
    os.environ["REPO_URL"] = "test_repo"
    os.environ["BACKEND_URL"] = "http://testserver"
    os.environ["WORKER_ATTEMPT_ID"] = "mock_attempt"
    os.environ["WORKER_AUTH_BYPASS"] = "true"
    import worker
    import importlib
    importlib.reload(worker)
    worker.TASK_ID = task_id
    worker.REPO_URL = "test_repo"
    worker.BACKEND_URL = "http://testserver"
    return worker
    
def test_two_fix_code_generator_persistence():
    task_id = "test-cgen-persistence-" + str(uuid.uuid4())
    cycle_id = "cycle1"
    
    repair_plan = [
        {"fix_id": "A", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"}
    ]
    
    _create_job_state(task_id, repair_plan, {"fix_id": "A"}, cycle_id)
    
    res_a = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_a = res_a.json()["approval_token"]
    
    res_app_a = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_a, "decision": "approved", "fix_id": "A", "approval_cycle_id": cycle_id})
    assert res_app_a.status_code == 200
    
    # Simulate dispatcher checking out the job
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'DISPATCHING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    class MockGraph:
        def astream(self, *args, **kwargs):
            class AsyncIter:
                def __init__(self):
                    self.yielded = False
                def __aiter__(self): return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        return {"code_generator": {"patches": ["PATCH_FOR_A"], "generated_code": "CODE_FOR_A"}}
                    raise StopAsyncIteration
            return AsyncIter()
            
    worker = setup_worker_env(task_id)
    worker.langgraph_app = MockGraph()
    
    async def run():
        # Cancel event to break heartbeat
        cancel_event = asyncio.Event()
        main_task = asyncio.current_task()
        asyncio.create_task(worker.heartbeat_loop(cancel_event, main_task))
        await worker.run_worker()
        cancel_event.set()
        
    asyncio.run(run())
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    
    assert row is not None
    status, state_str = row
    assert status == "WAITING_FOR_APPROVAL"
    
    state = json.loads(state_str)
    
    assert "PATCH_FOR_A" in state.get("patches", [])
    assert state.get("generated_code") == "CODE_FOR_A"
    
    assert state["approval_payload"]["fix_id"] == "B"
    assert state["repair_plan"][0]["status"] == "approved"
    assert state["repair_plan"][1]["status"] == "pending"
    assert state["last_completed_node"] == "code_generator"
    assert state["approval_cycle_id"] != cycle_id
    
    cycle_b = state["approval_cycle_id"]
    res_b = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    assert res_b.status_code == 200
    tok_b = res_b.json()["approval_token"]
    
    res_app_b = client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_b, "decision": "approved", "fix_id": "B", "approval_cycle_id": cycle_b})
    assert res_app_b.status_code == 200

def test_three_fix_code_generator_persistence():
    task_id = "test-cgen-persistence3-" + str(uuid.uuid4())
    cycle_id = "cycle1"
    
    repair_plan = [
        {"fix_id": "A", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "B", "status": "pending", "risk_level": "high-risk"},
        {"fix_id": "C", "status": "pending", "risk_level": "high-risk"}
    ]
    
    _create_job_state(task_id, repair_plan, {"fix_id": "A"}, cycle_id)
    
    class MockGraphGen:
        def __init__(self, patch_val):
            self.patch_val = patch_val
        def astream(self, *args, **kwargs):
            class AsyncIter:
                def __init__(self, p):
                    self.yielded = False
                    self.p = p
                def __aiter__(self): return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        return {"code_generator": {"patches": [self.p]}}
                    raise StopAsyncIteration
            return AsyncIter(self.patch_val)
            
    res_a = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_a = res_a.json()["approval_token"]
    client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_a, "decision": "approved", "fix_id": "A", "approval_cycle_id": cycle_id})
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'DISPATCHING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    worker = setup_worker_env(task_id)
    worker.langgraph_app = MockGraphGen("PATCH_A")
    
    async def run():
        cancel_event = asyncio.Event()
        main_task = asyncio.current_task()
        asyncio.create_task(worker.heartbeat_loop(cancel_event, main_task))
        await worker.run_worker()
        cancel_event.set()
        
    asyncio.run(run())
    
    conn = sqlite3.connect(DB_PATH)
    state_str = conn.execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()[0]
    state = json.loads(state_str)
    assert "PATCH_A" in state.get("patches", [])
    cycle_b = state["approval_cycle_id"]
    conn.close()
    
    res_b = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_b = res_b.json()["approval_token"]
    client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_b, "decision": "approved", "fix_id": "B", "approval_cycle_id": cycle_b})
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'DISPATCHING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    worker.langgraph_app = MockGraphGen("PATCH_B")
    asyncio.run(run())
    
    conn = sqlite3.connect(DB_PATH)
    state_str = conn.execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()[0]
    state = json.loads(state_str)
    assert "PATCH_B" in state.get("patches", [])
    cycle_c = state["approval_cycle_id"]
    conn.close()
    
    res_c = client.post(f"/api/v1/job/{task_id}/issue-approval-token", headers={"Authorization": "Bearer view123"})
    tok_c = res_c.json()["approval_token"]
    client.post(f"/api/v1/approve/{task_id}", json={"approval_token": tok_c, "decision": "approved", "fix_id": "C", "approval_cycle_id": cycle_c})
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = 'DISPATCHING' WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    class MockGraphGenFinal:
        def astream(self, *args, **kwargs):
            class AsyncIter:
                def __init__(self): self.yielded = False
                def __aiter__(self): return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        return {"code_generator": {"patches": ["PATCH_C"]}}
                    raise StopAsyncIteration
            return AsyncIter()
            
    worker.langgraph_app = MockGraphGenFinal()
    asyncio.run(run())
    
    conn = sqlite3.connect(DB_PATH)
    status, state_str = conn.execute("SELECT status, pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    
    state = json.loads(state_str)
    assert "PATCH_A" in state.get("patches", [])
    assert "PATCH_B" in state.get("patches", [])
    assert "PATCH_C" in state.get("patches", [])
    assert not state.get("awaiting_approval")
    assert state.get("approval_payload") is None
    assert status != "WAITING_FOR_APPROVAL"
    assert cycle_id != cycle_b and cycle_b != cycle_c
