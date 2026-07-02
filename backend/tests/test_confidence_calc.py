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
        # tests: 0.5 * 40 = 20
        # static: 1.0 * 30 = 30
        # patches: 0.5 * 20 = 10
        # chroma: 0.0 * 10 = 0
        # total = 60.0
        score = calculate_pipeline_confidence(state, chroma_score=0.0)
        self.assertEqual(score, 60.0)


if __name__ == "__main__":
    unittest.main()
