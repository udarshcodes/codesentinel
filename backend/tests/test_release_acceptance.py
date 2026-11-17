import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from agents.code_generator import agent_code_generator, non_behavioral_repair
from agents.repair_planner import agent_repair_planner
from agents.security_verifier import agent_security_verifier
from agents.pr_author import agent_pr_author
from agents.static_analysis import agent_static_analysis
from tools.eslint_scan import scan_eslint_projects, scanner_path
from tools.npm_lock_repair import synchronize_npm_lock
from tools.patch_applier import apply_patch
from agents.bug_investigator import agent_bug_investigator
from tools.llm_router import LLMExhaustionError
from agents.dependency_analyzer import agent_dependency_analyzer, compatible_registry_update
from tools.remediations import npm_dependency_patch


@pytest.mark.asyncio
async def test_completed_rag_index_status_reaches_persisted_node_output():
    async def indexed():
        return {'status':'success', 'documents_indexed':8}
    with patch('agents.bug_investigator.context_cache.get', return_value=indexed()), patch('agents.bug_investigator.GROQ_API_KEYS', []):
        result = await agent_bug_investigator({'repo_url':'test'})
    assert result['rag_status'] == {'status':'success', 'documents_indexed':8}


@pytest.mark.asyncio
async def test_effect_reset_repair_preserves_existing_interactions_without_llm(tmp_path):
    source = """const Popup = () => {
const [visible, setVisible] = useState(false);
useEffect(() => {
if (theme !== 'light') {
setVisible(false);
return;
}
const timer = setTimeout(() => setVisible(true), 2500);
return () => clearTimeout(timer);
}, [theme]);
const dismiss = () => setVisible(false);
};
"""
    (tmp_path / 'Popup.jsx').write_text(source)
    state = {'repo_local_path':str(tmp_path), 'repair_plan':[{'issue_id':0}],
             'investigated_issues':[{'id':0, 'affected_files':['Popup.jsx'],
                                   'original_finding':{'rule':'react-hooks/set-state-in-effect', 'line':5}}]}
    with patch('agents.code_generator.GROQ_API_KEYS', ['test']), patch('agents.code_generator.invoke_llm', AsyncMock()) as llm:
        result = await agent_code_generator(state)
    llm.assert_not_called()
    assert result['patches'][0]['applied']
    updated = (tmp_path / 'Popup.jsx').read_text()
    assert 'const dismiss = () => setVisible(false);' in updated
    assert 'setTimeout(() => setVisible(true), 2500)' in updated


@pytest.mark.asyncio
@pytest.mark.parametrize('latest,candidate_vulns,expected', [('1.2.0', [], '1.2.0'), ('1.2.0', [{'id': 'still-vulnerable'}], None), ('2.0.0', [], None)])
async def test_npm_candidates_require_registry_same_major_and_clean_osv(tmp_path, latest, candidate_vulns, expected):
    node_fixture(tmp_path)
    response = SimpleNamespace(status_code=200, json=lambda: {'version': latest})
    async def osv(packages):
        assert packages
        return {'example': candidate_vulns if packages[0]['version'] == '1.2.0' else [{'id': 'old-cve'}]}
    with patch('httpx.AsyncClient.get', AsyncMock(return_value=response)), patch('tools.osv_client.batch_query_osv', side_effect=osv), patch('tools.osv_client.fetch_vuln_details', AsyncMock(return_value={})):
        result = await agent_dependency_analyzer({'repo_local_path': str(tmp_path)})
    finding = next(f for f in result['dependency_findings'] if f['cve'] != 'N/A')
    assert finding.get('recommended_version') == expected
    if not expected:
        assert finding['remediation_mode'] == 'manual_review'


@pytest.mark.asyncio
@pytest.mark.parametrize('candidate_vulns,expected', [([], '1.2.0'), ([{'id': 'unpatched'}], None)])
async def test_python_upgrade_must_also_have_a_clean_candidate_scan(tmp_path, candidate_vulns, expected):
    (tmp_path / 'requirements.txt').write_text('example==1.0.0\n')
    response = SimpleNamespace(status_code=200, json=lambda: {'info': {'version': '1.2.0'}})
    async def osv(packages):
        return {'example': candidate_vulns if packages[0]['version'] == '1.2.0' else [{'id': 'old-cve'}]}
    with patch('httpx.AsyncClient.get', AsyncMock(return_value=response)), patch('tools.osv_client.batch_query_osv', side_effect=osv), patch('tools.osv_client.fetch_vuln_details', AsyncMock(return_value={})):
        result = await agent_dependency_analyzer({'repo_local_path': str(tmp_path)})
    finding = next(item for item in result['dependency_findings'] if item['cve'] != 'N/A')
    assert finding.get('recommended_version') == expected
    if not expected:
        assert finding['remediation_mode'] == 'manual_review'


