import os
import shutil
import subprocess
import threading
import uuid
from typing import Dict, Any
from tools.subprocess_runner import run_isolated_subprocess

_project_dependencies = {}
_node_dependencies = {}
_project_runtimes = {}


def clear_project_runtime(repo):
    _project_runtimes.pop(os.path.realpath(repo), None)


def clear_project_dependencies(repo):
    _project_dependencies.pop(os.path.realpath(repo), None)


def register_project_runtime(repo, runtime):
    repo, root = os.path.realpath(repo), os.path.realpath(runtime['root'])
    if os.path.commonpath([repo, root]) == repo or not os.path.isdir(root):
        raise ValueError('The managed interpreter must live outside the target repository.')
    _project_runtimes[repo] = {**runtime, 'root': root}


def register_node_dependencies(repo, packages):
    repo, packages = os.path.realpath(repo), os.path.realpath(packages)
    try:
        inside_repo = os.path.commonpath([repo, packages]) == repo
    except ValueError:  # Different Windows drives are outside the repository.
        inside_repo = False
    if inside_repo or not os.path.isdir(packages):
        raise ValueError("Node dependencies must live outside the target repository.")
    _node_dependencies[repo] = packages


def register_project_dependencies(repo, packages):
    repo, packages = os.path.realpath(repo), os.path.realpath(packages)
    try:
        inside_repo = os.path.commonpath([repo, packages]) == repo
    except ValueError:
        inside_repo = False
    if inside_repo or not os.path.isdir(packages):
        raise ValueError("Dependencies must live outside the untrusted repository.")
    _project_dependencies[repo] = packages


def is_docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        if res.returncode != 0:
            print("Docker availability probe failed (daemon unavailable or access denied).")
        return res.returncode == 0
    except subprocess.TimeoutExpired:
        print("Docker availability probe timed out after 15 seconds.")
        return False
    except OSError as error:
        print(f"Docker availability probe failed: {type(error).__name__}")
        return False

