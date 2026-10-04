import pytest
from api.job_manager import JobManager

def test_state_machine_valid():
    assert JobManager._is_valid_transition("WAITING_FOR_DISPATCH", "DISPATCHING") == True
    assert JobManager._is_valid_transition("RUNNING", "WAITING_FOR_LLM_CAPACITY") == True
    
def test_state_machine_invalid():
    assert JobManager._is_valid_transition("QUEUED", "COMPLETED") == False
    assert JobManager._is_valid_transition("FAILED", "RUNNING") == False
    assert JobManager._is_valid_transition("COMPLETED", "RUNNING") == False
