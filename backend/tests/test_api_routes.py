"""
Tests for api/routes.py — API endpoints for analyze, approve, and webhook.
"""

import os
import sys
import pytest
import hmac
import hashlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    from main import app

    return TestClient(app)


class TestAnalyzeEndpoint:
    def test_valid_repo_url(self, client):
        response = client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "task_id" in data
        assert "task_ids" in data

    def test_invalid_repo_url(self, client):
        response = client.post("/api/v1/analyze", json={"repo_url": "not-a-valid-url"})
        assert response.status_code == 400

    def test_backward_compat_route(self, client):
        response = client.post(
            "/api/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}
        )
        assert response.status_code == 200

    def test_missing_repo_url(self, client):
        response = client.post("/api/v1/analyze", json={})
        assert response.status_code == 422  # Pydantic validation error


class TestApproveEndpoint:
    def test_approve_no_pipeline(self, client):
        response = client.post(
            "/api/v1/approve/nonexistent-task", json={"decision": "approved"}
        )
        assert response.status_code == 404

    def test_approve_invalid_decision(self, client):
        response = client.post("/api/v1/approve/some-task", json={"decision": "maybe"})
        assert response.status_code == 400


class TestWebhookEndpoint:
    def test_webhook_no_event_header(self, client):
        response = client.post("/api/v1/webhook/github", json={})
        data = response.json()
        assert data.get("status") == "ignored"

    def test_webhook_push_to_main(self, client):
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        assert data["status"] == "accepted"
        assert "task_id" in data

    def test_webhook_push_to_feature_branch_ignored(self, client):
        payload = {
            "ref": "refs/heads/feature/something",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        assert data["status"] == "ignored"

    def test_webhook_pr_opened(self, client):
        payload = {
            "action": "opened",
            "pull_request": {"head": {"sha": "def456"}},
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        data = response.json()
        assert data["status"] == "accepted"

    def test_webhook_signature_verification(self, client, monkeypatch):
        secret = "test_secret_123"
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)

        payload = json.dumps(
            {
                "ref": "refs/heads/main",
                "after": "abc123",
                "repository": {"html_url": "https://github.com/octocat/Hello-World"},
            }
        ).encode()

        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        # Reload config after env change — the webhook reads os.getenv at runtime
        response = client.post(
            "/api/v1/webhook/github",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

    def test_webhook_missing_signature_rejected(self, client, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "some_secret")

        response = client.post(
            "/api/v1/webhook/github",
            json={"repository": {"html_url": "https://github.com/foo/bar"}},
            headers={"X-GitHub-Event": "push"},
        )
        assert response.status_code == 403


class TestHealthEndpoint:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
