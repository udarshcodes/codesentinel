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


def open_repo_file_at(base_dir: str, target_path: str, mode: str = "r", **kwargs):
    """
    Race-resistant file opener using directory file descriptors (openat).
    """
    import stat
    if os.path.isabs(target_path):
        raise ValueError("Absolute paths are not allowed.")
    if os.path.splitdrive(target_path)[0]:
        raise ValueError("Drive letters and UNC paths are not allowed.")
        
    base_dir = os.path.abspath(base_dir)
    rel_path = os.path.normpath(target_path)
    
    if rel_path.startswith("..") or rel_path == "..":
        raise ValueError("Path escapes base directory.")
        
    if os.name == 'posix':
        parts = []
        if rel_path and rel_path != ".":
            parts = rel_path.split(os.sep)
            
        current_fd = None
        try:
            # Open base directory securely
            current_fd = os.open(base_dir, os.O_RDONLY | os.O_DIRECTORY)
            
            for i, part in enumerate(parts):
                if part in ("", "."):
                    continue
                if part == "..":
                    raise ValueError("Path traversal attempted.")
                    
                flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                if i < len(parts) - 1:
                    # Intermediate component must be a directory
                    flags |= os.O_DIRECTORY
                else:
                    # Final component might be opened with different modes
                    if 'w' in mode:
                        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
                    elif 'a' in mode:
                        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0)
                    elif '+' in mode:
                        flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
                        if 'w' in mode:
                            flags |= os.O_CREAT | os.O_TRUNC
                
                next_fd = os.open(part, flags, dir_fd=current_fd)
                
                # Verify it's not a symlink (O_NOFOLLOW on FreeBSD/macOS for directories can be inconsistent, so we double-check)
                st = os.fstat(next_fd)
                if stat.S_ISLNK(st.st_mode):
                    os.close(next_fd)
                    raise ValueError(f"Symlinks are not allowed: {part}")
                if i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
                    os.close(next_fd)
                    raise ValueError(f"Not a directory: {part}")
                if i == len(parts) - 1 and not stat.S_ISREG(st.st_mode):
                    os.close(next_fd)
                    raise ValueError(f"Special files are not allowed: {part}")
                
                os.close(current_fd)
                current_fd = next_fd
                
            return open(current_fd, mode, **kwargs)
        except Exception as e:
            if current_fd is not None:
                try:
                    os.close(current_fd)
                except OSError:
                    pass
            raise ValueError(f"Safe open failed (possible symlink attack/TOCTOU): {e}")
    else:
        # Fallback for Windows
        canonical_path = resolve_safe_path(base_dir, target_path)
        st = os.lstat(canonical_path)
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"Symlinks are not allowed: {target_path}")
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"Special files are not allowed: {target_path}")
        return open(canonical_path, mode, **kwargs)


def open_safe(base_dir: str, target_path: str, mode: str = "r", **kwargs):
    """
    TOCTOU-aware file opener.
    Uses directory descriptor traversal (openat) on POSIX to prevent concurrent
    symlink replacement attacks.
    """
    return open_repo_file_at(base_dir, target_path, mode=mode, **kwargs)
