import pytest
import sqlite3
import json
from api.job_manager import JobManager, DB_PATH

@pytest.mark.asyncio
async def test_llm_recovery_flow():
    task_id = "test_llm_rec_123"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    cursor.execute("INSERT INTO jobs (task_id, status, worker_attempt_id) VALUES (?, ?, ?)", (task_id, "RUNNING", "worker1"))
    conn.commit()
    conn.close()

    # Call set_worker_waiting_capacity
    JobManager.set_worker_waiting_capacity(task_id, "worker1", "2099-01-01T00:00:00Z", {"last_llm_model": "gpt", "last_llm_error": "rate limited"})
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, next_retry, pipeline_state FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "WAITING_FOR_LLM_CAPACITY"
    assert row[1] == "2099-01-01T00:00:00Z"
    assert "last_llm_model" in json.loads(row[2])

@pytest.mark.asyncio
async def test_scheduler_recovers_waiting_task():
    task_id = "test_scheduler_rec_123"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE task_id = ?", (task_id,))
    
    # next_retry is in the past!
    past_time = "2020-01-01T00:00:00Z"
    dummy_state = json.dumps({
        "llm_waiting_state": True,
        "next_retry": past_time,
        "last_llm_model": "gpt-4"
    })
    cursor.execute("INSERT INTO jobs (task_id, status, next_retry, pipeline_state) VALUES (?, ?, ?, ?)", 
                   (task_id, "WAITING_FOR_LLM_CAPACITY", past_time, dummy_state))
    conn.commit()
    conn.close()
    
    ready = JobManager.get_waiting_jobs_ready()
    assert any(j["task_id"] == task_id for j in ready)
    
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is not None
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, pipeline_state, next_retry FROM jobs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == "DISPATCHING"
    assert row[2] is None  # next_retry column is scrubbed
    
    p_state = json.loads(row[1])
    assert p_state.get("llm_waiting_state") is False
    assert p_state.get("next_retry") is None
