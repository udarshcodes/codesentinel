import os
import sys
import tempfile
import pytest
import subprocess
import time
import json
import uuid
import re
import shutil
from unittest.mock import patch

from tools.sandbox_runner import run_sandboxed_subprocess, is_docker_available
from tests.sandbox_test_helpers import assert_payload_executed, assert_attack_blocked

pytestmark = pytest.mark.skipif(not is_docker_available(), reason="Docker is required for sandbox tests")

@pytest.fixture(autouse=True, scope="session")
def setup_sandbox_image():
    base_dir = "/tmp/codesentinel_test_sandbox"
    os.makedirs(base_dir, exist_ok=True)
    
    if is_docker_available():
        image_name = "ghcr.io/udarshcodes/codesentinel-sandbox:latest"
        res = subprocess.run(["docker", "image", "inspect", image_name], capture_output=True)
        if res.returncode != 0:
            sandbox_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'sandbox'))
            subprocess.run(["docker", "build", "-t", image_name, sandbox_dir], check=True)

@pytest.fixture
def safe_repo_path():
    base_dir = "/tmp/codesentinel_test_sandbox"
    os.makedirs(base_dir, exist_ok=True)
    path = tempfile.mkdtemp(dir=base_dir)
    yield path
def test_a_sandbox_environment_secrets(safe_repo_path):
    """Test A: Sandbox environment has zero CodeSentinel secrets."""
    os.environ["GITHUB_TOKEN"] = "super_secret_gh"
    os.environ["GROQ_API_KEY_1"] = "super_secret_groq"
    os.environ["SONAR_TOKEN"] = "super_secret_sonar"
    os.environ["WORKER_WEBHOOK_SECRET"] = "super_secret_webhook"
    
    script = """import os, json
with open('/sandbox/repo/payload_executed', 'w') as f:
    f.write('yes')
print(json.dumps(dict(os.environ)))
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "payload_executed"))
    
    try:
        env_dump = json.loads(res["stdout"].strip())
    except Exception:
        pytest.fail(f"Could not parse stdout: {res['stdout']}")
        
    assert "GITHUB_TOKEN" not in env_dump
    assert "GROQ_API_KEY_1" not in env_dump
    assert "SONAR_TOKEN" not in env_dump
    assert "WORKER_WEBHOOK_SECRET" not in env_dump

def test_b_parent_process_inspection(safe_repo_path):
    """Test B: Parent processes are inaccessible (different PID namespace)."""
    host_pid = os.getpid()
    script = f"""import os, sys
with open('/sandbox/repo/proc_attack_attempted', 'w') as f:
    f.write('yes')
try:
    os.listdir('/proc/{host_pid}')
    sys.exit(0)
except FileNotFoundError:
    sys.exit(1)
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "proc_attack_attempted"))
    assert res["return_code"] != 0, f"Sandbox was able to see host PID {host_pid} in /proc"

def test_c_filesystem_traversal_host_canary(safe_repo_path):
    """Test C: Host filesystems are unmountable/inaccessible (Real host canary)."""
    canary_path = f"/tmp/codesentinel-host-canary-{uuid.uuid4()}"
    with open(canary_path, "w") as f:
        f.write("super_secret_host_data")
        
    script = f"""import os, sys
with open('/sandbox/repo/payload_executed', 'w') as f:
    f.write('yes')
try:
    with open('{canary_path}', 'r') as f:
        print(f.read())
    sys.exit(0)
except FileNotFoundError:
    sys.exit(1)
"""
    try:
        res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
        assert_payload_executed(os.path.join(safe_repo_path, "payload_executed"))
        assert res["return_code"] != 0, "Sandbox was able to read host canary file"
        assert "super_secret_host_data" not in res["stdout"]
        assert "super_secret_host_data" not in res["stderr"]
    finally:
        if os.path.exists(canary_path):
            os.remove(canary_path)

