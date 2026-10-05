import os
import subprocess
from typing import Dict, Any


def get_safe_env(keep_github_token: bool = False) -> Dict[str, str]:
    """Returns a sanitized environment stripped of sensitive credentials."""
    env = os.environ.copy()
    secrets = [
        "GROQ_API_KEY", "WORKER_WEBHOOK_SECRET", 
        "ADMIN_SECRET", "GIT_ASKPASS", "SSH_AUTH_SOCK"
    ]
    if not keep_github_token:
        secrets.extend(["GITHUB_TOKEN", "GH_TOKEN", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_KEY_0", "GIT_CONFIG_COUNT"])
    
    for key in list(env.keys()):
        if any(key == s or key.startswith(s + "_") or (key.startswith(s) and s == "GROQ_API_KEY") for s in secrets):
            env.pop(key, None)
            
    if not keep_github_token:
        env.pop("HOME", None)
        env.pop("USERPROFILE", None)

    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def clone_github_repo(repo_url: str, target_dir: str, github_token: str = "") -> None:
    """
    Safely clones a GitHub repository, supporting both public and private repositories.
    If a token is provided, it attempts authenticated cloning first. If that fails (e.g., token 
    lacks access to a public repo), it safely falls back to unauthenticated cloning.
    If both fail, it raises the authenticated error to avoid masking permission problems.
    """
    clone_env = get_safe_env(keep_github_token=False)
    clone_env["GIT_TERMINAL_PROMPT"] = "0"
    clone_env["GIT_ASKPASS"] = "echo"
    clone_env["GCM_INTERACTIVE"] = "false"
    
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout", repo_url, target_dir]
    
    try:
        if github_token and repo_url.startswith("https://github.com/"):
            auth_clone_env = clone_env.copy()
            auth_clone_env["GIT_CONFIG_COUNT"] = "1"
            auth_clone_env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            auth_clone_env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {github_token}"
            
            try:
                subprocess.run(cmd, check=True, timeout=300, env=auth_clone_env, capture_output=True, text=True)
                return
            except subprocess.CalledProcessError as e:
                auth_err = e
                # Fall back to unauthenticated clone. If it succeeds, the repo was public.
                # If it fails, raise the original auth_err to show true permission failure.
                try:
                    subprocess.run(cmd, check=True, timeout=300, env=clone_env, capture_output=True, text=True)
                    return
                except subprocess.CalledProcessError:
                    raise auth_err
        else:
            subprocess.run(cmd, check=True, timeout=300, env=clone_env, capture_output=True, text=True)
            
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or e.stdout or str(e)
        if github_token:
            err_msg = err_msg.replace(github_token, "***")
        raise RuntimeError(f"Git clone failed (exit code {e.returncode}): {err_msg}")


def run_isolated_subprocess(
    cmd: list[str],
    cwd: str,
    timeout: int = 60,
    max_output_bytes: int = 10 * 1024 * 1024,  # 10 MB limit
    max_memory_mb: int = 2048
) -> Dict[str, Any]:
    """
    Safely executes an untrusted subprocess in the target repository.
    - Minimal allowlisted environment (strips CodeSentinel secrets).
    - shell=False enforced.
    - Strict timeouts and output capture size limits.
    - Resource limits applied where supported.
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
    
    # 1. Minimal Allowlisted Environment
    allowed_env_keys = {
        "PATH", "LANG", "LC_ALL", "USER", "USERNAME", "TMP", "TEMP", "TMPDIR"
    }
    
    isolated_env = {}
    for k in allowed_env_keys:
        if k in os.environ:
            isolated_env[k] = os.environ[k]
            
    # Force non-interactive modes
    isolated_env["CI"] = "true"
    isolated_env["GIT_TERMINAL_PROMPT"] = "0"
    isolated_env["DEBIAN_FRONTEND"] = "noninteractive"
    isolated_env["PYTHONUNBUFFERED"] = "1"
    
    # Ensure local node_modules/.bin is in path
    isolated_env["PATH"] = os.path.join(cwd, "node_modules", ".bin") + os.pathsep + isolated_env.get("PATH", "")
    
    # Ensure HOME / USERPROFILE is explicitly NOT passed or pointed to a safe empty dir
    # to prevent reading ~/.gitconfig, ~/.ssh, ~/.npmrc etc.
    if "HOME" in isolated_env:
        del isolated_env["HOME"]
    if "USERPROFILE" in isolated_env:
        del isolated_env["USERPROFILE"]
        
    try:
        # Preexec_fn is only supported on POSIX systems
        if os.name == 'posix':
            def preexec_fn():
                os.setsid()
                try:
                    import resource
                    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
                    mem_limit = max_memory_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
                    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
                    fsize_limit = 50 * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_limit, fsize_limit))
                except (ImportError, AttributeError, ValueError, OSError):
                    pass
            creationflags = 0
        else:
            preexec_fn = None
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=isolated_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            preexec_fn=preexec_fn,
            creationflags=creationflags
        )
        
        out_dict = {}
        import threading
        
        def _stream_reader(stream, max_bytes, out_dict, key):
            data = bytearray()
            truncated = False
            try:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    if len(data) + len(chunk) > max_bytes:
                        data.extend(chunk[:max_bytes - len(data)])
                        truncated = True
                        break
                    data.extend(chunk)
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
            out_dict[key] = bytes(data)
            out_dict[key + "_truncated"] = truncated

        t_out = threading.Thread(target=_stream_reader, args=(process.stdout, max_output_bytes, out_dict, "stdout"))
        t_err = threading.Thread(target=_stream_reader, args=(process.stderr, max_output_bytes, out_dict, "stderr"))
        t_out.start()
        t_err.start()
        
        try:
            process.wait(timeout=timeout)
            t_out.join()
            t_err.join()
            
            stdout_data = out_dict.get("stdout", b"")
            stderr_data = out_dict.get("stderr", b"")
            
            status = "SUCCESS" if process.returncode == 0 else "FAILED"
            
            stdout_str = stdout_data.decode('utf-8', errors='replace')
            stderr_str = stderr_data.decode('utf-8', errors='replace')
            
            if out_dict.get("stdout_truncated"):
                stdout_str += "\n...[TRUNCATED]"
            if out_dict.get("stderr_truncated"):
                stderr_str += "\n...[TRUNCATED]"

            return {
                "status": status,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "stdout_truncated": out_dict.get("stdout_truncated", False),
                "stderr_truncated": out_dict.get("stderr_truncated", False),
                "returncode": process.returncode
            }
            
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
            elif os.name == 'posix':
                import signal
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except OSError:
                    process.kill()
            else:
                process.kill()
            
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            
            t_out.join()
            t_err.join()
            
            stdout_data = out_dict.get("stdout", b"")
            stderr_data = out_dict.get("stderr", b"")
            
            stdout_str = stdout_data.decode('utf-8', errors='replace')
            stderr_str = stderr_data.decode('utf-8', errors='replace')
            
            if out_dict.get("stdout_truncated"):
                stdout_str += "\n...[TRUNCATED]"
            if out_dict.get("stderr_truncated"):
                stderr_str += "\n...[TRUNCATED]"
                
            return {
                "status": "TIMEOUT",
                "stdout": stdout_str,
                "stderr": stderr_str,
                "stdout_truncated": out_dict.get("stdout_truncated", False),
                "stderr_truncated": out_dict.get("stderr_truncated", False),
                "returncode": -1,
                "error": f"Command timed out after {timeout} seconds"
            }
            
    except FileNotFoundError as e:
        return {
            "status": "UNAVAILABLE",
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "error": "Executable not found"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "error": "Execution error"
        }