@pytest.mark.asyncio
async def test_osv_results_do_not_cross_ecosystems_or_installed_versions():
    from agents.dependency_analyzer import query_dependency_versions
    packages = [{'ecosystem': eco, 'name': 'shared', 'version': version}
                for eco, version in [('PyPI', '1.0.0'), ('npm', '1.0.0'), ('PyPI', '2.0.0')]]
    async def query(batch):
        assert len(batch) == 1
        item = batch[0]
        return {item['name']: [{'id': item['ecosystem'] + ':' + item['version']}]}
    result = await query_dependency_versions(packages, query)
    assert len(result) == 3
    assert result[('PyPI', 'shared', '1.0.0')] != result[('npm', 'shared', '1.0.0')]
    assert result[('PyPI', 'shared', '1.0.0')] != result[('PyPI', 'shared', '2.0.0')]


@pytest.mark.asyncio
async def test_missing_osv_package_response_is_not_interpreted_as_clean():
    from agents.dependency_analyzer import query_dependency_versions
    query = AsyncMock(return_value={})
    assert await query_dependency_versions([{'ecosystem': 'PyPI', 'name': 'example', 'version': '1.0.0'}], query) is None


@pytest.mark.asyncio
async def test_grounded_dependency_repair_overrides_model_downgrade(tmp_path):
    manifest = json.dumps({'devDependencies': {'vite': '^8.0.12', '@vitejs/plugin-react': '^6.0.1'}})
    (tmp_path / 'package.json').write_text(manifest)
    finding = {'package': 'vite', 'ecosystem': 'npm', 'current_version': '8.0.16', 'recommended_version': '8.3.8'}
    state = {'repo_local_path': str(tmp_path), 'repair_plan': [{'issue_id': 0, 'proposed_action': 'Downgrade Vite to 5.0.0'}],
             'investigated_issues': [{'id': 0, 'affected_files': ['package.json'], 'original_finding': finding}]}
    with patch('agents.code_generator.GROQ_API_KEYS', ['test']), patch('agents.code_generator.invoke_llm', AsyncMock()) as llm:
        result = await agent_code_generator(state)
    llm.assert_not_called()
    assert result['patches'][0]['applied']
    updated = json.loads((tmp_path / 'package.json').read_text())
    assert updated['devDependencies'] == {'vite': '8.3.8', '@vitejs/plugin-react': '^6.0.1'}
    assert not compatible_registry_update('8.0.16', '5.4.21')
    with pytest.raises(ValueError):
        npm_dependency_patch(manifest, 'package.json', {**finding, 'recommended_version': '5.4.21'})


@pytest.mark.asyncio
async def test_speculative_css_and_dead_code_findings_are_manual_without_llm_calls():
    findings = [{"tool": tool, "file": "app.css", "issue": "Potential unused code"}
                for tool in ("dead_code_detector", "dead_file_checker", "css_quality_checker")]
    with patch("agents.bug_investigator.GROQ_API_KEYS", ["test"]), patch("agents.bug_investigator.invoke_llm", AsyncMock()) as llm:
        result = await agent_bug_investigator({"static_findings": findings})
    assert len(result["investigated_issues"]) == 3
    assert all(issue["remediation_mode"] == "manual_review" for issue in result["investigated_issues"])
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_investigator_preserves_capacity_pause_instead_of_silently_omitting_findings(tmp_path):
    with patch("agents.bug_investigator.GROQ_API_KEYS", ["test"]), patch("agents.bug_investigator.query_similar_fixes", return_value=[]), patch("agents.bug_investigator.query_codebase", return_value=[]), patch("agents.bug_investigator.invoke_llm", AsyncMock(side_effect=LLMExhaustionError("WAITING_FOR_LLM_CAPACITY", "test", 300, "rate limit"))):
        with pytest.raises(LLMExhaustionError):
            await agent_bug_investigator({"repo_local_path": str(tmp_path), "static_findings": [{"issue": "Actual issue"}]})


