import subprocess
import os

def apply_patch(diff_content: str, repo_local_path: str) -> dict:
    """
    Validates and applies a unified diff using the system patch command.
    Returns: {"success": bool, "stderr": str}
    """
    if not diff_content:
        return {"success": False, "stderr": "Diff content is empty."}
        
    # Strict validation of unified diff format
    if "---" not in diff_content or "+++" not in diff_content or "@@" not in diff_content:
        return {"success": False, "stderr": "Invalid diff format. Missing ---, +++, or @@ markers."}
        
    try:
        # Save diff to a temporary file
        patch_file = os.path.join(repo_local_path, "temp_fix.patch")
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(diff_content)
            
        # Run patch command
        result = subprocess.run(
            ["patch", "-p1", "-i", "temp_fix.patch"],
            cwd=repo_local_path,
            capture_output=True,
            text=True
        )
        
        # Clean up
        if os.path.exists(patch_file):
            os.remove(patch_file)
            
        if result.returncode == 0:
            return {"success": True, "stderr": ""}
        else:
            return {"success": False, "stderr": result.stderr or result.stdout or "Unknown patch error."}
            
    except Exception as e:
        return {"success": False, "stderr": str(e)}
