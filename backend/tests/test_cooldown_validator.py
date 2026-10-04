from datetime import datetime, timezone, timedelta
from api.job_manager import JobManager

def test_cooldown_validator_future():
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=5)).isoformat()
    can_claim, is_malformed = JobManager._check_llm_cooldown(future)
    assert can_claim is False
    assert is_malformed is False

def test_cooldown_validator_past():
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=5)).isoformat()
    can_claim, is_malformed = JobManager._check_llm_cooldown(past)
    assert can_claim is True
    assert is_malformed is False

def test_cooldown_validator_missing():
    can_claim, is_malformed = JobManager._check_llm_cooldown(None)
    assert can_claim is False
    assert is_malformed is True
    
    can_claim, is_malformed = JobManager._check_llm_cooldown("")
    assert can_claim is False
    assert is_malformed is True

def test_cooldown_validator_malformed():
    can_claim, is_malformed = JobManager._check_llm_cooldown("not-a-date")
    assert can_claim is False
    assert is_malformed is True
