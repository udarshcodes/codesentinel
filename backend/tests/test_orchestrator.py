"""
Tests for orchestrator.py — LangGraph state machine routing logic.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator import OrchestratorAgent

route_after_validator = OrchestratorAgent.route_after_validator
route_after_security = OrchestratorAgent.route_after_security


class TestRouteAfterValidator(unittest.TestCase):
    def test_all_patches_pass(self):
        state = {
            "validation_results": [
                {"passed": True, "files_passed": 2, "files_validated": 2},
            ],
            "retry_count": 0,
        }
        result = route_after_validator(state)
        self.assertEqual(result, "security_verifier")

    def test_some_patches_fail_retries_left(self):
        state = {
            "validation_results": [
                {"passed": False, "files_passed": 1, "files_validated": 2},
            ],
            "patches": [
                {"file": "a.py", "applied": True},
            ],
            "retry_count": 1,
        }
        result = route_after_validator(state)
        self.assertEqual(result, "code_generator")

    def test_some_patches_fail_no_applied_patches(self):
        state = {
            "validation_results": [
                {"passed": False, "files_passed": 0, "files_validated": 1},
            ],
            "patches": [],
            "retry_count": 1,
        }
        result = route_after_validator(state)
        self.assertEqual(result, "security_verifier")

    def test_some_patches_fail_max_retries(self):
        state = {
            "validation_results": [
                {"passed": False},
            ],
            "retry_count": 3,
        }
        result = route_after_validator(state)
        self.assertEqual(result, "security_verifier")

    def test_empty_validation_results(self):
        state = {
            "validation_results": [],
            "retry_count": 0,
        }
        result = route_after_validator(state)
        self.assertEqual(result, "security_verifier")


class TestRouteAfterSecurity(unittest.TestCase):
    def test_security_verified(self):
        state = {
            "security_verified": True,
            "retry_count": 0,
        }
        result = route_after_security(state)
        self.assertEqual(result, "pr_author")

    def test_security_failed_retries_left(self):
        state = {
            "security_verified": False,
            "retry_count": 1,
            "security_retry_context": [{"id": "CVE-1"}],
        }
        result = route_after_security(state)
        self.assertEqual(result, "code_generator")

    def test_security_failed_max_retries(self):
        state = {
            "security_verified": False,
            "retry_count": 3,
            "security_retry_context": [{"id": "CVE-1"}],
        }
        result = route_after_security(state)
        self.assertEqual(result, "pr_author")


if __name__ == "__main__":
    unittest.main()
