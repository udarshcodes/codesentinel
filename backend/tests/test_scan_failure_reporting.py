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


@pytest.mark.asyncio
@pytest.mark.parametrize('category,verified', [('quality', True), ('security', False), ('', False)])
async def test_security_gate_distinguishes_style_from_security_findings(tmp_path, category, verified):
    from agents.security_verifier import agent_security_verifier
    finding = {'file': 'app.py', 'category': category, 'issue': 'Existing finding'}
    with patch('agents.security_verifier.agent_static_analysis', new=AsyncMock(return_value={
        'static_findings': [finding], 'scanners_failed': False
    })):
        result = await agent_security_verifier({
            'repo_local_path': str(tmp_path), 'validation_results': [{'passed': True}],
            'patches': [{'file': 'app.py', 'applied': True}]
        })
    assert result['security_verified'] is verified


@pytest.mark.asyncio
async def test_function_length_heuristic_stays_visible_without_automatic_refactor(tmp_path):
    from agents.bug_investigator import agent_bug_investigator
    finding = {'tool': 'long_method_detector', 'file': 'app.py', 'category': 'quality',
               'severity': 'LOW', 'issue': 'Function exceeds the heuristic length limit'}
    with patch('agents.bug_investigator.GROQ_API_KEYS', ['test']), patch('agents.bug_investigator.context_cache.get', return_value=None), patch('agents.bug_investigator.invoke_llm', new=AsyncMock()) as llm:
        result = await agent_bug_investigator({'repo_local_path': str(tmp_path), 'static_findings': [finding]})
    llm.assert_not_called()
    assert result['investigated_issues'][0]['remediation_mode'] == 'manual_review'
