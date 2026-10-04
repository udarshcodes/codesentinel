import pytest
import sqlite3
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.job_manager import JobManager, DB_PATH

def test_malformed_next_retry():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    
    # Insert a job with a malformed next_retry
    cursor.execute("""
        INSERT INTO jobs (task_id, repo_url, status, next_retry)
        VALUES ('malformed_task', 'http://repo', 'WAITING_FOR_LLM_CAPACITY', 'not-a-timestamp')
    """)
    conn.commit()
    conn.close()
    
    # This should not raise an exception
    ready = JobManager.get_waiting_jobs_ready()
    
    # Verify it was marked NEEDS_REVIEW
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM jobs WHERE task_id = 'malformed_task'")
    status = cursor.fetchone()[0]
    
    # Clean up
    cursor.execute("DELETE FROM jobs WHERE task_id = 'malformed_task'")
    conn.commit()
    conn.close()
    
    assert status == 'NEEDS_REVIEW'
