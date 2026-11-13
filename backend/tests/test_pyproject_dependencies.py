from unittest.mock import AsyncMock, patch

import pytest
from agents.dependency_analyzer import agent_dependency_analyzer


@pytest.mark.asyncio
async def test_pep621_pins_reach_osv_and_keep_manifest_path(tmp_path):
    manifest = tmp_path / "service" / "pyproject.toml"
    manifest.parent.mkdir()
    manifest.write_text('[project]\ndependencies = ["fastapi==0.111.0", "numpy<2.0"]\n')
    response = type("Response", (), {"status_code": 200,
                    "json": lambda self: {"info": {"version": "9.0.0"}}})()
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)), \
         patch("tools.osv_client.batch_query_osv", new=AsyncMock(return_value={})) as osv, \
         patch("tools.osv_client.fetch_vuln_details", new=AsyncMock(return_value={})):
        result = await agent_dependency_analyzer({"repo_local_path": str(tmp_path)})
    assert osv.call_args.args[0] == [{"name": "fastapi", "version": "0.111.0",
                                      "ecosystem": "PyPI", "file": "service/pyproject.toml"}]
    assert result["dependency_findings"][0]["file"] == "service/pyproject.toml"


@pytest.mark.asyncio
async def test_vulnerable_manifest_dependency_is_reported_without_source_import(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["python-dotenv==1.0.1"]\n')
    response = type("Response", (), {"status_code": 200,
                    "json": lambda self: {"info": {"version": "1.0.1"}}})()
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)), \
         patch("tools.osv_client.batch_query_osv", new=AsyncMock(return_value={
             "python-dotenv": [{"id": "GHSA-test"}]
         })), \
         patch("tools.osv_client.fetch_vuln_details", new=AsyncMock(return_value={})):
        result = await agent_dependency_analyzer({"repo_local_path": str(tmp_path)})
    assert any(f["cve"] == "GHSA-test" for f in result["dependency_findings"])