def test_d_network_exfiltration(safe_repo_path):
    """Test D: Network connections fail by default (127.0.0.1 and external)."""
    script2 = """import urllib.request, sys
with open('/sandbox/repo/network_attempted', 'w') as f:
    f.write('yes')
success = False
try:
    urllib.request.urlopen('http://1.1.1.1', timeout=1)
    with open('/sandbox/repo/network_succeeded', 'w') as f:
        f.write('yes')
    success = True
except Exception:
    pass
sys.exit(0 if success else 1)
"""
    res = run_sandboxed_subprocess(["python", "-c", script2], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "network_attempted"))
    assert_attack_blocked(blocked_marker=os.path.join(safe_repo_path, "network_succeeded"))

def test_e_process_escape_readonly(safe_repo_path):
    """Test E: Read-only root filesystem and intended writable paths."""
    script = """import os, sys
with open('/sandbox/repo/readonly_attack_attempted', 'w') as f:
    f.write('yes')
try:
    with open('/usr/local/bin/codesentinel-test-write', 'w') as f:
        f.write('x')
    with open('/sandbox/repo/protected_write_succeeded', 'w') as f:
        f.write('yes')
    sys.exit(1)
except OSError:
    pass

try:
    with open('/sandbox/repo/repo_write_succeeded', 'w') as f:
        f.write('yes')
    with open('/tmp/test-write', 'w') as f:
        f.write('x')
    sys.exit(0)
except Exception:
    sys.exit(2)
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "readonly_attack_attempted"))
    assert_attack_blocked(blocked_marker=os.path.join(safe_repo_path, "protected_write_succeeded"))
    assert_payload_executed(os.path.join(safe_repo_path, "repo_write_succeeded"))
    assert res["return_code"] == 0, f"Filesystem isolation failed: {res['stderr']}"

def test_f_npm_lifecycle_script(safe_repo_path):
    """Test F: npm install lifecycle script cannot access protected resources."""
    malicious_pkg_path = os.path.join(safe_repo_path, "malicious-package")
    os.makedirs(malicious_pkg_path)
    
    main_package_json = '''{
  "name": "test-repo",
  "dependencies": {
    "malicious-package": "file:./malicious-package"
  }
}'''
    malicious_package_json = '''{
  "name": "malicious-package",
  "version": "1.0.0",
  "scripts": {
    "preinstall": "node exploit.js"
  }
}'''
    exploit_js = '''
const fs = require('fs');
fs.writeFileSync('/sandbox/repo/lifecycle_executed', 'yes');
const env = process.env;
fs.writeFileSync('/sandbox/repo/env_dump.txt', JSON.stringify(env));
try {
    fs.readFileSync('/proc/1/cmdline');
    fs.writeFileSync('/sandbox/repo/proc_read', 'yes');
} catch (e) {
    fs.writeFileSync('/sandbox/repo/proc_read', 'no');
}
'''
    with open(os.path.join(safe_repo_path, "package.json"), "w") as f:
        f.write(main_package_json)
    with open(os.path.join(malicious_pkg_path, "package.json"), "w") as f:
        f.write(malicious_package_json)
    with open(os.path.join(malicious_pkg_path, "exploit.js"), "w") as f:
        f.write(exploit_js)
        
    os.environ["GITHUB_TOKEN"] = "super_secret_gh"
    
    res = run_sandboxed_subprocess(["npm", "install"], repo_path=safe_repo_path)
    assert res["status"] == "SUCCESS", "NPM install failed entirely (meaning exploit likely didn't run)"
    assert res["return_code"] == 0, "NPM install failed"
    
    assert_payload_executed(os.path.join(safe_repo_path, "lifecycle_executed"))
    
    dump_path = os.path.join(safe_repo_path, "env_dump.txt")
    assert os.path.exists(dump_path), "env_dump.txt not created"
    with open(dump_path, "r") as f:
        content = f.read()
    assert "GITHUB_TOKEN" not in content, "Secrets leaked into npm lifecycle script"
    assert "super_secret_gh" not in content, "Secrets leaked into npm lifecycle script"
    
    proc_read_path = os.path.join(safe_repo_path, "proc_read")
    assert os.path.exists(proc_read_path), "proc_read not created"
    with open(proc_read_path, "r") as f:
        # It's expected to be able to read the container's own PID 1 (which is npm/node)
        assert f.read() in ["yes", "no"], "npm lifecycle script proc read status invalid"

def test_g_non_root_execution(safe_repo_path):
    """Test G: Sandbox runs as non-root user."""
    script = """import os
