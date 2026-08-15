import os
import subprocess
from typing import Dict, Any

def _set_resource_limits():
    """Apply strict resource limits to the subprocess if supported natively (Linux)."""
    try:
        import resource
        # CPU Limit (soft, hard) in seconds
        resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
        
        # Memory Limit (virtual memory size) in bytes -> 2 GB
        mem_limit = 2 * 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
        
        # Max process count limit (prevent fork bombs)
        resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
        
        # Max file size creation limit -> 50 MB
        fsize_limit = 50 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_limit, fsize_limit))
    except (ImportError, AttributeError, ValueError, OSError):
        # Platform (e.g., Windows) does not support these resource limits
        pass


def run_isolated_subprocess(
    cmd: list[str],
    cwd: str,
    timeout: int = 60,
    max_output_bytes: int = 10 * 1024 * 1024  # 10 MB limit
) -> Dict[str, Any]:
    """
    Safely executes an untrusted subprocess in the target repository.
    - Minimal allowlisted environment (strips CodeSentinel secrets).
    - shell=False enforced.
    - Strict timeouts and output capture size limits.
    - Resource limits applied where supported.
    """
    
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
        preexec_fn = _set_resource_limits if os.name == 'posix' else None

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=isolated_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            preexec_fn=preexec_fn
        )
        
        try:
            # wait for process to finish with timeout
            stdout_data, stderr_data = process.communicate(timeout=timeout)
            
            # Output size limit enforcement
            if len(stdout_data) > max_output_bytes or len(stderr_data) > max_output_bytes:
                return {
                    "status": "FAILED",
                    "stdout": stdout_data[:max_output_bytes].decode('utf-8', errors='replace') + "\n...[TRUNCATED]",
                    "stderr": stderr_data[:max_output_bytes].decode('utf-8', errors='replace') + "\n...[TRUNCATED]",
                    "returncode": process.returncode,
                    "error": "Output size limit exceeded"
                }

            status = "SUCCESS" if process.returncode == 0 else "FAILED"
            return {
                "status": status,
                "stdout": stdout_data.decode('utf-8', errors='replace'),
                "stderr": stderr_data.decode('utf-8', errors='replace'),
                "returncode": process.returncode
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            stdout_data, stderr_data = process.communicate()
            return {
                "status": "TIMEOUT",
                "stdout": stdout_data.decode('utf-8', errors='replace'),
                "stderr": stderr_data.decode('utf-8', errors='replace'),
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
