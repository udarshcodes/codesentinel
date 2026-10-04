import os
import time
import shutil
import tempfile
import threading
import pytest
from tools.safe_repo import safe_read_text

@pytest.fixture
def toctou_env():
    temp_base = tempfile.mkdtemp(prefix="toctou_test_")
    repo_dir = os.path.join(temp_base, "repo")
    os.makedirs(repo_dir)
    
    safe_dir = os.path.join(repo_dir, "safe")
    os.makedirs(safe_dir)
    
    target_file = os.path.join(safe_dir, "target.txt")
    with open(target_file, "w") as f:
        f.write("SAFE_CONTENT")
        
    host_dir = os.path.join(temp_base, "host")
    os.makedirs(host_dir)
    canary_file = os.path.join(host_dir, "target.txt")
    with open(canary_file, "w") as f:
        f.write("SUPER_SECRET_HOST_DATA")
        
    yield {
        "base": temp_base,
        "repo": repo_dir,
        "safe_dir": safe_dir,
        "target": target_file,
        "host_canary": canary_file
    }
    shutil.rmtree(temp_base, ignore_errors=True)

@pytest.mark.skipif(os.name == "nt", reason="TOCTOU mitigation uses openat, which is POSIX-only. Windows falls back to realpath validation.")
def test_toctou_symlink_swap(toctou_env):
    repo = toctou_env["repo"]
    safe_dir = toctou_env["safe_dir"]
    host_canary = toctou_env["host_canary"]
    
    stop_flag = False
    
    def attacker():
        # Rapidly swap safe_dir with a symlink to host_dir and back
        host_dir = os.path.dirname(host_canary)
        temp_symlink = os.path.join(repo, "temp_symlink")
        os.symlink(host_dir, temp_symlink)
        
        while not stop_flag:
            try:
                # Rename is atomic on POSIX, swapping the directory for a symlink
                os.rename(temp_symlink, safe_dir)
                # Now it's a symlink, swap it back to a directory
                os.unlink(safe_dir)
                os.makedirs(safe_dir)
                with open(os.path.join(safe_dir, "target.txt"), "w") as f:
                    f.write("SAFE_CONTENT")
                os.symlink(host_dir, temp_symlink)
            except OSError:
                pass

    t = threading.Thread(target=attacker)
    t.start()
    
    reads_attempted = 0
    canary_reads = 0
    
    try:
        # Run for 2 seconds to try to hit the race condition
        end_time = time.time() + 2.0
        while time.time() < end_time:
            reads_attempted += 1
            try:
                content = safe_read_text(repo, "safe/target.txt")
                if "SUPER_SECRET_HOST_DATA" in content:
                    canary_reads += 1
            except ValueError:
                # Safe failure (symlink detected or file not found during swap)
                pass
            except OSError:
                # Safe failure (file missing during swap)
                pass
    finally:
        stop_flag = True
        t.join()
        
    assert canary_reads == 0, f"TOCTOU vulnerability detected: Canary read {canary_reads} times out of {reads_attempted} attempts!"
    print(f"\nTOCTOU race attempts: {reads_attempted}, successful safe reads/failures, 0 canary reads.")
