import os

def resolve_safe_path(base_dir: str, target_path: str) -> str:
    """
    Safely resolves a target path against a base directory.
    - Prevents directory traversal (../)
    - Prevents absolute path injection
    - Prevents UNC paths and Windows drive escapes
    - Fully resolves symlinks and verifies the final canonical path remains inside base_dir
    
    Raises ValueError if the path escapes the base_dir or is malicious.
    """
    # 1. Reject absolute paths early
    if os.path.isabs(target_path):
        raise ValueError("Absolute paths are not allowed.")
        
    # 2. Reject UNC paths and drive letters (Windows)
    if os.path.splitdrive(target_path)[0]:
        raise ValueError("Drive letters and UNC paths are not allowed.")
        
    base_dir = os.path.abspath(base_dir)
    full_path = os.path.join(base_dir, target_path)
    
    # 3. Canonicalize the path, resolving all symlinks
    canonical_path = os.path.realpath(full_path)
    
    # 4. Verify the canonical path strictly resides inside base_dir
    # Note: Using os.path.commonpath is safer than startswith because it handles path separators correctly.
    try:
        common = os.path.commonpath([base_dir, canonical_path])
    except ValueError:
        # Occurs if paths are on different drives on Windows
        raise ValueError("Path escapes base directory.")
        
    if common != base_dir:
        raise ValueError("Path escapes base directory.")
        
    return canonical_path


def open_safe(base_dir: str, target_path: str, mode: str = "r", **kwargs):
    """
    TOCTOU-aware file opener.
    Resolves the path securely and opens it using O_NOFOLLOW (on POSIX) to minimize the race condition
    where an attacker swaps the file for a symlink between path resolution and opening.
    """
    canonical_path = resolve_safe_path(base_dir, target_path)
    
    if os.name == 'posix':
        # Translate Python string modes to os.O_* flags
        flags = os.O_RDONLY
        if 'w' in mode:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        elif 'a' in mode:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        elif '+' in mode:
            flags = os.O_RDWR
            if 'w' in mode:
                flags |= os.O_CREAT | os.O_TRUNC
                
        # Add O_NOFOLLOW to mitigate TOCTOU symlink swapping
        # Note: getattr used for compatibility if O_NOFOLLOW is missing on some weird platforms
        nofollow_flag = getattr(os, 'O_NOFOLLOW', 0)
        flags |= nofollow_flag
        
        try:
            fd = os.open(canonical_path, flags)
            return open(fd, mode, **kwargs)
        except OSError as e:
            raise ValueError(f"Safe open failed (possible symlink attack/TOCTOU): {e}")
    else:
        # Fallback for Windows
        return open(canonical_path, mode, **kwargs)
