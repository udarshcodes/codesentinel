import pytest
import os
import hmac
import hashlib
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch

client = TestClient(app)

def test_webhook_valid_signature():
    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "test_secret"}):
        payload = b'{"ref": "refs/heads/main"}'
        sig = "sha256=" + hmac.HMAC(b"test_secret", payload, hashlib.sha256).hexdigest()
        
        res = client.post(
            "/api/v1/webhook/github",
            headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"},
            content=payload
        )
        assert res.status_code == 200

def test_webhook_invalid_signature():
    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "test_secret"}):
        payload = b'{"ref": "refs/heads/main"}'
        res = client.post(
            "/api/v1/webhook/github",
            headers={"X-Hub-Signature-256": "sha256=invalid", "X-GitHub-Event": "push"},
            content=payload
        )
        assert res.status_code == 403

def test_webhook_missing_signature():
    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "test_secret"}):
        res = client.post(
            "/api/v1/webhook/github",
            headers={"X-GitHub-Event": "push"},
            json={"ref": "refs/heads/main"}
        )
        assert res.status_code == 403

def test_webhook_fail_closed_production():
    # If in production and secret is missing, it should reject
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "GITHUB_WEBHOOK_SECRET": ""}):
        res = client.post(
            "/api/v1/webhook/github",
            headers={"X-GitHub-Event": "push"},
            json={"ref": "refs/heads/main"}
        )
        assert res.status_code == 403
