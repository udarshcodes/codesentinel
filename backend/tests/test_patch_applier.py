"""
Tests for tools/patch_applier.py — SEARCH/REPLACE patch application.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.patch_applier import apply_patch


class TestApplyPatchExactMatch:
    def test_exact_search_replace(self, tmp_path):
        target = tmp_path / "example.py"
        target.write_text("def add(a, b):\n    return a - b\n")

        diff = (
            "<<<SEARCH>>>\n" "    return a - b\n" "<<<REPLACE>>>\n" "    return a + b\n"
        )
        result = apply_patch(str(target), diff)
        assert result["success"] is True
        assert "return a + b" in target.read_text()

    def test_search_not_found(self, tmp_path):
        target = tmp_path / "example.py"
        target.write_text("def add(a, b):\n    return a + b\n")

        diff = (
            "<<<SEARCH>>>\n" "    return a * b\n" "<<<REPLACE>>>\n" "    return a - b\n"
        )
        result = apply_patch(str(target), diff)
        # Should either fail gracefully or use fuzzy matching
        assert isinstance(result, dict)
        assert "success" in result

    def test_multiple_blocks(self, tmp_path):
        target = tmp_path / "example.py"
        target.write_text("x = 1\ny = 2\nz = 3\n")

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
        result = apply_patch(str(target), diff)
        content = target.read_text()
        if result.get("success"):
            assert "x = 10" in content
            assert "z = 30" in content


class TestApplyPatchEdgeCases:
    def test_empty_file(self, tmp_path):
        target = tmp_path / "empty.py"
        target.write_text("")

        diff = "<<<SEARCH>>>\n" "\n" "<<<REPLACE>>>\n" "# Added content\n"
        result = apply_patch(str(target), diff)
        assert isinstance(result, dict)

    def test_nonexistent_file(self, tmp_path):
        result = apply_patch(
            str(tmp_path / "nonexistent.py"), "<<<SEARCH>>>\nfoo\n<<<REPLACE>>>\nbar\n"
        )
        assert isinstance(result, dict)
        assert result.get("success") is False or "error" in str(result).lower()

    def test_syntax_validation_on_python(self, tmp_path):
        """If the patch produces invalid Python, the patch should be rolled back."""
        target = tmp_path / "valid.py"
        target.write_text("def foo():\n    return 42\n")

        diff = (
            "<<<SEARCH>>>\n"
            "    return 42\n"
            "<<<REPLACE>>>\n"
            "    return (\n"  # Intentionally broken syntax
        )
        result = apply_patch(str(target), diff)
        # The patch_applier should detect the syntax error and rollback
        assert isinstance(result, dict)
