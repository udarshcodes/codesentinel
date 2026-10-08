import os
from github import Github
import subprocess
from datetime import datetime
import time
import shutil
import tempfile
import threading
import secrets
import requests

_trusted_workspaces = {}
_trusted_lock = threading.Lock()

def register_trusted_workspace(path: str, repo_url: str, commit_sha: str) -> str:
    token = secrets.token_urlsafe(32)
    # Ensure the path is strictly inside the trusted root
    temp_base = os.getenv("TEMP_REPO_PATH", "/tmp/repos")
    temp_base_real = os.path.realpath(temp_base)
    path = os.path.realpath(path)
    
    try:
        common = os.path.commonpath([temp_base_real, path])
        if common != temp_base_real:
            raise ValueError("Cannot register workspace outside trusted root")
    except ValueError:
        raise ValueError("Cannot register workspace outside trusted root (different drive)")
        
    with _trusted_lock:
        _trusted_workspaces[path] = {
            "token": token,
            "repo_url": repo_url,
            "commit_sha": commit_sha
        }
    return token

def verify_trusted_workspace(path: str, token: str) -> bool:
    path = os.path.realpath(path)
    with _trusted_lock:
        expected = _trusted_workspaces.get(path)
    if not expected:
        return False
    if not secrets.compare_digest(expected["token"], token):
        return False
        
    from tools.subprocess_runner import get_safe_env
    safe_env = get_safe_env(keep_github_token=False)
    try:
        remote_out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=path, capture_output=True, text=True, check=True, env=safe_env).stdout.strip()
        if remote_out != expected["repo_url"]:
            return False
            
        if expected["commit_sha"]:
            merge_base = subprocess.run(["git", "merge-base", expected["commit_sha"], "HEAD"], cwd=path, capture_output=True, text=True, check=True, env=safe_env).stdout.strip()
            if merge_base != expected["commit_sha"]:
                return False
    except Exception:
        return False
        
    return True

def create_trusted_pr_workspace(repo_url: str, token: str, commit_sha: str = "") -> str:
    """Creates a fresh, trusted workspace isolated from any untrusted repository metadata."""
    temp_base = os.getenv("TEMP_REPO_PATH", "/tmp/repos")
    os.makedirs(temp_base, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="codesentinel_trusted_", dir=temp_base)
    
    from tools.subprocess_runner import get_safe_env
    clone_env = get_safe_env(keep_github_token=True)
    clone_env["GIT_TERMINAL_PROMPT"] = "0"
    clone_env["GIT_ASKPASS"] = "echo"
    clone_env["GCM_INTERACTIVE"] = "false"
    
    try:
        if token and repo_url.startswith("https://github.com/"):
            clone_env["GIT_CONFIG_COUNT"] = "1"
            clone_env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            clone_env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {token}"
            try:
                subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout", repo_url, temp_dir], check=True, timeout=300, env=clone_env, capture_output=True, text=True)
            except subprocess.CalledProcessError as clone_err:
                # If authentication failed, check if the repo is public before falling back
                err_text = (clone_err.stderr or "").lower()
                if "authentication failed" in err_text or "invalid credentials" in err_text or "not found" in err_text:
                    import requests
                    parts = repo_url.rstrip("/").split("/")
                    if len(parts) >= 2:
                        owner = parts[-2]
                        repo = parts[-1]
                        if repo.endswith(".git"):
                            repo = repo[:-4]
                        try:
                            resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", timeout=10)
                            if resp.status_code == 200 and not resp.json().get("private", True):
                                # Public repository, fallback to unauthenticated clone
                                subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout", repo_url, temp_dir], check=True, timeout=300, env=get_safe_env(keep_github_token=False), capture_output=True, text=True)
                                clone_err = None
                        except Exception:
                            pass
                if clone_err is not None:
                    raise clone_err
        else:
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--no-checkout", repo_url, temp_dir], check=True, timeout=300, env=clone_env, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if token:
            err_msg = err_msg.replace(token, "***")
        raise RuntimeError(f"Clone failed: {err_msg}")
        
    safe_env = get_safe_env(keep_github_token=False)
    
    # Neutralize hooks explicitly
    subprocess.run(["git", "config", "core.hooksPath", "/dev/null"], cwd=temp_dir, check=True, env=safe_env)
    
    if commit_sha:
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "checkout", commit_sha], cwd=temp_dir, check=True, env=safe_env)
    else:
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "checkout"], cwd=temp_dir, check=True, env=safe_env)
        
    # Mark it securely
    trusted_token = register_trusted_workspace(temp_dir, repo_url, commit_sha)
    with open(os.path.join(temp_dir, ".codesentinel_trusted_workspace"), "w") as f:
        f.write(trusted_token)
        
    return temp_dir



