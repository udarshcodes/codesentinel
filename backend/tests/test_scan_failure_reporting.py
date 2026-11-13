from unittest.mock import AsyncMock, patch

import httpx
import pytest
from agents.static_analysis import agent_static_analysis
from tools.osv_client import batch_query_osv


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(503),
    httpx.Response(200, json={"results": []}),
])
async def test_osv_unavailable_or_incomplete_is_not_clean(response):
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)):
        result = await batch_query_osv([{"name": "requests", "version": "2.32.3", "ecosystem": "PyPI"}])
    assert result is None


@pytest.mark.asyncio
async def test_failed_scanner_without_report_is_not_clean(tmp_path):
    with patch("agents.static_analysis.run_sandboxed_subprocess", return_value={
        "status": "FAILED", "stdout": "", "stderr": "Configuration could not load", "returncode": 2
    }):
        result = await agent_static_analysis({"repo_local_path": str(tmp_path)})
    assert result["scanners_failed"] is True


@pytest.mark.asyncio
async def test_incomplete_scan_cannot_verify_a_patch(tmp_path):
    from agents.security_verifier import agent_security_verifier
    with patch("agents.security_verifier.agent_static_analysis", new=AsyncMock(return_value={
        "static_findings": [], "scanners_failed": True
    })):
        result = await agent_security_verifier({
            "repo_local_path": str(tmp_path), "validation_results": [{"passed": True}],
            "patches": [{"file": "app.py", "applied": True}]
        })
    assert result["security_verified"] is False
