import pytest
from api.job_manager import JobManager

def test_needs_review_is_terminal():
    assert JobManager._is_valid_transition("NEEDS_REVIEW", "STARTING") is False
    assert JobManager._is_valid_transition("NEEDS_REVIEW", "WAITING_FOR_DISPATCH") is False
    assert JobManager._is_valid_transition("NEEDS_REVIEW", "RUNNING") is False
    assert JobManager._is_valid_transition("NEEDS_REVIEW", "COMPLETED") is False
    assert JobManager._is_valid_transition("NEEDS_REVIEW", "FAILED") is False

def test_wait_for_approval_transitions():
    assert JobManager._is_valid_transition("WAITING_FOR_APPROVAL", "NEEDS_REVIEW") is True
    assert JobManager._is_valid_transition("WAITING_FOR_APPROVAL", "WAITING_FOR_DISPATCH") is True
    assert JobManager._is_valid_transition("WAITING_FOR_APPROVAL", "FAILED") is True
    
    assert JobManager._is_valid_transition("WAITING_FOR_APPROVAL", "STARTING") is False
    assert JobManager._is_valid_transition("WAITING_FOR_APPROVAL", "RUNNING") is False
