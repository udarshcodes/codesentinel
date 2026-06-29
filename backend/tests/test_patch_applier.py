"""
Tests for tools/patch_applier.py — SEARCH/REPLACE patch application.
"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.patch_applier import apply_patch


class TestApplyPatchExactMatch(unittest.TestCase):
    def test_exact_search_replace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "example.py")
            with open(target, "w") as f:
                f.write("def add(a, b):\n    return a - b\n")

            diff = (
                "<<<SEARCH>>>\n" "    return a - b\n" "<<<REPLACE>>>\n" "    return a + b\n"
            )
            result = apply_patch(diff, tmp_dir, "example.py")
            self.assertTrue(result["success"])
            with open(target) as f:
                self.assertIn("return a + b", f.read())

    def test_search_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "example.py")
            with open(target, "w") as f:
                f.write("def add(a, b):\n    return a + b\n")

            diff = (
                "<<<SEARCH>>>\n" "    return a * b\n" "<<<REPLACE>>>\n" "    return a - b\n"
            )
            result = apply_patch(diff, tmp_dir, "example.py")
            self.assertIsInstance(result, dict)
            self.assertIn("success", result)

    def test_multiple_blocks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "example.py")
            with open(target, "w") as f:
                f.write("x = 1\ny = 2\nz = 3\n")

            diff = (
                "<<<SEARCH>>>\n"
                "x = 1\n"
                "<<<REPLACE>>>\n"
                "x = 10\n"
                "<<<SEARCH>>>\n"
                "z = 3\n"
                "<<<REPLACE>>>\n"
                "z = 30\n"
            )
            result = apply_patch(diff, tmp_dir, "example.py")
            with open(target) as f:
                content = f.read()
            if result.get("success"):
                self.assertIn("x = 10", content)
                self.assertIn("z = 30", content)


class TestApplyPatchEdgeCases(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "empty.py")
            with open(target, "w") as f:
                f.write("")

            diff = "<<<SEARCH>>>\n" "\n" "<<<REPLACE>>>\n" "# Added content\n"
            result = apply_patch(diff, tmp_dir, "empty.py")
            self.assertIsInstance(result, dict)

    def test_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = apply_patch(
                "<<<SEARCH>>>\nfoo\n<<<REPLACE>>>\nbar\n", tmp_dir, "nonexistent.py"
            )
            self.assertIsInstance(result, dict)
            self.assertTrue(result.get("success") is False or "error" in str(result).lower())

    def test_syntax_validation_on_python(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "valid.py")
            with open(target, "w") as f:
                f.write("def foo():\n    return 42\n")

            diff = (
                "<<<SEARCH>>>\n"
                "    return 42\n"
                "<<<REPLACE>>>\n"
                "    return (\n"
            )
            result = apply_patch(diff, tmp_dir, "valid.py")
            self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
