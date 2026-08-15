import pytest
import os
import tempfile
from tools.safe_path import resolve_safe_path

def test_resolve_safe_path_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        
        resolved = resolve_safe_path(tmpdir, "test.txt")
        assert resolved == os.path.normpath(test_file)

def test_resolve_safe_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="Path escapes base directory"):
            resolve_safe_path(tmpdir, "../outside.txt")

def test_resolve_safe_path_absolute():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="Path escapes base directory|Absolute paths"):
            resolve_safe_path(tmpdir, "/etc/passwd")

def test_resolve_safe_path_symlink_escape():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a directory outside the "repo"
        with tempfile.TemporaryDirectory() as outside_dir:
            secret_file = os.path.join(outside_dir, "secret.txt")
            with open(secret_file, "w") as f:
                f.write("secret")
            
            # Create a symlink inside the "repo" pointing outside
            symlink_path = os.path.join(tmpdir, "link_out")
            try:
                os.symlink(outside_dir, symlink_path)
            except OSError:
                pytest.skip("Symlinks not supported on this OS without admin rights")

            with pytest.raises(ValueError, match="Path escapes base directory"):
                resolve_safe_path(tmpdir, "link_out/secret.txt")
