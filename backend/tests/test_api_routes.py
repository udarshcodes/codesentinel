"""
Tests for api/routes.py — API endpoints for analyze, approve, and webhook.
"""

import os
import sys
import unittest
from unittest.mock import patch
import hmac
import hashlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app


@patch("api.routes.run_pipeline_worker")
class TestApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_valid_repo_url(self, mock_worker):
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)
        self.assertIn("task_ids", data)

    def test_invalid_repo_url(self, mock_worker):
        response = self.client.post(
            "/api/v1/analyze", json={"repo_url": "not-a-valid-url"}
        )
        self.assertEqual(response.status_code, 400)

    def test_backward_compat_route(self, mock_worker):
        response = self.client.post(
            "/api/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}
        )
        self.assertEqual(response.status_code, 200)

    def test_missing_repo_url(self, mock_worker):
        response = self.client.post("/api/v1/analyze", json={})
        self.assertEqual(response.status_code, 422)

    def test_approve_no_pipeline(self, mock_worker):
        response = self.client.post(
            "/api/v1/approve/nonexistent-task", json={"decision": "approved"}
        )
        self.assertEqual(response.status_code, 404)

    def test_approve_invalid_decision(self, mock_worker):
        response = self.client.post(
            "/api/v1/approve/some-task", json={"decision": "maybe"}
        )
        self.assertEqual(response.status_code, 400)

    def test_webhook_no_event_header(self, mock_worker):
        response = self.client.post("/api/v1/webhook/github", json={})
        data = response.json()
        self.assertEqual(data.get("status"), "ignored")

    def test_webhook_push_to_main(self, mock_worker):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)

    def test_webhook_push_to_feature_branch_ignored(self, mock_worker):
        payload = {
            "ref": "refs/heads/feature/something",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        self.assertEqual(data["status"], "ignored")

    def test_webhook_pr_opened(self, mock_worker):
        payload = {
            "action": "opened",
            "pull_request": {"head": {"sha": "def456"}},
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        data = response.json()
        self.assertEqual(data["status"], "accepted")

    def test_webhook_signature_verification(self, mock_worker):
        secret = "test_secret_123"
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
            payload = json.dumps(
                {
                    "ref": "refs/heads/main",
                    "after": "abc123",
                    "repository": {
                        "html_url": "https://github.com/octocat/Hello-World"
                    },
                }
            ).encode()

            sig = (
                "sha256="
                + hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
            )

            response = self.client.post(
                "/api/v1/webhook/github",
                content=payload,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
            self.assertEqual(response.status_code, 200)

    def test_webhook_missing_signature_rejected(self, mock_worker):
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "some_secret"}):
            response = self.client.post(
                "/api/v1/webhook/github",
                json={"repository": {"html_url": "https://github.com/foo/bar"}},
                headers={"X-GitHub-Event": "push"},
            )
            self.assertEqual(response.status_code, 403)

    def test_health(self, mock_worker):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch("api.routes.httpx.AsyncClient")
    def test_analyze_multi_repo_empty(self, mock_client, mock_worker):
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get.return_value.status_code = 404
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/nonexistentorg/*"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Could not find any active public repositories", response.json()["detail"]
        )


if __name__ == "__main__":
    unittest.main()