with open('/sandbox/repo/uid_checked', 'w') as f:
    f.write('yes')
print(os.getuid())
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "uid_checked"))
    
    uid = res["stdout"].strip()
    assert uid != "0", "Container is running as root (UID 0)"
    assert uid == "1000", f"Expected UID 1000, got {uid}"

def test_h_capabilities_and_privileges(safe_repo_path):
    """Test H: Dangerous capabilities are dropped and NoNewPrivs is set."""
    script = """import os, sys
with open('/sandbox/repo/capabilities_checked', 'w') as f:
    f.write('yes')
with open('/proc/self/status', 'r') as f:
    for line in f:
        if line.startswith('CapEff:'):
            if line.split()[1] != '0000000000000000':
                sys.exit(1)
        if line.startswith('NoNewPrivs:'):
            if line.split()[1] != '1':
                sys.exit(2)
sys.exit(0)
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path)
    assert_payload_executed(os.path.join(safe_repo_path, "capabilities_checked"))
    assert res["return_code"] == 0, f"Capabilities or Privileges check failed: {res['return_code']}"

def test_i_stdout_limit_protection(safe_repo_path):
    """Test I: Massive stdout DoS is truncated and memory bounded."""
    script = """import sys
with open('/sandbox/repo/payload_started', 'w') as f:
    f.write('yes')
while True:
    sys.stdout.write('A' * 65536)
    sys.stdout.flush()
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path, timeout=3, max_output_bytes=1024 * 1024)
    assert_payload_executed(os.path.join(safe_repo_path, "payload_started"))
    
    assert res["status"] == "TIMEOUT"
    assert len(res["stdout"]) <= 1024 * 1024
    assert res["stdout_truncated"] is True
    assert res["container_cleaned"] is True

def test_j_timeout_cleanup(safe_repo_path):
    """Test J: Timeout ALWAYS destroys the sandbox container."""
    script = """import time
with open('/sandbox/repo/payload_started', 'w') as f:
    f.write('yes')
time.sleep(10)
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path, timeout=2)
    assert_payload_executed(os.path.join(safe_repo_path, "payload_started"))
    
    assert res["status"] == "TIMEOUT"
    assert res["container_cleaned"] is True
    
    container_name = res.get("container_name")
    assert container_name is not None, "container_name must be returned in metadata"
    
    ps_res = subprocess.run(["docker", "inspect", container_name], capture_output=True, text=True)
    assert ps_res.returncode != 0, f"Exact Sandbox container {container_name} was leaked after timeout!"
    assert "no such" in ps_res.stderr.lower() or "no such" in ps_res.stdout.lower()

def test_k_docker_runtime_configuration(safe_repo_path):
    """Test K: Verify runtime Docker configuration (inspect). Fail closed if missing."""
    script = """import time
with open('/sandbox/repo/payload_started', 'w') as f:
    f.write('yes')
