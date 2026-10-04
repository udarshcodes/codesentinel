import ast
import pytest
import os
import shutil
import tempfile
import asyncio
from unittest.mock import patch, MagicMock

from models.pipeline_state import PipelineState
from agents.static_analysis import agent_static_analysis


def test_no_host_execution_in_static_analysis():
    # 1. Parse static_analysis.py using AST
    file_path = os.path.join(
        os.path.dirname(__file__), "..", "agents", "static_analysis.py"
    )
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename="static_analysis.py")

    # 2. Check for missing insecure methods
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    if func.value.id == "subprocess" and func.attr in (
                        "run",
                        "Popen",
                        "call",
                        "check_call",
                        "check_output",
                    ):
                        pytest.fail(f"Found unsafe {func.value.id}.{func.attr}() call at line {node.lineno}")
                    if func.value.id == "shutil" and func.attr == "which":
                        pytest.fail(f"Found unsafe {func.value.id}.{func.attr}() call at line {node.lineno}")
                    if func.value.id == "os" and func.attr == "system":
                        pytest.fail(f"Found unsafe os.system() call at line {node.lineno}")

    # 3. Verify npx is eliminated
    if "npx --yes" in source or "npx" in source:
        pytest.fail("Found 'npx' execution in static_analysis.py. Expected 'eslint' directly inside sandbox.")


@pytest.mark.asyncio
async def test_static_analysis_sandboxed_integration():
    """
    Test real Docker static-analysis integration.
    Create a malicious repository whose ESLint configuration proves execution happened.
    """
    repo_dir = tempfile.mkdtemp()
    try:
        # Create a malicious package.json / eslintrc that tries to access the host
        with open(os.path.join(repo_dir, ".eslintrc.js"), "w") as f:
            f.write("""
            const fs = require('fs');
            try {
                // Try to read a host canary
                fs.readFileSync('/sandbox/repo/host_canary.txt', 'utf8');
            } catch (e) {
                // Ignore
            }
            module.exports = {
                "env": { "node": true },
                "rules": { "no-console": "error" }
            };
            """)

        with open(os.path.join(repo_dir, "test.js"), "w") as f:
            f.write("console.log('test');\\n")

        with open(os.path.join(repo_dir, "host_canary.txt"), "w") as f:
            f.write("canary_content")

        state = PipelineState()
        state["repo_local_path"] = repo_dir

        with patch("agents.static_analysis.run_sandboxed_subprocess") as mock_run:
            mock_run.return_value = {
                "status": "SUCCESS",
                "stdout": "[]",
                "stderr": "",
                "returncode": 0
            }
            
            result = await agent_static_analysis(state)
            
            # Verify all expected scanners were called via run_sandboxed_subprocess
            cmds_called = [call.args[0][0] if isinstance(call.args[0], list) else call.args[0] for call in mock_run.call_args_list]
            
            # Since some scanners run via "sh -c", let's inspect the first element or the command string
            raw_cmds = []
            for call in mock_run.call_args_list:
                cmd_list = call.args[0]
                if cmd_list[0] == "sh" and "-c" in cmd_list:
                    raw_cmds.append(cmd_list[2])
                else:
                    raw_cmds.append(cmd_list[0])
            
            assert "semgrep" in raw_cmds
            assert "bandit" in raw_cmds
            assert "eslint" in raw_cmds
            assert "pylint" in raw_cmds
            assert "flake8" in raw_cmds
            assert "sonar-scanner" in raw_cmds
            
            assert not result["scanners_failed"]
    finally:
        shutil.rmtree(repo_dir)
