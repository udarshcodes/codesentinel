import os
import sqlite3
import pytest
import json
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH


def setup_test_job(task_id: str):
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, created_at, updated_at, worker_attempt_id) VALUES (?, 'repo', 'RUNNING', ?, ?, 'w1')",
        (task_id, now, now)
    )
    conn.commit()
    conn.close()

def test_waiting_for_llm_capacity_to_dispatching_clears_state():
    task_id = "test_llm_exit_dispatching"
    setup_test_job(task_id)
    
    # 1. Manually set up a valid WAITING_FOR_LLM_CAPACITY state
    now = datetime.now(timezone.utc)
    # Put next_retry in the past so it can be claimed
    past_retry = (now - timedelta(minutes=5)).isoformat()
    
    valid_pipeline_state = {
        "llm_waiting_state": True,
        "next_retry": past_retry,
        "last_llm_model": "gpt-4", "last_llm_error": "rate limit"
    }
    
    JobManager.set_worker_waiting_capacity(task_id, worker_attempt_id="w1", next_retry_timestamp=past_retry, pipeline_state=valid_pipeline_state)
    
    # Verify it entered the state correctly
    job = JobManager.get_job(task_id)
    assert job["status"] == "WAITING_FOR_LLM_CAPACITY"
    assert job["pipeline_state"]["llm_waiting_state"] is True
    assert job["next_retry"] == past_retry
    
    # 2. Transition out of it using claim_waiting_job -> DISPATCHING
    worker_attempt_id = JobManager.claim_waiting_job(task_id)
    assert worker_attempt_id is not None
    
    # 3. Verify it was cleared atomically
    job = JobManager.get_job(task_id)
    assert job["status"] == "DISPATCHING"
    assert job["pipeline_state"].get("llm_waiting_state") is False
    assert job["pipeline_state"].get("next_retry") is None
    assert job["next_retry"] is None

def test_waiting_for_llm_capacity_to_running_rejects_staleness():
    task_id = "test_llm_exit_running"
    setup_test_job(task_id)
    
    now = datetime.now(timezone.utc)
    future_retry = (now + timedelta(minutes=5)).isoformat()
    
    # Attempt to transition to RUNNING with stale waiting metadata
    stale_pipeline_state = {
        "llm_waiting_state": True,
        "next_retry": future_retry
    }
    
    # This should be rejected by validate_state_consistency
    with pytest.raises(ValueError, match="RUNNING cannot claim llm_waiting_state=True"):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        JobManager.validate_state_consistency(cursor, task_id, "RUNNING", stale_pipeline_state)
        conn.close()

def test_dispatching_rejects_llm_waiting_state():
    task_id = "test_llm_exit_dispatching_reject"
    setup_test_job(task_id)
    
    stale_pipeline_state = {
        "llm_waiting_state": True
    }
    
    with pytest.raises(ValueError, match="DISPATCHING cannot claim llm_waiting_state=True"):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        JobManager.validate_state_consistency(cursor, task_id, "DISPATCHING", stale_pipeline_state)
        conn.close()

def test_running_rejects_active_next_retry():
    task_id = "test_llm_exit_running_reject"
    setup_test_job(task_id)
    
    now = datetime.now(timezone.utc)
    future_retry = (now + timedelta(minutes=5)).isoformat()
    
    stale_pipeline_state = {
        "llm_waiting_state": False,
        "next_retry": future_retry
    }
    
    with pytest.raises(ValueError, match="RUNNING cannot claim active next_retry"):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        JobManager.validate_state_consistency(cursor, task_id, "RUNNING", stale_pipeline_state)
        conn.close()

def test_transition_job_state_clears_automagically():
    task_id = "test_llm_auto_clear"
    setup_test_job(task_id)
    
    now = datetime.now(timezone.utc)
    past_retry = (now - timedelta(minutes=5)).isoformat()
    
    # Start in WAITING_FOR_DISPATCH so we can transition to something else freely
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'WAITING_FOR_DISPATCH' WHERE task_id = ?", (task_id,))
    JobManager.transition_job_state(cursor, task_id, "DISPATCHING", worker_attempt_id="w1", timestamp=now.isoformat())
    conn.commit()
    conn.close()

    # Now simulate a worker state save with stale LLM data (which should be scrubbed!)
    # Actually worker save goes through save_worker_state -> transition_job_state
    
    stale_state = {
        "llm_waiting_state": True,
        "next_retry": past_retry
    }
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # DISPATCHING -> RUNNING should scrub the llm waiting state
    JobManager.transition_job_state(
        cursor, task_id, "RUNNING", 
        worker_attempt_id="w1", 
        timestamp=now.isoformat(), 
        pipeline_state=stale_state
    )
    conn.commit()
    conn.close()
    
    job = JobManager.get_job(task_id)
    assert job["status"] == "RUNNING"
    assert job["pipeline_state"].get("llm_waiting_state") is False
    assert job["pipeline_state"].get("next_retry") is None