def node_fixture(repo):
    manifest = json.dumps({"dependencies": {"example": "1.0.0"}})
    lock = json.dumps({"lockfileVersion": 3, "packages": {
        "": {"dependencies": {"example": "1.0.0"}}, "node_modules/example": {
            "version": "1.0.0", "resolved": "https://registry.npmjs.org/example/-/example-1.0.0.tgz", "integrity": "sha512-example"}}})
    (repo / "package.json").write_text(manifest)
    (repo / "package-lock.json").write_text(lock)
    return manifest, lock


@pytest.mark.asyncio
async def test_generated_dependency_repair_includes_replayable_synchronized_lock(tmp_path):
    original, lock = node_fixture(tmp_path)
    proposal = "<<<SEARCH>>>\n" + original + "\n<<<REPLACE>>>\n" + original.replace("1.0.0", "2.0.0")
    def npm(cmd, **kwargs):
        if "--package-lock-only" in cmd:
            assert "--ignore-scripts" in cmd
            workspace = Path(kwargs["cwd"])
            assert {p.name for p in workspace.iterdir()} == {"package.json", "package-lock.json"}
            (workspace / "package-lock.json").write_text(lock.replace("1.0.0", "2.0.0"))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    llm = AsyncMock(return_value=proposal)
    state = {"repo_local_path": str(tmp_path), "repair_plan": [{"issue_id": 0, "proposed_action": "Repair example dependency"}],
             "investigated_issues": [{"id": 0, "affected_files": ["package.json"]}]}
    with patch("agents.code_generator.GROQ_API_KEYS", ["test"]), patch("agents.code_generator.invoke_llm", llm), patch("tools.npm_lock_repair.subprocess.run", side_effect=npm):
        result = await agent_code_generator(state)
    assert "Issue to fix: Repair example dependency" in llm.call_args.args[0]
    assert [p["file"] for p in result["patches"]] == ["package.json", "package-lock.json"]
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "package.json").write_text(original)
    (clean / "package-lock.json").write_text(lock)
    for p in result["patches"]:
        assert p["applied"]
        assert apply_patch(p["patch_text"], str(clean), p["file"])["success"]
        assert (clean / p["file"]).read_text() == (tmp_path / p["file"]).read_text()


def test_matching_lock_does_not_trigger_online_regeneration(tmp_path):
    node_fixture(tmp_path)
    with patch("tools.npm_lock_repair.subprocess.run") as run:
        assert synchronize_npm_lock(str(tmp_path), "package.json") is None
    run.assert_not_called()


@pytest.mark.asyncio
async def test_dependency_only_planning_preserves_zero_and_nonsequential_ids():
    with patch("agents.repair_planner.GROQ_API_KEYS", ["test"]):
        result = await agent_repair_planner({"investigated_issues": [
            {"id": 0, "description": "Outdated dependency one"}, {"id": 7, "description": "Vulnerable dependency two"}]})
    assert {p["issue_id"] for p in result["repair_plan"]} == {0, 7}


