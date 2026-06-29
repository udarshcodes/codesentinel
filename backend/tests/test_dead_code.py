"""
Tests for dead code and dead file detection in static_analysis.py.
"""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.static_analysis import agent_static_analysis


class TestDeadCodeDetection(unittest.TestCase):
    def test_multi_lang_dead_code(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Go file with unused function
            with open(os.path.join(tmp_dir, "utils.go"), "w") as f:
                f.write("package main\n\nfunc unusedHelper() {}\n")

            # Java file with unused private method
            with open(os.path.join(tmp_dir, "Service.java"), "w") as f:
                f.write(
                    "public class Service {\n    private void deadMethod() {}\n}\n"
                )

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
