import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.subprocess_runner import run_isolated_subprocess

def test_run_isolated_subprocess_success():
    result = run_isolated_subprocess([sys.executable, "-c", "print('hello world')"], cwd=os.getcwd())
    assert result["status"] == "SUCCESS"
    assert "hello world" in result["stdout"]

def test_run_isolated_subprocess_timeout():
    result = run_isolated_subprocess([sys.executable, "-c", "import time; time.sleep(5)"], cwd=os.getcwd(), timeout=1)
    assert result["status"] == "TIMEOUT"
    assert "Command timed out" in result["error"]

def test_run_isolated_subprocess_malicious_env_leak():
    # Set a secret in the environment
    os.environ["SUPER_SECRET_TOKEN"] = "12345"
    
    # Try to print the environment from the subprocess
    result = run_isolated_subprocess([sys.executable, "-c", "import os; print(os.environ.get('SUPER_SECRET_TOKEN', 'not_found'))"], cwd=os.getcwd())
    
    # The subprocess should NOT have access to SUPER_SECRET_TOKEN
    assert "not_found" in result["stdout"]
    assert "12345" not in result["stdout"]

def test_run_isolated_subprocess_resource_limits():
    if os.name == 'nt':
        pytest.skip("Resource limits via rlimit not supported on Windows")
        
    # Attempt to allocate excessive memory
    script = "a = 'x' * (256 * 1024 * 1024)" # Try to allocate 256MB
    
    # Run with a max_memory of 64MB
    result = run_isolated_subprocess([sys.executable, "-c", script], cwd=os.getcwd(), max_memory_mb=64)
    
    # Should crash with MemoryError or be killed
    assert result["status"] == "FAILED"