def check_sandbox_capabilities():
    """
    Verifies that the configured sandbox image contains all mandatory tools.
    Runs the verify-tools.sh script inside the container.
    """
    env_type = os.getenv("ENVIRONMENT", "development").lower()
    sandbox_image_raw = os.getenv("SANDBOX_IMAGE", "")
    
    if not is_docker_available():
        if env_type == "production":
            raise RuntimeError("FATAL: Docker is required in production for sandboxing untrusted execution.")
        print("[WARNING] Docker not found! REAL_SANDBOX_UNAVAILABLE. Capabilities check bypassed.")
        return
        
    if env_type == "production":
        if not sandbox_image_raw:
            raise RuntimeError("FATAL: SANDBOX_IMAGE must be explicitly configured in production.")
        if "@sha256:" not in sandbox_image_raw:
            raise RuntimeError("FATAL: SANDBOX_IMAGE must use an immutable digest (e.g., @sha256:...) in production. Mutable tags are forbidden.")
            
    sandbox_image = sandbox_image_raw or "ghcr.io/udarshcodes/codesentinel-sandbox:latest"
    
    print(f"Checking sandbox capabilities for image: {sandbox_image}...")
    
    # Empty environment for the python subprocess running docker
    safe_env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TMP": os.environ.get("TMP", "/tmp"),
        "TEMP": os.environ.get("TEMP", "/tmp"),
    }
    
    user_arg = "1000:1000"
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        user_arg = f"{os.getuid()}:{os.getgid()}"

    docker_cmd = [
        "docker", "run", "--rm",
        "--memory", "512m",
        "--network", "none",
        "--user", user_arg,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp",
        sandbox_image, "verify-tools.sh"
    ]
    
    try:
        res = subprocess.run(
            docker_cmd,
            env=safe_env,
            capture_output=True,
            timeout=60,
            text=True
        )
        if res.returncode != 0:
            raise RuntimeError(f"FATAL: Sandbox capability verification failed!\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        print("Sandbox capability verification passed successfully.")
    except Exception as e:
        raise RuntimeError(f"FATAL: Failed to verify sandbox capabilities: {e}")

def run_sandboxed_subprocess(
    cmd: list[str],
    cwd: str = None,
    repo_path: str = None,
    timeout: int = 60,
    max_memory_mb: int = 2048,
    max_output_bytes: int = 10 * 1024 * 1024,
    network_disabled: bool = True
) -> Dict[str, Any]:
    """
    Safely executes an untrusted subprocess in a Docker sandbox.
    If Docker is unavailable and ENVIRONMENT is production, fails closed.
    If Docker is unavailable and ENVIRONMENT is not production, warns and falls back to isolated subprocess.
    """
    from tools.auth import is_lease_lost
    if is_lease_lost():
        return {
            "status": "ERROR",
            "stdout": "",
            "stderr": "Worker lease lost!",
            "returncode": -1,
            "error": "Worker lease lost!"
        }

    env_type = os.getenv("ENVIRONMENT", "development").lower()
    sandbox_image_raw = os.getenv("SANDBOX_IMAGE", "")
    
    actual_cwd = repo_path or cwd
    if not actual_cwd:
        raise ValueError("Must provide either cwd or repo_path")

    if not is_docker_available():
        if env_type == "production":
            raise RuntimeError(
                "Docker is required in production for sandboxing untrusted execution. "
                "Failing closed to prevent insecure process-level execution."
            )
        else:
            # Fallback for local development
            print(
                "WARNING: REAL_SANDBOX_UNAVAILABLE. "
                "UNTRUSTED CODE EXECUTION IS RUNNING WITH PROCESS-LEVEL ISOLATION ONLY. "
                "DO NOT USE THIS MODE FOR PRODUCTION."
            )
            # Run the un-sandboxed version but we must adapt it to the new return type interface if it doesn't match
            iso_res = run_isolated_subprocess(
                cmd,
                cwd=actual_cwd,
                timeout=timeout,
                max_output_bytes=max_output_bytes,
                max_memory_mb=max_memory_mb
            )
            # Adapt legacy run_isolated_subprocess dict to new keys if necessary
            if "stdout_truncated" not in iso_res:
                iso_res["stdout_truncated"] = False
                iso_res["stderr_truncated"] = False
                iso_res["container_cleaned"] = True
            return iso_res

    if env_type == "production":
        if not sandbox_image_raw:
            raise RuntimeError("FATAL: SANDBOX_IMAGE must be explicitly configured in production.")
        if "@sha256:" not in sandbox_image_raw:
            raise RuntimeError("FATAL: SANDBOX_IMAGE must use an immutable digest (e.g., @sha256:...) in production. Mutable tags are forbidden.")

    # Construct docker run command
    sandbox_image = sandbox_image_raw or "ghcr.io/udarshcodes/codesentinel-sandbox:latest"
    
    container_id = str(uuid.uuid4())
    container_name = f"codesentinel-sandbox-{container_id}"
    
    user_arg = "1000:1000"
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        user_arg = f"{os.getuid()}:{os.getgid()}"
        
    docker_cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--label", "codesentinel.sandbox=true",
        "--memory", f"{max_memory_mb}m",
        "--pids-limit", "100",
        "--user", user_arg,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp",
        "-e", "HOME=/tmp",
        "-e", "XDG_CACHE_HOME=/tmp/cache",
        "-e", "NPM_CONFIG_CACHE=/tmp/npm",
        "-e", "GOPATH=/tmp/go",
        "-e", "GOCACHE=/tmp/go-cache",
        "-e", "CARGO_HOME=/tmp/cargo",
        "-e", "MAVEN_OPTS=-Duser.home=/tmp",
        "-e", "GRADLE_USER_HOME=/tmp/gradle",
        "-e", "SONAR_USER_HOME=/tmp/sonar",
        "-v", f"{os.path.abspath(actual_cwd)}:/sandbox/repo",
        "-w", "/sandbox/repo"
    ]
    
    runtime = next((value for project, value in sorted(_project_runtimes.items(), key=lambda item: len(item[0]), reverse=True)
                    if os.path.commonpath([project, os.path.realpath(actual_cwd)]) == project), None)
    scanner_modules = {'bandit', 'pylint', 'flake8', 'semgrep'}
    scanner_command = os.path.basename(cmd[0]) in scanner_modules or (len(cmd) > 2 and cmd[1] == '-m' and cmd[2] in scanner_modules)
    if runtime and not scanner_command:
        docker_cmd.extend(['-v', f"{runtime['root']}:/opt/codesentinel/project-python:ro",
                           '-e', 'PATH=/opt/codesentinel/project-python/bin:/opt/codesentinel/venv/bin:/usr/local/go/bin:/opt/rust/bin:/opt/maven/bin:/opt/gradle/bin:/opt/sonar-scanner/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'])
        if os.path.basename(cmd[0]) in {'python', 'python3'}:
            cmd = [runtime['executable']] + cmd[1:]

    for project, packages in _project_dependencies.items():
        try:
            matches = os.path.commonpath([project, os.path.realpath(actual_cwd)]) == project
        except ValueError:
            matches = False
        if matches and not (runtime and scanner_command):
            docker_cmd.extend(["-v", f"{packages}:/opt/codesentinel/project-deps:ro", "-e", "PYTHONPATH=/opt/codesentinel/project-deps"])
            break
    node_modules = _node_dependencies.get(os.path.realpath(actual_cwd))
    if node_modules:
        docker_cmd.extend(["-v", f"{node_modules}:/sandbox/repo/node_modules:ro"])
        docker_cmd.extend(["--tmpfs", "/sandbox/repo/node_modules/.vite-temp:size=128m,mode=1777",
                           "--tmpfs", "/sandbox/repo/node_modules/.vite:size=128m,mode=1777"])
    if network_disabled:
        docker_cmd.extend(["--network", "none"])
        
    docker_cmd.append(sandbox_image)
    docker_cmd.extend(cmd)

    safe_env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TMP": os.environ.get("TMP", "/tmp"),
        "TEMP": os.environ.get("TEMP", "/tmp"),
    }
    
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    
    stdout_truncated = False
    stderr_truncated = False

    def stream_reader(pipe, buf, is_stdout):
        nonlocal stdout_truncated, stderr_truncated
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                
                if len(buf) < max_output_bytes:
                    space_left = max_output_bytes - len(buf)
                    buf.extend(chunk[:space_left])
                    if len(chunk) > space_left:
                        if is_stdout:
                            stdout_truncated = True
                        else:
                            stderr_truncated = True
                else:
                    if is_stdout:
                        stdout_truncated = True
                    else:
                        stderr_truncated = True
        except Exception:
            pass

    status = "ERROR"
    returncode = -2
    container_cleaned = False
    
    try:
        kwargs = {}
        if os.name == 'posix':
            kwargs['start_new_session'] = True
        elif os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            docker_cmd,
            env=safe_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )
        
        t_out = threading.Thread(target=stream_reader, args=(proc.stdout, stdout_buf, True))
        t_err = threading.Thread(target=stream_reader, args=(proc.stderr, stderr_buf, False))
        
        t_out.start()
        t_err.start()
        
        try:
            returncode = proc.wait(timeout=timeout)
            status = "SUCCESS" if returncode == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
            returncode = -1
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
            except Exception:
                pass
            
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)
        
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        
    except Exception as e:
        status = "ERROR"
        stderr_buf.extend(str(e).encode('utf-8'))
        returncode = -2
    finally:
        import time
        for attempt in range(2):
            try:
                cleanup_res = subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if cleanup_res.returncode == 0:
                    container_cleaned = True
                    break
                elif "No such container" in cleanup_res.stderr or "No such container" in cleanup_res.stdout:
                    container_cleaned = True
                    break
            except Exception:
                pass
            
            if attempt == 0:
                time.sleep(0.5)
        
        if not container_cleaned:
            print(f"WARNING: Failed to cleanup sandbox container {container_name}")

    return {
        "status": status,
        "stdout": stdout_buf.decode("utf-8", errors="replace"),
        "stderr": stderr_buf.decode("utf-8", errors="replace"),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "return_code": returncode,
        "returncode": returncode,
        "container_cleaned": container_cleaned,
        "container_name": container_name,
        "docker_cli_reaped": proc.poll() is not None if 'proc' in locals() else False
    }
