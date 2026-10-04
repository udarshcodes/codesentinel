import pytest
import sqlite3
import json
from datetime import datetime, timezone, timedelta

from api.job_manager import JobManager, DB_PATH

@pytest.fixture
def clean_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    cursor.execute("DELETE FROM job_events")
    cursor.execute("DELETE FROM approval_credentials")
    conn.commit()
    conn.close()
    yield

def test_running_to_dispatching_invalid():
    """Verify that RUNNING -> DISPATCHING is no longer a globally valid transition."""
    assert not JobManager._is_valid_transition("RUNNING", "DISPATCHING")

def test_recover_stale_worker_claim_success(clean_db):
    """Verify that a stale RUNNING job can be recovered via the explicit recover operation."""
    task_id = "test_recover_success"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "RUNNING", old_hb)
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is not None
    assert new_worker != w1
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "DISPATCHING"
    assert job["worker_attempt_id"] == new_worker

def test_recover_stale_worker_claim_negative_fresh_running(clean_db):
    """Verify that a fresh RUNNING worker cannot be recovered."""
    task_id = "test_recover_fresh_run"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fresh_hb = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "RUNNING", fresh_hb)
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "RUNNING"
    assert job["worker_attempt_id"] == w1

def test_recover_stale_worker_claim_negative_fresh_dispatching(clean_db):
    """Verify that a fresh DISPATCHING worker cannot be recovered."""
    task_id = "test_recover_fresh_disp"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fresh_disp = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, dispatch_attempted_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "DISPATCHING", fresh_disp)
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None

def test_recover_stale_worker_claim_negative_terminal(clean_db):
    """Verify that a terminal worker cannot be recovered."""
    task_id = "test_recover_terminal"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, "worker1", "FAILED", (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None

def test_recover_stale_worker_claim_negative_waiting_for_approval(clean_db):
    """Verify that WAITING_FOR_APPROVAL cannot be recovered via stale claim."""
    task_id = "test_recover_wfa"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, "worker1", "WAITING_FOR_APPROVAL", (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None

def test_recover_stale_worker_claim_negative_waiting_for_llm(clean_db):
    """Verify that WAITING_FOR_LLM_CAPACITY cannot be recovered via stale claim."""
    task_id = "test_recover_wfllm"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, "worker1", "WAITING_FOR_LLM_CAPACITY", (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None

def test_scheduler_failing_malformed_state(clean_db):
    """Verify that get_waiting_jobs_ready safely fails jobs with malformed state to NEEDS_REVIEW."""
    task_id_disp = "test_malformed_disp"
    task_id_llm = "test_malformed_llm"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (task_id, status, next_retry) VALUES (?, ?, ?)",
        (task_id_disp, "WAITING_FOR_DISPATCH", "invalid-date")
    )
    cursor.execute(
        "INSERT INTO jobs (task_id, status, next_retry) VALUES (?, ?, ?)",
        (task_id_llm, "WAITING_FOR_LLM_CAPACITY", "invalid-date")
    )
    conn.commit()
    conn.close()
    
    ready_jobs = JobManager.get_waiting_jobs_ready()
    # The malformed jobs should NOT be returned as ready.
    assert not any(j["task_id"] in (task_id_disp, task_id_llm) for j in ready_jobs)
    
    # Check that they were transitioned to NEEDS_REVIEW
    job1 = JobManager.get_job(task_id_disp)
    assert job1["status"] == "NEEDS_REVIEW"
    
    job2 = JobManager.get_job(task_id_llm)
    assert job2["status"] == "NEEDS_REVIEW"
    
    # Check that events were generated
    events1 = JobManager.get_events(task_id_disp)
    assert len(events1) > 0
    assert events1[-1]["event"] == "scheduler_state_invalid"
    
    events2 = JobManager.get_events(task_id_llm)
    assert len(events2) > 0
    assert events2[-1]["event"] == "scheduler_state_invalid"


def test_recover_stale_worker_claim_state_normalization(clean_db):
    """Verify that a stale RUNNING job's LLM waiting metadata is cleared upon recovery."""
    task_id = "test_recover_state_norm"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    old_next_retry = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    
    pipeline_state = {
        "llm_waiting_state": True,
        "next_retry": old_next_retry,
        "last_llm_error": "rate limit"
    }
    
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at, pipeline_state) VALUES (?, ?, ?, ?, ?)",
        (task_id, w1, "RUNNING", old_hb, json.dumps(pipeline_state))
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is not None
    assert new_worker != w1
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "DISPATCHING"
    assert job["worker_attempt_id"] == new_worker
    
    updated_state = job["pipeline_state"]
    assert updated_state.get("llm_waiting_state") is False
    assert updated_state.get("next_retry") is None
    assert updated_state.get("last_llm_error") == "rate limit" # preserved

def test_recover_stale_worker_claim_approval_safety(clean_db):
    """Verify that WAITING_FOR_APPROVAL cannot be stale-recovered."""
    task_id = "test_recover_approval_safety"
    w1 = "worker1"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "WAITING_FOR_APPROVAL", old_hb)
    )
    conn.commit()
    conn.close()
    
    new_worker = JobManager.recover_stale_worker_claim(task_id)
    assert new_worker is None
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_APPROVAL"
    assert job["worker_attempt_id"] == w1

def test_recover_stale_worker_claim_concurrent(clean_db, monkeypatch):
    """Verify safe concurrent recovery of the same stale job."""
    task_id = "test_recover_concurrent"
    w1 = "worker1"


    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, worker_attempt_id, status, worker_heartbeat_at) VALUES (?, ?, ?, ?)",
        (task_id, w1, "RUNNING", old_hb)
    )
    conn.commit()
    conn.close()
    
    original_connect = sqlite3.connect
    
    call_count = 0
    class MockConnection:
        def __init__(self, real_conn):
            self.real_conn = real_conn
        def cursor(self):
            return MockCursor(self.real_conn.cursor())
        def commit(self):
            self.real_conn.commit()
        def rollback(self):
            self.real_conn.rollback()
        def close(self):
            self.real_conn.close()
        def execute(self, *args, **kwargs):
            return self.real_conn.execute(*args, **kwargs)
            
    class MockCursor:
        def __init__(self, real_cursor):
            self.real_cursor = real_cursor
        def fetchone(self):
            return self.real_cursor.fetchone()
        def fetchall(self):
            return self.real_cursor.fetchall()
        def execute(self, query, *args, **kwargs):
            nonlocal call_count
            if "UPDATE jobs SET status = ?" in query:
                call_count += 1
                if call_count == 1:
                    # Simulate a concurrent update by another process
                    self.real_cursor.execute("UPDATE jobs SET worker_attempt_id = 'different' WHERE task_id = ?", (task_id,))
            return self.real_cursor.execute(query, *args, **kwargs)
        @property
        def rowcount(self):
            return self.real_cursor.rowcount
            
    def mock_connect(*args, **kwargs):
        return MockConnection(original_connect(*args, **kwargs))
        
    with monkeypatch.context() as m:
        m.setattr("api.job_manager.sqlite3.connect", mock_connect)
        new_worker = JobManager.recover_stale_worker_claim(task_id)
    
    # The first caller's update should fail because the rowcount is 0 (worker_attempt_id changed)
    assert new_worker is None
    
    # Ensure no events were produced by the failed recovery
    events = JobManager.get_events(task_id)
    revokes = [e for e in events if e["event"] == "worker_revoked"]
    assert len(revokes) == 0
