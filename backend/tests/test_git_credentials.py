import unittest
import os
import pytest
from unittest.mock import patch, MagicMock
from agents.repo_mapper import agent_repo_mapper

class TestGitCredentials(unittest.IsolatedAsyncioTestCase):
    @patch('subprocess.run')
    async def test_fetch_repo_credentials_not_in_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="success")
        
        token = "secret_gh_token_123"
        repo_url = "https://github.com/owner/repo"
        
        with patch.dict(os.environ, {"GITHUB_TOKEN": token}):
            await agent_repo_mapper({"repo_url": repo_url})
            
        # Verify that the token doesn't appear in ANY subprocess call arguments
        for call in mock_run.call_args_list:
            args = call[0][0] # The command list
            for arg in args:
                self.assertNotIn(token, arg)
                
            # Verify it uses the config env vars
            if args[1] == "clone":
                env = call[1].get("env", {})
                self.assertEqual(env.get("GIT_CONFIG_COUNT"), "1")
                self.assertIn("AUTHORIZATION: bearer secret_gh_token_123", env.get("GIT_CONFIG_VALUE_0", ""))

