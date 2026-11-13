from unittest.mock import patch
import pytest
from agents.static_analysis import agent_static_analysis
from agents.bug_investigator import agent_bug_investigator


@pytest.mark.asyncio
async def test_normal_test_assertions_and_public_lm_studio_placeholder_are_not_security_repairs(tmp_path):
    (tmp_path / 'test_app.py').write_text('def test_example():\n    assert True\n')
    (tmp_path / 'app.py').write_text('assert user_is_allowed\napi_key="lm-studio"\n')
    (tmp_path / 'secret.py').write_text('api_key="synthetic-test-secret-value"\n')
    def report(cmd, **kwargs):
        import json
        bandit = [{'filename': filename, 'test_id': 'B101', 'issue_text': 'Use of assert detected', 'issue_severity': 'LOW'} for filename in ('test_app.py', 'app.py')]
        output = {'results': bandit} if cmd[0] == 'bandit' else {'results': []}
        return {'status': 'SUCCESS', 'stdout': json.dumps(output) if cmd[0] in ('semgrep', 'bandit') else '[]' if cmd[0] == 'pylint' else '', 'stderr': '', 'returncode': 0}
    with patch.dict('os.environ', {'ENABLE_SONAR_SCAN': '0'}), patch('agents.static_analysis.run_sandboxed_subprocess', side_effect=report):
        result = await agent_static_analysis({'repo_local_path': str(tmp_path)})
    security = result['static_findings']
    assert not any(f.get('rule') == 'B101' and f['file'] == 'test_app.py' for f in security)
    assert any(f.get('rule') == 'B101' and f['file'] == 'app.py' for f in security)
    assert not any(f.get('tool') == 'secrets_scanner' and f['file'] == 'app.py' for f in security)
    assert any(f.get('tool') == 'secrets_scanner' and f['file'] == 'secret.py' for f in security)


@pytest.mark.asyncio
async def test_investigation_records_dismissals_and_preserves_critical_scanner_severity(tmp_path):
    (tmp_path / 'app.py').write_text('value = 1\n')
    findings = [{'file': 'app.py', 'issue': 'placeholder', 'severity': 'low'}, {'file': 'app.py', 'issue': 'real issue', 'severity': 'CRITICAL'}]
    responses = [{'decision': 'dismiss', 'reason': 'This is a public placeholder value.'}, {'id': 999, 'severity': 'high', 'description': 'real issue', 'affected_files': ['app.py']}]
    with patch('agents.bug_investigator.GROQ_API_KEYS', ['test']), patch('agents.bug_investigator.query_similar_fixes', return_value=[]), patch('agents.bug_investigator.query_codebase', return_value=[]), patch('agents.bug_investigator.invoke_llm', side_effect=responses):
        result = await agent_bug_investigator({'repo_local_path': str(tmp_path), 'repo_url': 'test', 'static_findings': findings})
    assert len(result['dismissed_findings']) == 1
    assert result['investigated_issues'][0]['severity'] == 'critical'
    assert result['investigated_issues'][0]['id'] == 1
