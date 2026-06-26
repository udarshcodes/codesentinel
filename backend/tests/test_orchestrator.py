"""
Tests for orchestrator.py — LangGraph state machine routing logic.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator import route_after_validator, route_after_security


class TestRouteAfterValidator:
    def test_all_patches_pass(self):
        state = {
            "validation_results": [
                {"file": "a.py", "status": "passed"},
                {"file": "b.py", "status": "passed"},
            ],
            "retry_count": 0,
        }
        result = route_after_validator(state)
        assert result == "security_verifier"

    def test_some_patches_fail_retries_left(self):
        state = {
            "validation_results": [
                {"file": "a.py", "status": "passed"},
                {"file": "b.py", "status": "failed", "errors": ["syntax error"]},
            ],
            "retry_count": 0,
        }
        result = route_after_validator(state)
        assert result == "code_generator"

    def test_some_patches_fail_max_retries(self):
        state = {
            "validation_results": [
                {"file": "a.py", "status": "failed"},
            ],
            "retry_count": 3,  # MAX_RETRIES is 2, so this exceeds it
        }
        result = route_after_validator(state)
        assert result == "security_verifier"

    def test_empty_validation_results(self):
        state = {
            "validation_results": [],
            "retry_count": 0,
        }
        result = route_after_validator(state)
        assert result == "security_verifier"


class TestRouteAfterSecurity:
    def test_security_verified(self):
        state = {
            "security_verified": True,
            "retry_count": 0,
        }
        result = route_after_security(state)
        assert result == "pr_author"

    def test_security_failed_retries_left(self):
        state = {
            "security_verified": False,
            "retry_count": 0,
        }
        result = route_after_security(state)
        assert result == "code_generator"

    def test_security_failed_max_retries(self):
        state = {
            "security_verified": False,
            "retry_count": 3,
        }
        result = route_after_security(state)
        assert result == "pr_author"
