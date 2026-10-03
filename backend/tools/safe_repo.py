import os
import stat
from tools.safe_path import resolve_safe_path, open_safe

def check_no_symlinks(repo_root: str, target_path: str):
    """
    Validates that the target path (relative or absolute, but must be within repo_root) 
    contains no symlinks in any component relative to the repository root.
    """
    repo_root = os.path.abspath(repo_root)
    if os.path.isabs(target_path):
        rel_path = os.path.relpath(target_path, repo_root)
        if rel_path.startswith(".."):
            raise ValueError(f"Path escapes repository root: {target_path}")
    else:
        rel_path = target_path
    
    parts = rel_path.split(os.sep)
    current = repo_root
    for part in parts:
        if part in ("", ".", ".."):
            continue
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
            if stat.S_ISLNK(st.st_mode):
                raise ValueError(f"Symlinks are not allowed during analysis: {current}")
            if not stat.S_ISDIR(st.st_mode) and not stat.S_ISREG(st.st_mode):
                raise ValueError(f"Special files are not allowed during analysis: {current}")
        except FileNotFoundError:
            # If a component doesn't exist, it can't be a symlink yet.
            pass

def safe_walk(repo_root: str, topdown=True, onerror=None):
    """
    A safe replacement for os.walk that explicitly strips symlink directories in-place 
    and yields only regular files that are not symlinks.
    Yields (root, safe_dirs, safe_files, symlink_paths).
    
    NOTE: This is NOT the security boundary for preventing concurrent TOCTOU race
    conditions. It only discovers paths. Any read MUST use open_safe or safe_read_text.
    """
    for root, dirs, files in os.walk(repo_root, topdown=topdown, onerror=onerror, followlinks=False):
        safe_dirs = []
        symlinks = []
        for d in dirs:
            if d == ".git":
                continue
            full_d = os.path.join(root, d)
            try:
                st = os.lstat(full_d)
                if stat.S_ISLNK(st.st_mode):
                    symlinks.append(full_d)
                elif stat.S_ISDIR(st.st_mode):
                    safe_dirs.append(d)
            except OSError:
                pass
        
        # Modify dirs in-place to prevent os.walk from entering symlink directories
        dirs[:] = safe_dirs
        
        safe_files = []
        for f in files:
            full_f = os.path.join(root, f)
            try:
                st = os.lstat(full_f)
                if stat.S_ISLNK(st.st_mode):
                    symlinks.append(full_f)
                elif stat.S_ISREG(st.st_mode):
                    safe_files.append(f)
            except OSError:
                pass
                
        yield root, safe_dirs, safe_files, symlinks

def safe_read_text(repo_root: str, target_path: str, encoding="utf-8", errors="strict", max_bytes=None) -> str:
    """
    Reads a file securely, explicitly rejecting any symlink in the path.
    """
    check_no_symlinks(repo_root, target_path)
    
    if not os.path.isabs(target_path):
        target_path = os.path.join(repo_root, target_path)
        
    rel_path = os.path.relpath(target_path, os.path.abspath(repo_root))
    if rel_path.startswith(".."):
        raise ValueError(f"Path escapes repository root: {target_path}")
    
    # Delegate to the lower-level TOCTOU mitigation
    with open_safe(repo_root, rel_path, mode="r", encoding=encoding, errors=errors) as f:
        if max_bytes is not None:
            return f.read(max_bytes)
        return f.read()

def safe_path_exists(repo_root: str, target_path: str) -> bool:
    """
    Checks if a safe path exists, ensuring it contains no symlinks.
    """
    try:
        check_no_symlinks(repo_root, target_path)
        
        if not os.path.isabs(target_path):
            target_path = os.path.join(repo_root, target_path)
            
        rel_path = os.path.relpath(target_path, os.path.abspath(repo_root))
        if rel_path.startswith(".."):
            return False
            
        canonical_target = resolve_safe_path(repo_root, rel_path)
        return os.path.exists(canonical_target)
    except (ValueError, OSError):
        return False
