import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import subprocess
import tempfile
import sys
from tools.github_client import commit_and_push, check_token_permissions

class TestGithubAuth(unittest.TestCase):
    def setUp(self):
        self.local_path = tempfile.mkdtemp()
        self.branch_name = "test-branch"
        self.message = "test message"
        self.push_repo_url = "https://github.com/owner/repo.git"
        self.token = "fake_github_token"
        
        self.patcher_workspace = patch('tools.github_client.os.path.exists')
        self.mock_exists = self.patcher_workspace.start()
        self.mock_exists.return_value = True

        self.patcher_open = patch('tools.github_client.open', mock_open(read_data='trusted_token'))
        self.mock_open = self.patcher_open.start()

        self.patcher_verify = patch('tools.github_client.verify_trusted_workspace')
        self.mock_verify = self.patcher_verify.start()
        self.mock_verify.return_value = True

    def tearDown(self):
        self.patcher_workspace.stop()
        self.patcher_open.stop()
        self.patcher_verify.stop()
        import shutil
        shutil.rmtree(self.local_path, ignore_errors=True)

    @patch('tools.github_client.os.remove')
    @patch('tools.github_client.subprocess.run')
    def test_token_passed_to_git_securely_via_askpass(self, mock_run, mock_remove):
        mock_run.return_value = MagicMock(returncode=1) # mock diff status


        mock_run.side_effect = [
            None, # git add
            MagicMock(returncode=1), # git diff --cached (changes exist)
            None, # git commit
            None  # git push
        ]

        commit_and_push(
            self.local_path,
            self.branch_name,
            self.message,
            self.push_repo_url,
            self.token,
            ["dummy.py"]
        )

        push_call = mock_run.call_args_list[-1]
        env = push_call[1].get('env', {})
        
        self.assertIn("GIT_ASKPASS", env)
        self.assertEqual(env.get("GIT_TERMINAL_PROMPT"), "0")
        self.assertEqual(env.get("CODESENTINEL_GIT_TOKEN"), self.token)
        
        askpass_path = env["GIT_ASKPASS"]
        mock_remove.assert_called_with(askpass_path)
        
        cmd = push_call[0][0]
        self.assertNotIn(self.token, " ".join(cmd))

    @patch('tools.github_client.subprocess.run')
    def test_token_never_appears_in_exception(self, mock_run):
        mock_run.side_effect = [
            None, # git add
            MagicMock(returncode=1), # diff
            None, # commit
            subprocess.CalledProcessError(1, "git push", stderr=f"fatal: auth failed for token {self.token}")
        ]

        with self.assertRaises(RuntimeError) as context:
            commit_and_push(
                self.local_path,
                self.branch_name,
                self.message,
                self.push_repo_url,
                self.token,
                ["dummy.py"]
            )

        self.assertNotIn(self.token, str(context.exception))
        self.assertIn("***", str(context.exception))

    @patch('tools.github_client.requests.get')
    def test_check_permissions_push_allowed(self, mock_get):
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"permissions": {"push": True}, "owner": {"login": "testuser"}}),
            MagicMock(status_code=200, json=lambda: {"login": "testuser"})
        ]
        
        check_token_permissions("https://github.com/testuser/repo", self.token)

    @patch('tools.github_client.requests.get')
    def test_check_permissions_read_only(self, mock_get):
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: {"permissions": {"push": False}, "owner": {"login": "testuser"}}),
            MagicMock(status_code=200, json=lambda: {"login": "testuser"})
        ]
        
        with self.assertRaises(RuntimeError) as context:
            check_token_permissions("https://github.com/testuser/repo", self.token)
            
        self.assertIn("GitHub token does not have write permission", str(context.exception))

    @patch('tools.github_client.requests.get')
    def test_check_permissions_no_access(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        
        with self.assertRaises(RuntimeError) as context:
            check_token_permissions("https://github.com/testuser/repo", self.token)
            
        self.assertIn("does not have sufficient permission", str(context.exception))

if __name__ == '__main__':
    unittest.main()
