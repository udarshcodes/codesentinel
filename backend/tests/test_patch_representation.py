import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import tempfile
import json
import sys
import copy

from agents.code_generator import agent_code_generator
from agents.pr_author import agent_pr_author

class TestPatchRepresentation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.repo_dir = os.path.join(self.tmp_dir, "repo")
        os.makedirs(self.repo_dir)
        self.target_file = "test.py"
        with open(os.path.join(self.repo_dir, self.target_file), "w") as f:
            f.write("def foo():\n    pass\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("agents.code_generator.invoke_llm")
    @patch("tools.patch_applier.apply_patch")
    def test_code_generator_stores_patch_text_and_diff(self, mock_apply, mock_invoke):

        mock_invoke.return_value = "<<<SEARCH>>>\n    pass\n<<<REPLACE>>>\n    return 42\n"
        mock_apply.return_value = {"success": True}

        state = {
            "repo_local_path": self.repo_dir,
            "repair_plan": [{"issue_id": "1", "plan": "Fix foo"}],
            "investigated_issues": [{"id": "1", "affected_files": [self.target_file]}],
            "patches": []
        }

        with patch("agents.code_generator.GROQ_API_KEYS", ["test"]), patch("agents.code_generator.open_safe") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "def foo():\n    return 42\n"
            import asyncio
            result = asyncio.run(agent_code_generator(state))

            self.assertIn("patches", result)
            self.assertEqual(len(result["patches"]), 1)
            patch_obj = result["patches"][0]
            self.assertIn("patch_text", patch_obj)
            self.assertEqual(patch_obj["patch_text"], "<<<SEARCH>>>\n    pass\n<<<REPLACE>>>\n    return 42\n")
            self.assertIn("diff", patch_obj)
            self.assertTrue("---" in patch_obj["diff"] or "return 42" in patch_obj["diff"])

    @patch("tools.github_client.create_trusted_pr_workspace")
    @patch("tools.patch_applier.apply_patch")
    @patch("tools.github_client.check_token_permissions")
    @patch("tools.github_client.prepare_repo_for_push")
    def test_pr_author_uses_patch_text(self, mock_prepare, mock_check, mock_apply, mock_create):

        mock_create.return_value = self.repo_dir
        mock_apply.return_value = {"success": True}
        mock_check.return_value = True
        mock_prepare.return_value = {"push_url": "https://github.com/test", "base_branch": "main"}

        state = {
            "repo_url": "https://github.com/test/test",
            "repo_local_path": self.repo_dir,
            "commit_sha": "abc1234",
            "patches": [
                {
                    "file": self.target_file,
                    "patch_text": "<<<SEARCH>>>\n<<<REPLACE>>>\n",
                    "diff": "unified diff should not be used",
                    "applied": True
                }
            ]
        }

        def mock_run_side_effect(cmd, cwd=None, env=None, timeout=None):
            if "rev-parse" in cmd:
                return {"status": "SUCCESS", "stdout": "abc1234"}
            return {"status": "SUCCESS", "stdout": self.target_file}

        with patch("agents.pr_author.run_isolated_subprocess") as mock_run:
            mock_run.side_effect = mock_run_side_effect
            with patch("agents.pr_author.GROQ_API_KEYS", ["test"]), patch.dict(os.environ, {"GITHUB_TOKEN": "test"}):
                import asyncio
                res = asyncio.run(agent_pr_author(state))
                mock_apply.assert_called_once_with("<<<SEARCH>>>\n<<<REPLACE>>>\n", self.repo_dir, self.target_file)

    @patch("tools.github_client.create_trusted_pr_workspace")
    @patch("tools.patch_applier.apply_patch")
    @patch("tools.github_client.check_token_permissions")
    @patch("tools.github_client.prepare_repo_for_push")
    def test_pr_author_missing_patch_text_fails_safely(self, mock_prepare, mock_check, mock_apply, mock_create):

        mock_create.return_value = self.repo_dir
        mock_check.return_value = True
        mock_prepare.return_value = {"push_url": "https://github.com/test", "base_branch": "main"}

        state = {
            "repo_url": "https://github.com/test/test",
            "repo_local_path": self.repo_dir,
            "commit_sha": "abc1234",
            "patches": [
                {
                    "file": self.target_file,
                    "diff": "legacy unified diff",
                    "applied": True
                }
            ]
        }

        def mock_run_side_effect(cmd, cwd=None, env=None, timeout=None):
            if "rev-parse" in cmd:
                return {"status": "SUCCESS", "stdout": "abc1234"}
            return {"status": "SUCCESS", "stdout": self.target_file}

        with patch("agents.pr_author.run_isolated_subprocess") as mock_run:
            mock_run.side_effect = mock_run_side_effect
            with patch("agents.pr_author.GROQ_API_KEYS", ["test"]), patch.dict(os.environ, {"GITHUB_TOKEN": "test"}):
                import asyncio
                res = asyncio.run(agent_pr_author(state))
                mock_apply.assert_not_called()
                self.assertIn("pr_error", res)
                self.assertIn("Secure patch_text is missing", res["pr_error"])

    def test_patch_text_reapplied_successfully(self):

        from tools.patch_applier import apply_patch
        patch_text = "<<<SEARCH>>>\ndef foo():\n    pass\n<<<REPLACE>>>\ndef foo():\n    return 42\n"
        res = apply_patch(patch_text, self.tmp_dir, "repo/test.py")
        self.assertTrue(res.get("success"))
        with open(os.path.join(self.repo_dir, self.target_file), "r") as f:
            content = f.read()
            self.assertIn("return 42", content)
            
if __name__ == "__main__":
    unittest.main()