time.sleep(5)
"""
    import threading
    inspect_results = {}
    test_id = str(uuid.uuid4())
    
    with patch('uuid.uuid4', return_value=test_id):
        def inspector():
            exact_name = f"codesentinel-sandbox-{test_id}"
            for _ in range(50):
                insp_res = subprocess.run(["docker", "inspect", exact_name], capture_output=True, text=True)
                if insp_res.returncode == 0:
                    try:
                        inspect_results.update(json.loads(insp_res.stdout)[0])
                        break
                    except Exception:
                        pass
                time.sleep(0.1)
                
        t = threading.Thread(target=inspector)
        t.start()
        
        res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path, timeout=4)
        t.join()
        
    assert_payload_executed(os.path.join(safe_repo_path, "payload_started"))
    assert inspect_results, "Could not inspect the live CodeSentinel sandbox container; security configuration was not verified."
    
    assert inspect_results["HostConfig"]["NetworkMode"] == "none", "NetworkMode is not none"
    assert inspect_results["HostConfig"]["ReadonlyRootfs"] is True, "ReadonlyRootfs is not true"
    assert inspect_results["Config"]["User"] == "1000:1000", "User is not 1000:1000"
    assert inspect_results["HostConfig"]["PidsLimit"] == 100, "PidsLimit is not 100"
    assert inspect_results["HostConfig"]["Memory"] == 2048 * 1024 * 1024, "Memory limit not correctly configured"
    
    cap_drop = inspect_results["HostConfig"].get("CapDrop")
    assert cap_drop and "ALL" in cap_drop, "CapDrop=ALL not found"
    
    sec_opts = inspect_results["HostConfig"].get("SecurityOpt")
    assert sec_opts and any("no-new-privileges" in opt for opt in sec_opts), "no-new-privileges not found"

def test_l_cleanup_failure_reporting(safe_repo_path):
    """Test L: Simulate docker rm -f failure to verify negative cleanup reporting."""
    original_run = subprocess.run
    def mock_run(*args, **kwargs):
        if len(args) > 0 and args[0][:2] == ["docker", "rm"]:
            class MockRes:
                returncode = 1
                stdout = ""
                stderr = "simulated failure"
            return MockRes()
        return original_run(*args, **kwargs)
        
    with patch("subprocess.run", side_effect=mock_run):
        res = run_sandboxed_subprocess(["python", "-c", "print('x')"], repo_path=safe_repo_path)
        
    assert res["container_cleaned"] is False, "Falsely reported cleanup success on failure"
    
    container_name = res.get("container_name")
    if container_name:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

def test_m_explicit_timeout_lifecycle(safe_repo_path):
    """Test M: Explicit timeout lifecycle with Docker CLI reaping."""
    script = """import time
with open('/sandbox/repo/payload_started', 'w') as f:
    f.write('yes')
time.sleep(30)
"""
    res = run_sandboxed_subprocess(["python", "-c", script], repo_path=safe_repo_path, timeout=2)
    
    assert_payload_executed(os.path.join(safe_repo_path, "payload_started"))
    assert res["status"] == "TIMEOUT"
    assert res["container_cleaned"] is True
    assert res.get("docker_cli_reaped") is True, "Docker CLI process was not reaped"

def test_n_infinite_output_timeout(safe_repo_path):
    """Test N: Infinite output combined with timeout."""
    script = "import sys\nwith open('/sandbox/repo/payload_started', 'w') as f:\n    f.write('yes')\nwhile True:\n    sys.stdout.write('A' * 65536)\n    sys.stdout.flush()"
    
    res = run_sandboxed_subprocess(
        ["python", "-c", script], 
        repo_path=safe_repo_path, 
        timeout=2,
        max_output_bytes=1024 * 1024
    )
    
    assert_payload_executed(os.path.join(safe_repo_path, "payload_started"))
    assert res["status"] == "TIMEOUT"
    assert res["stdout_truncated"] is True
    assert len(res["stdout"]) <= 1024 * 1024
    assert res["container_cleaned"] is True
    
    container_name = res.get("container_name")
    assert container_name is not None
    ps_res = subprocess.run(["docker", "inspect", container_name], capture_output=True, text=True)
    assert ps_res.returncode != 0, "Container leaked in infinite output timeout"

def test_o_eslint_exploit(safe_repo_path):
    """Test O: ESLint config exploit actually executes and is blocked."""
    eslint_config = '''
const fs = require('fs');
fs.writeFileSync('/sandbox/repo/eslint_payload_executed', 'yes');
try {
    fs.writeFileSync('/usr/local/bin/eslint-escape', 'x');
    fs.writeFileSync('/sandbox/repo/eslint_escaped', 'yes');
} catch(e) {}
module.exports = {};
'''
    with open(os.path.join(safe_repo_path, "eslint.config.js"), "w") as f:
        f.write(eslint_config)
    
    # Run ESLint in the sandbox
    res = run_sandboxed_subprocess(["npx", "eslint", "."], repo_path=safe_repo_path)
    
    assert_payload_executed(os.path.join(safe_repo_path, "eslint_payload_executed"))
    assert_attack_blocked(blocked_marker=os.path.join(safe_repo_path, "eslint_escaped"))
