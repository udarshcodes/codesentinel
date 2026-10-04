import pytest
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager, DB_PATH, init_db

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield

def test_claim_waiting_job_llm_cooldown_future():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cooldown-future-" + str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    future_retry = (now + timedelta(minutes=5)).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, next_retry) VALUES (?, 'repo', 'WAITING_FOR_LLM_CAPACITY', ?)",
        (task_id, future_retry)
    )
    conn.commit()
    conn.close()
    
    # Attempt to claim
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is None
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "WAITING_FOR_LLM_CAPACITY"
    conn.close()

def test_claim_waiting_job_llm_cooldown_past():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cooldown-past-" + str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    past_retry = (now - timedelta(minutes=5)).isoformat()
    
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, next_retry) VALUES (?, 'repo', 'WAITING_FOR_LLM_CAPACITY', ?)",
        (task_id, past_retry)
    )
    conn.commit()
    conn.close()
    
    # Attempt to claim
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is not None
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "DISPATCHING"
    conn.close()

def test_claim_waiting_job_llm_cooldown_malformed():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cooldown-malformed-" + str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, next_retry) VALUES (?, 'repo', 'WAITING_FOR_LLM_CAPACITY', 'not-a-timestamp')",
        (task_id,)
    )
    conn.commit()
    conn.close()
    
    # Attempt to claim
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is None
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "NEEDS_REVIEW"
    conn.close()

def test_claim_waiting_job_llm_cooldown_missing():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cooldown-missing-" + str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status) VALUES (?, 'repo', 'WAITING_FOR_LLM_CAPACITY')",
        (task_id,)
    )
    conn.commit()
    conn.close()
    
    # Attempt to claim
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is None
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "NEEDS_REVIEW"
    conn.close()

def test_claim_waiting_job_llm_cooldown_empty():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    task_id = "test-cooldown-empty-" + str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO jobs (task_id, repo_url, status, next_retry) VALUES (?, 'repo', 'WAITING_FOR_LLM_CAPACITY', '')",
        (task_id,)
    )
    conn.commit()
    conn.close()
    
    # Attempt to claim
    attempt_id = JobManager.claim_waiting_job(task_id)
    assert attempt_id is None
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    assert row[0] == "NEEDS_REVIEW"
    conn.close()
