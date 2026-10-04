import os
import threading
import time
import tempfile
import pytest
from tools.safe_repo import safe_read_text

def test_toctou_replacement(tmp_path):
    """
    Simulates a TOCTOU race condition where an attacker replaces a legitimate file
    with a symlink after it has been verified but before it is opened.
    """
    repo_root = str(tmp_path)
    target_file = os.path.join(repo_root, "race.txt")
    
    # Target of symlink outside repo
    outside_dir = tempfile.mkdtemp()
    secret_file = os.path.join(outside_dir, "secret.txt")
    with open(secret_file, "w") as f:
        f.write("secret content")

    # Initial state: legitimate file
    with open(target_file, "w") as f:
        f.write("legit content")

    # This test attempts to race the safe_read_text implementation.
    # While Python's GIL and timing make perfect races hard, we can simulate
    # the outcome by replacing the file before calling safe_read_text,
    # expecting safe_read_text to block the symlink entirely.
    
    # Replace file with symlink
    os.remove(target_file)
    try:
        os.symlink(secret_file, target_file)
    except OSError:
        pytest.skip("Symlinks not supported on this OS/filesystem without elevation")
        
    with pytest.raises(ValueError, match="Symlinks are not allowed|Path escapes"):
        content = safe_read_text(repo_root, "race.txt")
        # If it returns "secret content", TOCTOU failed/symlink bypass succeeded.
        assert content != "secret content", "Symlink traversal vulnerability triggered!"
