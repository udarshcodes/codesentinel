import os
import sys
import pytest
from tools.subprocess_runner import run_isolated_subprocess

def test_subprocess_output_abuse(tmpdir):
    script = """
import sys
import time
while True:
    sys.stdout.write("A" * 65536)
    sys.stdout.flush()
    time.sleep(0.01)
"""
    script_path = os.path.join(str(tmpdir), "abuse.py")
    with open(script_path, "w") as f:
        f.write(script)
        
    max_bytes = 1024 * 1024 # 1 MB
    
    result = run_isolated_subprocess(
        cmd=[sys.executable, script_path],
        cwd=str(tmpdir),
        timeout=2,
        max_output_bytes=max_bytes
    )
    
    assert result["status"] in ("TIMEOUT", "FAILED")
    assert len(result["stdout"]) <= max_bytes + 1000 # allow for truncation string
    assert result.get("stdout_truncated") is True
