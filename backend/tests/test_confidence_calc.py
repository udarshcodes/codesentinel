"""
Tests for tools/confidence_calc.py — unified confidence score formula.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.confidence_calc import calculate_pipeline_confidence


class TestConfidenceCalc(unittest.TestCase):
    def test_perfect_score(self):
        state = {
            "validation_results": [{"passed": True}],
            "patches": [{"applied": True}],
            "security_verified": True,
        }
        score = calculate_pipeline_confidence(state, chroma_score=100.0)
        self.assertEqual(score, 100.0)

    def test_partial_score(self):
        state = {
            "validation_results": [
                {"passed": False, "files_passed": 1, "files_validated": 2}
            ],
            "patches": [{"applied": True}, {"applied": False}],
            "security_verified": True,
        }
        # Failed validation earns no test/security points; half the attempted repairs earn 10.
        score = calculate_pipeline_confidence(state, chroma_score=0.0)
        self.assertEqual(score, 10.0)

    def test_absent_and_failed_test_evidence_is_not_inferred_from_syntax_counts(self):
        self.assertEqual(calculate_pipeline_confidence({}), 0)
        failed = {"validation_results": [{"passed": False, "files_passed": 100, "files_validated": 100}]}
        self.assertEqual(calculate_pipeline_confidence(failed), 0)
        syntax_only = {"validation_results": [{"passed": True, "tests_executed": False}]}
        self.assertEqual(calculate_pipeline_confidence(syntax_only), 0)


if __name__ == "__main__":
    unittest.main()
