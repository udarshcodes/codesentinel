from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from api.routes import trigger_github_worker
from main import app
from limiter import limiter


@pytest.mark.parametrize("url", ["https://evil.example/org/*", "https://github.com/org/../../other/*"])
def test_invalid_wildcard_rejected_before_network(url):
    limiter.reset()
    with patch("httpx.AsyncClient.get", new=AsyncMock()) as get:
        assert TestClient(app).post("/api/v1/analyze", json={"repo_url": url}).status_code == 400
    get.assert_not_called()


@pytest.mark.asyncio
async def test_production_callback_ignores_request_host(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BACKEND_URL", "https://trusted.example")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=httpx.Response(204))) as post:
        await trigger_github_worker("task", "https://github.com/udarshcodes/setu", "a" * 40,
                                    "attempt", "https://attacker.example")
    assert post.call_args.kwargs["json"]["inputs"]["backend_url"] == "https://trusted.example"