def prepare_repo_for_push(repo_url: str, local_path: str, token: str) -> dict:
    """Forks repo if needed, checks out branch."""
    g = Github(token)
    parts = repo_url.split("github.com/")[-1].split("/")
    repo_name = f"{parts[0]}/{parts[1].removesuffix('.git')}"

    source_repo = g.get_repo(repo_name)
    user = g.get_user()
    is_owner = source_repo.owner.login == user.login

    if is_owner:
        push_repo_url = repo_url
    else:
        target_repo = user.create_fork(source_repo)
        push_repo_url = target_repo.clone_url
        time.sleep(3)

    branch_name = f"agent/fix-{int(datetime.now().timestamp())}"

    from tools.subprocess_runner import get_safe_env
    safe_env = get_safe_env(keep_github_token=False)
    
    # Configure git and checkout branch
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "checkout", "-b", branch_name], cwd=local_path, check=True, timeout=30, env=safe_env
    )
    subprocess.run(
        ["git", "config", "user.name", "CodeSentinel AI"],
        cwd=local_path,
        check=True,
        timeout=10,
        env=safe_env
    )
    subprocess.run(
        ["git", "config", "user.email", "codesentinel@ai.local"],
        cwd=local_path,
        check=True,
        timeout=10,
        env=safe_env
    )

    # Clean up temp
    for junk in ["temp.patch", ".pytest_cache"]:
        junk_path = os.path.join(local_path, junk)
        if os.path.exists(junk_path):
            if os.path.isdir(junk_path):
                shutil.rmtree(junk_path, ignore_errors=True)
            else:
                os.remove(junk_path)

    from config import IGNORED_DIRS

    for root, dirs, _ in os.walk(local_path):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

    return {
        "is_owner": is_owner,
        "push_repo_url": push_repo_url,
        "branch_name": branch_name,
        "repo_name": repo_name,
        "user_login": user.login,
    }


def commit_and_push(
    local_path: str,
    branch_name: str,
    message: str,
    push_repo_url: str,
    token: str,
    files: list,
) -> bool:
    """Commits and pushes."""
    from tools.subprocess_runner import get_safe_env
    safe_env = get_safe_env(keep_github_token=False)
    
    marker_path = os.path.join(local_path, ".codesentinel_trusted_workspace")
    if not os.path.exists(marker_path):
        raise ValueError("Security Violation: Attempted to run trusted git operations on untrusted workspace!")
        
    with open(marker_path, "r") as f:
        actual_token = f.read().strip()
        
    if not verify_trusted_workspace(local_path, actual_token):
        raise ValueError("Security Violation: Trusted workspace authenticity could not be verified!")
        
    if not files:
        return False
    for f in files:
        if os.path.exists(os.path.join(local_path, f)):
            try:
                subprocess.run(
                    ["git", "-c", "core.hooksPath=/dev/null", "add", f], cwd=local_path, check=True, timeout=30, env=safe_env
                )
            except subprocess.CalledProcessError as e:
                print(f"Failed to add file {f}: {e}")
        else:
            print(f"File {f} does not exist, skipping add.")

    diff_status = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "diff", "--cached", "--quiet"],
        cwd=local_path,
        timeout=30,
        env=safe_env
    )
    if diff_status.returncode == 0:
        return False

    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", message],
        cwd=local_path,
        check=True,
        timeout=30,
        env=safe_env
    )

    try:
        push_env = get_safe_env(keep_github_token=True)
        askpass_path = None
        if token and push_repo_url.startswith("https://github.com/"):
            import tempfile
            import sys
            ext = ".bat" if sys.platform == "win32" else ".sh"
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                askpass_path = f.name
                if sys.platform == "win32":
                    f.write("@echo off\necho %CODESENTINEL_GIT_TOKEN%\n")
                else:
                    f.write("#!/bin/sh\necho $CODESENTINEL_GIT_TOKEN\n")
            
            if sys.platform != "win32":
                os.chmod(askpass_path, 0o700)
                
            push_env["GIT_ASKPASS"] = askpass_path
            push_env["GIT_TERMINAL_PROMPT"] = "0"
            push_env["CODESENTINEL_GIT_TOKEN"] = token
            
            try:
                subprocess.run(
                    ["git", "-c", "core.hooksPath=/dev/null", "push", "-u", push_repo_url, branch_name],
                    cwd=local_path,
                    check=True,
                    timeout=120,
                    capture_output=True,
                    text=True,
                    env=push_env
                )
            finally:
                if askpass_path and os.path.exists(askpass_path):
                    os.remove(askpass_path)
        else:
            subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "push", "-u", push_repo_url, branch_name],
                cwd=local_path,
                check=True,
                timeout=120,
                capture_output=True,
                text=True,
                env=push_env
            )
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr or str(e)
        if token:
            err_msg = err_msg.replace(token, "***")
        raise RuntimeError(f"Failed to push branch to GitHub: {err_msg}")
    return True


def open_pull_request(
    repo_name: str,
    branch_name: str,
    title: str,
    body: str,
    token: str,
    is_owner: bool,
    user_login: str,
    is_draft: bool = False,
) -> str:
    g = Github(token)
    try:
        source_repo = g.get_repo(repo_name)
        base = "main"
        try:
            source_repo.get_branch("main")
        except Exception as e:
            print(f"Warning: Branch 'main' not found, falling back to 'master'. Error: {e}")
            base = "master"

        head_ref = branch_name if is_owner else f"{user_login}:{branch_name}"

        pr = source_repo.create_pull(
            title=title, body=body, head=head_ref, base=base, draft=is_draft
        )
        return pr.html_url
    except Exception as e:
        err_msg = str(e)
        if token:
            err_msg = err_msg.replace(token, "***")
        raise RuntimeError(f"Failed to create pull request: {err_msg}")

def check_token_permissions(repo_url: str, token: str):
    """Safely verify that the supplied token can access the target repository."""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return
    owner = parts[-2]
    repo = parts[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=10)
    
    if resp.status_code == 404 or resp.status_code == 401 or resp.status_code == 403:
        raise RuntimeError("GitHub token does not have sufficient permission to create a pull request in the target repository.")
    
    if resp.status_code == 200:
        repo_data = resp.json()
        perms = repo_data.get("permissions", {})
        
        user_resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if user_resp.status_code == 200:
            user_data = user_resp.json()
            if repo_data.get("owner", {}).get("login") == user_data.get("login"):
                if not perms.get("push"):
                    raise RuntimeError("GitHub token does not have write permission to the target repository.")

