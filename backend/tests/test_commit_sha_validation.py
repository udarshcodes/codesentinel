import pytest
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch

client = TestClient(app)

def test_commit_sha_valid():
    with patch("api.routes.trigger_github_worker"):
        res = client.post("/api/v1/analyze", json={
            "repo_url": "https://github.com/owner/repo",
            "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        })
        assert res.status_code == 200
        
        res = client.post("/api/v1/analyze", json={
            "repo_url": "https://github.com/owner/repo",
            "commit_sha": "a1b2c3d"
        })
        assert res.status_code == 200

def test_commit_sha_invalid():
    invalid_shas = [
        "a1b2", # too short
        "main", # branch name
        "v1.0", # tag
        "../foo", # path traversal
        "HEAD^", # arbitrary ref
        "a b c d e f g" # spaces
    ]
    
    with patch("api.routes.trigger_github_worker"):
        for sha in invalid_shas:
            res = client.post("/api/v1/analyze", json={
                "repo_url": "https://github.com/owner/repo",
                "commit_sha": sha
            })
            assert res.status_code == 400
            assert "valid 7-40 character hexadecimal" in res.text
