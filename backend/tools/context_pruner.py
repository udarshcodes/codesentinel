import ast

CONTEXT_LINES = 3 # Unchanged lines to keep on each side of a change within a hunk

def extract_relevant_hunks(diff: str) -> str:
    """
    Process each hunk in a git diff independently.
    For each hunk, keep only:
    - The @@ header line
    - CONTEXT_LINES unchanged lines before the first +/- line
    - All changed (+/-) lines
    - CONTEXT_LINES unchanged lines after the last +/- line
    """
    if not diff or not diff.strip():
        return ""
        
    output_sections = []
    current_file_header: list[str] = []
    current_hunk_lines: list[str] = []
    in_hunk = False
    
    def flush_hunk():
        if not current_hunk_lines:
            return
        hunk_header = current_hunk_lines[0]
        body = current_hunk_lines[1:]
        
        changed_indices = [i for i, line in enumerate(body) if line.startswith(("+", "-"))]
        if not changed_indices:
            return
            
        first_change = changed_indices[0]
        last_change = changed_indices[-1]
        start = max(0, first_change - CONTEXT_LINES)
        end = min(len(body), last_change + CONTEXT_LINES + 1)
        
        pruned_body: list[str] = []
        if start > 0:
            pruned_body.append(f" [...{start} unchanged lines omitted]")
        pruned_body.extend(body[start:end])
        if end < len(body):
            pruned_body.append(f" [...{len(body) - end} unchanged lines omitted]")
            
        output_sections.append("\n".join(current_file_header + [hunk_header] + pruned_body))

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            flush_hunk()
            current_hunk_lines = []
            current_file_header = [line]
            in_hunk = False
        elif line.startswith(("---", "+++")):
            current_file_header.append(line)
        elif line.startswith("@@"):
            flush_hunk()
            current_hunk_lines = [line]
            in_hunk = True
        elif in_hunk:
            current_hunk_lines.append(line)
            
    flush_hunk()
    return "\n\n".join(output_sections)

def extract_function_context(file_content: str, changed_lines: list[int]) -> str:
    """
    Given a file's full content and the line numbers that changed, return
    the smallest slice of the file that contains those changes.
    """
    if not changed_lines:
        return ""
        
    changed_lines = [int(x) for x in changed_lines]
        
    try:
        tree = ast.parse(file_content)
        lines = file_content.splitlines()
        changed_set = set(changed_lines)
        relevant_functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_lines = set(range(node.lineno, node.end_lineno + 1))
                if fn_lines & changed_set:
                    body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                    relevant_functions.append(
                        f"# Function: {node.name} (lines {node.lineno}-{node.end_lineno})\n{body}"
                    )
                    
        if relevant_functions:
            return "\n\n".join(relevant_functions)
            
    except SyntaxError:
        pass
        
    return extract_error_window(file_content, min(changed_lines), max(changed_lines))

def extract_error_window(file_content: str, first_line: int, last_line: int, window: int = 10) -> str:
    """Return a tight line window around a known error or change range."""
    if not file_content:
        return ""
    lines = file_content.splitlines()
    start = max(0, first_line - window - 1)
    end = min(len(lines), last_line + window)
    header = f"[Lines {start + 1} to {end} of {len(lines)} total]\n"
    return header + "\n".join(lines[start:end])
