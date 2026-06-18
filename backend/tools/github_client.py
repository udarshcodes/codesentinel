import os
from github import Github
import subprocess
from datetime import datetime
import time
import shutil

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
    
    # Configure git and checkout branch
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=local_path, check=True, timeout=30)
    subprocess.run(["git", "config", "user.name", "CodeSentinel AI"], cwd=local_path, check=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "codesentinel@ai.local"], cwd=local_path, check=True, timeout=10)
    
    # Clean up temp
    for junk in ["temp.patch", ".pytest_cache"]:
        junk_path = os.path.join(local_path, junk)
        if os.path.exists(junk_path):
            if os.path.isdir(junk_path):
                shutil.rmtree(junk_path, ignore_errors=True)
            else:
                os.remove(junk_path)
                
    for root, dirs, files in os.walk(local_path):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                
    return {
        "is_owner": is_owner,
        "push_repo_url": push_repo_url,
        "branch_name": branch_name,
        "repo_name": repo_name,
        "user_login": user.login
    }

def commit_and_push(local_path: str, branch_name: str, message: str, push_repo_url: str, token: str, files: list) -> bool:
    """Commits and pushes."""
    if not files:
        return False
    for f in files:
        if os.path.exists(os.path.join(local_path, f)):
            try:
                subprocess.run(["git", "add", f], cwd=local_path, check=True, timeout=30)
            except subprocess.CalledProcessError as e:
                print(f"Failed to add file {f}: {e}")
        else:
            print(f"File {f} does not exist, skipping add.")
            
    status = subprocess.run(["git", "status", "--porcelain"], cwd=local_path, capture_output=True, text=True, timeout=30)
    if not status.stdout.strip():
        return False
        
    subprocess.run(["git", "commit", "--no-verify", "-m", message], cwd=local_path, check=True, timeout=30)
    
    import base64
    b64_token = base64.b64encode(f"oauth2:{token}".encode()).decode()
    
    subprocess.run(["git", "remote", "add", "auth_origin", push_repo_url], cwd=local_path, capture_output=True, timeout=10)
    subprocess.run(["git", "remote", "set-url", "auth_origin", push_repo_url], cwd=local_path, capture_output=True, timeout=10)
    subprocess.run(["git", "config", "http.https://github.com/.extraheader", f"AUTHORIZATION: basic {b64_token}"], cwd=local_path, check=True, timeout=10)
    subprocess.run(["git", "push", "-u", "auth_origin", branch_name], cwd=local_path, check=True, timeout=120)
    return True

def open_pull_request(repo_name: str, branch_name: str, title: str, body: str, token: str, is_owner: bool, user_login: str) -> str:
    g = Github(token)
    try:
        source_repo = g.get_repo(repo_name)
        base = "main"
        try:
            source_repo.get_branch("main")
        except Exception:
            base = "master"
            
        head_ref = branch_name if is_owner else f"{user_login}:{branch_name}"
        
        pr = source_repo.create_pull(
            title=title,
            body=body,
            head=head_ref,
            base=base
        )
        return pr.html_url
    except Exception as e:
        print(f"Error opening PR: {e}")
        return ""
