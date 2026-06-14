import os

def apply_patch(diff_content: str, repo_local_path: str, target_file: str) -> dict:
    """
    Parses <<<SEARCH>>> and <<<REPLACE>>> blocks from diff_content and applies
    them to target_file in repo_local_path.
    Returns: {"success": bool, "stderr": str}
    """
    if not diff_content:
        return {"success": False, "stderr": "Diff content is empty."}
        
    full_path = os.path.join(repo_local_path, target_file)
    if not os.path.exists(full_path):
        return {"success": False, "stderr": f"File not found: {target_file}"}
        
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Very basic parse for <<<SEARCH>>> and <<<REPLACE>>>
        # Split by <<<SEARCH>>>
        blocks = diff_content.split("<<<SEARCH>>>")[1:]
        if not blocks:
            # Fallback for LLMs that ignored instructions and just returned code
            # We won't apply it automatically because it's too risky.
            return {"success": False, "stderr": "No <<<SEARCH>>> blocks found in output."}
            
        modifications = 0
        for block in blocks:
            if "<<<REPLACE>>>" not in block:
                continue
                
            parts = block.split("<<<REPLACE>>>")
            if len(parts) != 2:
                continue
                
            search_str = parts[0].strip("\n")
            replace_str = parts[1].split("<<<")[0].strip("\n") # in case there are other markers
            
            # Simple string replacement
            if search_str in content:
                content = content.replace(search_str, replace_str, 1)
                modifications += 1
            else:
                # Try fuzzy matching or ignore whitespace?
                # For safety, require exact match on the stripped version?
                # We can try falling back to stripped line-by-line replace if exact fails.
                return {"success": False, "stderr": f"Search block not found in {target_file}:\n{search_str[:100]}..."}
                
        if modifications == 0:
            return {"success": False, "stderr": "No replacements were made."}
            
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {"success": True, "stderr": ""}
        
    except Exception as e:
        return {"success": False, "stderr": str(e)}
