import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from limiter import limiter

class TestApiAnalyzeDispatch(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        self.client = TestClient(app)

    @patch("api.routes.trigger_github_worker")
    def test_analyze_success_quick_return(self, mock_trigger):
        """Test that analyze returns quickly."""
        
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)
        self.assertTrue(len(data["task_id"]) > 0)
        self.assertIn("view_token", data)
        self.assertTrue(len(data["view_token"]) > 0)
        
    @patch("api.routes.trigger_github_worker")
    def test_analyze_dispatch_failure_non_blocking(self, mock_trigger):
        """Test dispatch failure is non-blocking"""
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        self.assertEqual(response.status_code, 200)

    @patch("api.routes.trigger_github_worker")
    def test_analyze_rate_limit(self, mock_trigger):
        """Test rate limit returns 429 cleanly"""
        limiter.enabled = True
        try:
            res1 = self.client.post("/api/v1/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}, headers={"X-Forwarded-For": "192.168.1.100"})
            res2 = self.client.post("/api/v1/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}, headers={"X-Forwarded-For": "192.168.1.100"})
            res3 = self.client.post("/api/v1/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}, headers={"X-Forwarded-For": "192.168.1.100"})
            
            self.assertEqual(res3.status_code, 429)
            self.assertIn("error", res3.json())
        finally:
            limiter.enabled = False