def test_project_eslint_translates_container_paths_and_records_rule(tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/eslint.config.js").write_text("export default []")
    (tmp_path / "frontend/package.json").write_text('{"devDependencies":{"eslint":"10.5.0"}}')
    def runner(command, **kwargs):
        assert command[:2] == ["node", "node_modules/eslint/bin/eslint.js"]
        assert kwargs["cwd"] == str(tmp_path / "frontend")
        return {"status": "FAILED", "returncode": 1, "stdout": json.dumps([{"filePath": "/sandbox/repo/src/App.jsx",
                 "messages": [{"ruleId": "react-hooks/set-state-in-effect", "message": "Fix effect", "severity": 2, "line": 9}]}])}
    with patch("tools.node_dependencies.prepare_node_dependencies", return_value={"status": "ready"}):
        findings, _, failed = scan_eslint_projects(str(tmp_path), runner)
    assert failed is False
    assert findings[0]["file"] == "frontend/src/App.jsx"
    assert findings[0]["rule"] == "react-hooks/set-state-in-effect"
    with pytest.raises(ValueError):
        scanner_path("/sandbox/repo/../../outside.py", str(tmp_path))


@pytest.mark.asyncio
async def test_dependency_repair_is_not_security_verified_with_remaining_cve(tmp_path):
    with patch("agents.security_verifier.agent_static_analysis", AsyncMock(return_value={"static_findings": []})), patch(
        "agents.dependency_analyzer.agent_dependency_analyzer", AsyncMock(return_value={"dependency_findings": [{"file": "package.json", "cve": "TEST-CVE", "issue": "Still vulnerable"}]})):
        result = await agent_security_verifier({"repo_local_path": str(tmp_path), "patches": [{"file": "package.json", "applied": True}], "validation_results": [{"passed": True}]})
    assert result["security_verified"] is False
    assert result["security_retry_context"][0]["cve"] == "TEST-CVE"


def test_css_comment_churn_is_rejected_but_python_syntax_repair_is_allowed():
    assert non_behavioral_repair("style.css", ".x { color:red; }", "/* fixed */\n.x { color:red; }")
    assert not non_behavioral_repair("app.py", "if True print(1)", "if True: print(1)")


def test_patch_never_uses_a_repository_controlled_backup_path(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    (tmp_path / "app.py.bak").write_text("unrelated file must remain unchanged")
    result = apply_patch("<<<SEARCH>>>\nvalue = 1\n<<<REPLACE>>>\nvalue = 2", str(tmp_path), "app.py")
    assert result["success"]
    assert (tmp_path / "app.py.bak").read_text() == "unrelated file must remain unchanged"


def test_patch_backup_symlink_cannot_overwrite_outside_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must not change")
    (repo / "app.py").write_text("value = 1\n")
    try:
        (repo / "app.py.bak").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires platform permission")
    assert apply_patch("<<<SEARCH>>>\nvalue = 1\n<<<REPLACE>>>\nvalue = 2", str(repo), "app.py")["success"]
    assert outside.read_text() == "must not change"


@pytest.mark.asyncio
async def test_successful_publication_clears_an_earlier_repair_error(tmp_path):
    workspace = tmp_path / "trusted"
    workspace.mkdir()
    (workspace / "app.py").write_text("value = 1\n")
    state = {"repo_local_path": str(tmp_path), "repo_url": "https://github.com/example/repo",
             "pr_error": "Earlier repair failed", "security_verified": True,
             "validation_results": [{"passed": True, "tests_executed": True}],
             "patches": [{"file": "app.py", "applied": True, "patch_text": "<<<SEARCH>>>\nvalue = 1\n<<<REPLACE>>>\nvalue = 2"}]}
    import os
    with patch.dict(os.environ, {"GITHUB_TOKEN": "test-only"}), patch("tools.github_client.check_token_permissions"), patch(
        "tools.github_client.create_trusted_pr_workspace", return_value=str(workspace)), patch(
        "tools.github_client.prepare_repo_for_push", return_value={"branch_name":"test", "push_repo_url":"https://github.com/example/repo", "repo_name":"example/repo", "is_owner":True, "user_login":"example"}), patch(
        "agents.pr_author.run_isolated_subprocess", return_value={"status":"SUCCESS", "stdout":"app.py\n"}), patch(
        "tools.github_client.commit_and_push", return_value=True), patch(
        "tools.github_client.open_pull_request", return_value="https://github.com/example/repo/pull/1"), patch("tools.auth.is_lease_lost", return_value=False):
        result = await agent_pr_author(state)
    assert result["pr_error"] == ""
    assert result["pr_url"].endswith("/pull/1")


@pytest.mark.asyncio
async def test_javascript_only_repository_does_not_fail_inapplicable_python_scanners(tmp_path):
    (tmp_path / "app.js").write_text("console.log('hello');")
    with patch("agents.static_analysis.run_sandboxed_subprocess", return_value={"status":"SUCCESS", "stdout":'{"results":[]}', "stderr":"", "returncode":0}) as run:
        result = await agent_static_analysis({"repo_local_path": str(tmp_path)})
    assert not {"bandit", "pylint", "flake8"}.intersection(call.args[0][0] for call in run.call_args_list)
    assert result["scanners_failed"] is False
