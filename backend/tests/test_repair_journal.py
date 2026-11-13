from unittest.mock import patch
import pytest
from agents.code_generator import agent_code_generator
from tools.patch_applier import apply_patch
from tools.remediations import request_timeout_patch


@pytest.mark.asyncio
async def test_two_timeout_repairs_survive_retry_and_clean_workspace_replay(tmp_path):
    original = "import requests\nrequests.get('https://example.invalid/a')\nrequests.post('https://example.invalid/b')\n"
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'app.py').write_text(original)
    state = {'repo_local_path': str(source), 'patches': [], 'repair_plan': [{'issue_id': 1}, {'issue_id': 2}],
             'investigated_issues': [{'id': id, 'affected_files': ['app.py'], 'original_finding': {'rule': 'B113', 'line': id + 1}} for id in (1, 2)]}
    with patch('agents.code_generator.GROQ_API_KEYS', ['test']), patch('agents.code_generator.invoke_llm') as llm:
        first = await agent_code_generator(state)
        assert len(first['patches']) == 2
        state.update(first, retry_count=1)
        retried = await agent_code_generator(state)
        assert len(retried['patches']) == 2
        llm.assert_not_called()
    trusted = tmp_path / 'trusted'
    trusted.mkdir()
    (trusted / 'app.py').write_text(original)
    for attempt in retried['patches']:
        assert apply_patch(attempt['patch_text'], str(trusted), 'app.py')['success']
    assert (trusted / 'app.py').read_text() == (source / 'app.py').read_text()
    assert (trusted / 'app.py').read_text().count('timeout=30') == 2


def test_timeout_repair_preserves_explicit_timeouts_and_dynamic_kwargs():
    assert request_timeout_patch('import requests\nrequests.get(url, timeout=5)') is None
    assert request_timeout_patch('import requests\nrequests.get(url, **options)') is None


@pytest.mark.asyncio
async def test_comment_only_python_proposal_is_rejected_and_rolled_back(tmp_path):
    original = 'value = 1\n'
    (tmp_path / 'app.py').write_text(original)
    state = {'repo_local_path': str(tmp_path), 'repair_plan': [{'issue_id': 1}],
             'investigated_issues': [{'id': 1, 'affected_files': ['app.py']}]}
    proposal = '<<<SEARCH>>>\nvalue = 1\n<<<REPLACE>>>\n# fixed the issue\nvalue = 1\n'
    with patch('agents.code_generator.GROQ_API_KEYS', ['test']), patch('agents.code_generator.invoke_llm', return_value=proposal):
        result = await agent_code_generator(state)
    assert result['patches'][0]['applied'] is False
    assert 'no AST change' in result['patches'][0]['error']
    assert (tmp_path / 'app.py').read_text() == original
