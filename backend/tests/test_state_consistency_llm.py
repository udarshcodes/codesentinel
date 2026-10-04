import pytest
import sqlite3
from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager

def test_validate_state_consistency_llm_waiting_valid():
    now = datetime.now(timezone.utc)
    next_retry = (now + timedelta(minutes=5)).isoformat()
    
    pipeline_state = {
        "llm_waiting_state": True,
        "next_retry": next_retry,
        "last_llm_model": "gpt-4", "last_llm_error": "rate limited"
    }
    
    # Should not raise
    JobManager.validate_state_consistency(None, "task1", "WAITING_FOR_LLM_CAPACITY", pipeline_state)

def test_validate_state_consistency_llm_waiting_missing_flag():
    now = datetime.now(timezone.utc)
    next_retry = (now + timedelta(minutes=5)).isoformat()
    
    pipeline_state = {
        "next_retry": next_retry
    }
    
    with pytest.raises(ValueError, match="requires llm_waiting_state=True"):
        JobManager.validate_state_consistency(None, "task1", "WAITING_FOR_LLM_CAPACITY", pipeline_state)

def test_validate_state_consistency_llm_waiting_missing_next_retry():
    pipeline_state = {
        "llm_waiting_state": True
    }
    
    with pytest.raises(ValueError, match="requires next_retry"):
        JobManager.validate_state_consistency(None, "task1", "WAITING_FOR_LLM_CAPACITY", pipeline_state)

def test_validate_state_consistency_llm_waiting_malformed_next_retry():
    pipeline_state = {
        "llm_waiting_state": True,
        "next_retry": "not-a-date"
    }
    
    with pytest.raises(ValueError, match="next_retry is malformed or invalid absolute UTC timestamp"):
        JobManager.validate_state_consistency(None, "task1", "WAITING_FOR_LLM_CAPACITY", pipeline_state)

