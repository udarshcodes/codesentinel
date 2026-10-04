import pytest
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch

client = TestClient(app)

def test_analyze_single_repo():
    with patch("api.routes.trigger_github_worker"):
        res = client.post("/api/v1/analyze", json={"repo_url": "https://github.com/owner/repo"})
        assert res.status_code == 200

def test_analyze_org_limits():
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
            self.headers = {}
        def json(self):
            return self.json_data
            
    async def mock_get(*args, **kwargs):
        repos = [{"html_url": f"https://github.com/org/repo{i}", "archived": False} for i in range(11)]
        return MockResponse(repos, 200)
        
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        res = client.post("/api/v1/analyze", json={"repo_url": "https://github.com/org/*"})
        assert res.status_code == 413
        assert "exceeds maximum allowed repositories" in res.text
