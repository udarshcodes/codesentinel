import ast
import os
import pytest

def test_no_raw_open_in_static_analysis():
    """
    Ensures that static_analysis.py does not contain any raw open() calls,
    preventing regressions that bypass the symlink-resistant safe file reader.
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(backend_dir, "agents", "static_analysis.py")
    
    assert os.path.exists(target_file), f"Could not find {target_file}"
    
    with open(target_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=target_file)
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                # Ensure it's not some class method or something
                pytest.fail(f"Found raw open() call at line {node.lineno} in static_analysis.py. "
                            f"All repository file reads must use safe_read_text to prevent symlink traversal.")
                            
def test_no_os_walk_in_static_analysis():
    """
    Ensures that static_analysis.py uses safe_walk() instead of os.walk().
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_file = os.path.join(backend_dir, "agents", "static_analysis.py")
    
    with open(target_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=target_file)
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "walk":
                    pytest.fail(f"Found os.walk() call at line {node.lineno} in static_analysis.py. "
                                f"All directory traversal must use safe_walk() to prevent symlink traversal.")
