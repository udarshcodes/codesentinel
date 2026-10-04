import os
import tempfile
import stat
import pytest
from tools.safe_repo import safe_read_text, safe_walk

def test_symlink_regression(tmp_path):
    """
    Ensures safe_read_text and safe_walk explicitly reject and skip symlinks.
    """
    repo_root = str(tmp_path)
    
    # Create normal file
    normal_file = os.path.join(repo_root, "normal.txt")
    with open(normal_file, "w") as f:
        f.write("safe content")
        
    # Create target for symlink (outside repo, simulating /etc/passwd)
    outside_dir = tempfile.mkdtemp()
    target_file = os.path.join(outside_dir, "secret.txt")
    with open(target_file, "w") as f:
        f.write("secret content")
        
    # Create symlink in repo
    symlink_file = os.path.join(repo_root, "link.txt")
    try:
        os.symlink(target_file, symlink_file)
    except OSError:
        pytest.skip("Symlinks not supported on this OS/filesystem without elevation")
        
    # Test safe_read_text blocks reading the symlink
    with pytest.raises(ValueError, match="Symlinks are not allowed"):
        safe_read_text(repo_root, "link.txt")
        
    # Test safe_walk skips the symlink
    files_found = []
    symlinks_found = []
    for root, dirs, files, syms in safe_walk(repo_root):
        files_found.extend(files)
        symlinks_found.extend(syms)
        
    assert "normal.txt" in files_found
    assert "link.txt" not in files_found
    assert os.path.join(repo_root, "link.txt") in symlinks_found
