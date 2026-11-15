"""
Tests for dead code and dead file detection in static_analysis.py.
"""

import asyncio
import os
import sys
import tempfile
import unittest.mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.static_analysis import agent_static_analysis


class TestDeadCodeDetection(unittest.TestCase):
    @unittest.mock.patch("agents.static_analysis.run_sandboxed_subprocess")
    def test_runtime_classes_are_not_reported_as_dead_css(self, mock_run):
        mock_run.return_value = {"status": "SUCCESS", "stdout": "{}", "stderr": ""}
        with tempfile.TemporaryDirectory() as repo:
            from pathlib import Path
            Path(repo, "app.js").write_text('element.classList.add("active")')
            Path(repo, "style.css").write_text('.active { opacity: 1; }')
            result = asyncio.run(agent_static_analysis({"repo_local_path": repo}))
            self.assertFalse(any("CSS class" in finding.get("issue", "")
                                 for finding in result.get("static_findings", [])))

    @unittest.mock.patch("agents.static_analysis.run_sandboxed_subprocess")
    def test_multi_lang_dead_code(self, mock_run):
        # Setup mock run to return empty JSON depending on the tool
        mock_run.return_value = unittest.mock.MagicMock(stdout="{}")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Go file with unused function
            with open(os.path.join(tmp_dir, "utils.go"), "w") as f:
                f.write("package main\n\nfunc unusedHelper() {}\n")

            # Java file with unused private method
            with open(os.path.join(tmp_dir, "Service.java"), "w") as f:
                f.write("public class Service {\n    private void deadMethod() {}\n}\n")

            # Rust file with unused function
            with open(os.path.join(tmp_dir, "lib.rs"), "w") as f:
                f.write("fn dead_fn() {}\n")

            # HTML & CSS with unused class
            with open(os.path.join(tmp_dir, "index.html"), "w") as f:
                f.write('<div class="active"></div>')
            with open(os.path.join(tmp_dir, "style.css"), "w") as f:
                f.write(".active { color: red; }\n.unused_class { color: blue; }\n")

            state = {"repo_local_path": tmp_dir}
            result = asyncio.run(agent_static_analysis(state))
            findings = result.get("static_findings", [])
            issues = [f.get("issue", "") for f in findings]
            issues_str = " ".join(issues)

            self.assertIn("unusedHelper", issues_str)
            self.assertIn("deadMethod", issues_str)
            self.assertIn("dead_fn", issues_str)
            self.assertIn(".unused_class", issues_str)


if __name__ == "__main__":
    unittest.main()
