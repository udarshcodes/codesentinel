import os
import pytest
from unittest.mock import patch

def test_a_worker_startup_missing_attempt_id():
    import worker as worker_module
    
    with patch.object(worker_module, 'TASK_ID', '123'), \
         patch.object(worker_module, 'REPO_URL', 'http://x'), \
         patch.object(worker_module, 'BACKEND_URL', 'http://x'), \
         patch.object(worker_module, 'WORKER_ATTEMPT_ID', None):
         with pytest.raises(SystemExit) as exc:
             worker_module.validate_env()
         assert exc.value.code == 1

def test_b_worker_startup_missing_secret_production():
    import worker as worker_module
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with patch.object(worker_module, 'TASK_ID', '123'), \
             patch.object(worker_module, 'REPO_URL', 'http://x'), \
             patch.object(worker_module, 'BACKEND_URL', 'http://x'), \
             patch.object(worker_module, 'WORKER_ATTEMPT_ID', 'abc'), \
             patch.object(worker_module, 'WORKER_SECRET', ''):
             with pytest.raises(SystemExit) as exc:
                 worker_module.validate_env()
             assert exc.value.code == 1

def test_c_production_sandbox_no_docker():
    from tools.sandbox_runner import run_sandboxed_subprocess
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with patch('tools.sandbox_runner.is_docker_available', return_value=False):
            with pytest.raises(RuntimeError) as exc:
                run_sandboxed_subprocess(["echo", "hello"], cwd="/tmp")
            assert "Failing closed to prevent insecure process-level execution" in str(exc.value)

def test_c_development_sandbox_no_docker_fallback():
    from tools.sandbox_runner import run_sandboxed_subprocess
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        with patch('tools.sandbox_runner.is_docker_available', return_value=False):
            with patch('tools.sandbox_runner.run_isolated_subprocess') as mock_iso:
                mock_iso.return_value = {"status": "SUCCESS"}
                res = run_sandboxed_subprocess(["echo", "hello"], cwd="/tmp")
                assert res["status"] == "SUCCESS"
                mock_iso.assert_called_once()

def test_d_worker_workflow_configuration():
    workflow_path = os.path.join(os.path.dirname(__file__), "../../.github/workflows/worker.yml")
    with open(workflow_path, 'r') as f:
        content = f.read()
    assert "ENVIRONMENT: production" in content

def test_e_dockerignore_database_exclusions():
    dockerignore_path = os.path.join(os.path.dirname(__file__), "../../backend/.dockerignore")
    with open(dockerignore_path, 'r') as f:
        content = f.read()
    assert "*.db" in content
    assert "*.sqlite" in content
    assert "*.sqlite3" in content

def test_f_worker_sandbox_digest_immutable():
    workflow_path = os.path.join(os.path.dirname(__file__), "../../.github/workflows/worker.yml")
    with open(workflow_path, 'r') as f:
        content = f.read()
    assert "SANDBOX_IMAGE:" in content
    sandbox_line = next(line for line in content.split('\n') if "SANDBOX_IMAGE:" in line)
    assert "@sha256:" in sandbox_line
    assert ":latest" not in sandbox_line
