"""
Context Pruner — Extract the smallest relevant code slice around changed lines.

Supports Python (AST), JS/TS (regex), Go (regex), and Java (regex).
Falls back to a line-window extraction for unsupported or unparseable files.
"""

import ast
import re


def extract_function_context(
    file_content: str, changed_lines: list[int], file_path: str = ""
) -> str:
    """
    Given a file's full content and the line numbers that changed, return
    the smallest slice of the file that contains those changes.

    Dispatches to language-specific extractors based on file extension.
    """
    if not changed_lines:
        return ""

    changed_lines = [int(x) for x in changed_lines]
    ext = _get_extension(file_path)

    if ext == ".py":
        result = _extract_python_functions(file_content, changed_lines)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        result = _extract_js_functions(file_content, changed_lines)
    elif ext == ".go":
        result = _extract_go_functions(file_content, changed_lines)
    elif ext == ".java":
        result = _extract_java_functions(file_content, changed_lines)
    else:
        result = None

    if result:
        return result

    return extract_error_window(file_content, min(changed_lines), max(changed_lines))


def extract_error_window(
    file_content: str, first_line: int, last_line: int, window: int = 10
) -> str:
    """Return a tight line window around a known error or change range."""
    if not file_content:
        return ""
    lines = file_content.splitlines()
    start = max(0, first_line - window - 1)
    end = min(len(lines), last_line + window)
    header = f"[Lines {start + 1} to {end} of {len(lines)} total]\n"
    return header + "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_extension(file_path: str) -> str:
    """Extract lowercase file extension."""
    if not file_path:
        return ""
    dot = file_path.rfind(".")
    return file_path[dot:].lower() if dot != -1 else ""


# ---------------------------------------------------------------------------
# Python — AST-based
# ---------------------------------------------------------------------------


def _extract_python_functions(
    file_content: str, changed_lines: list[int]
) -> str | None:
    try:
        tree = ast.parse(file_content)
        lines = file_content.splitlines()
        changed_set = set(changed_lines)
        relevant_functions = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not hasattr(node, "end_lineno") or node.end_lineno is None:
                    continue
                fn_lines = set(range(node.lineno, node.end_lineno + 1))
                if fn_lines & changed_set:
                    body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                    kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                    relevant_functions.append(
                        f"# {kind}: {node.name} (lines {node.lineno}-{node.end_lineno})\n{body}"
                    )

        if relevant_functions:
            return "\n\n".join(relevant_functions)

    except SyntaxError:
        pass

    return None


# ---------------------------------------------------------------------------
# JS/TS — Regex + brace matching
# ---------------------------------------------------------------------------

# Patterns that start a function/method/class block
_JS_FUNC_PATTERNS = [
    # Named function: function foo(...) {
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+"),
    # Arrow assigned: const foo = (...) => {
    re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>\s*\{?"
    ),
    # Class method: methodName(...) {
    re.compile(
        r"^\s*(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?\w+\s*\([^)]*\)\s*\{"
    ),
    # Class declaration
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+\w+"),
]


def _extract_js_functions(file_content: str, changed_lines: list[int]) -> str | None:
    return _extract_brace_blocks(
        file_content, changed_lines, _JS_FUNC_PATTERNS, "Function"
    )


# ---------------------------------------------------------------------------
# Go — Regex + brace matching
# ---------------------------------------------------------------------------

_GO_FUNC_PATTERNS = [
    # func name(...) ... {
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?\w+\s*\("),
]


def _extract_go_functions(file_content: str, changed_lines: list[int]) -> str | None:
    return _extract_brace_blocks(
        file_content, changed_lines, _GO_FUNC_PATTERNS, "Function"
    )


# ---------------------------------------------------------------------------
# Java — Regex + brace matching
# ---------------------------------------------------------------------------

_JAVA_FUNC_PATTERNS = [
    # public/private/protected ... type methodName(...) {
    re.compile(
        r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\]]+\s+\w+\s*\("
    ),
    # Class declaration
    re.compile(r"^\s*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+\w+"),
]


def _extract_java_functions(file_content: str, changed_lines: list[int]) -> str | None:
    return _extract_brace_blocks(
        file_content, changed_lines, _JAVA_FUNC_PATTERNS, "Function"
    )


# ---------------------------------------------------------------------------
# Generic brace-matching extractor (shared by JS/TS, Go, Java)
# ---------------------------------------------------------------------------


def _extract_brace_blocks(
    file_content: str, changed_lines: list[int], patterns: list[re.Pattern], label: str
) -> str | None:
    """
    Find all function/class blocks by matching start patterns and tracking
    brace depth to find the end. Return blocks containing changed lines.
    """
    lines = file_content.splitlines()
    changed_set = set(changed_lines)
    blocks: list[tuple[int, int, str]] = []  # (start_line, end_line, name)

    i = 0
    while i < len(lines):
        line = lines[i]
        matched = False
        for pat in patterns:
            if pat.search(line):
                matched = True
                break

        if matched:
            # Extract a name from the line
            name_match = re.search(r"(?:function|class|func)\s+(\w+)", line)
            if not name_match:
                name_match = re.search(r"(?:const|let|var)\s+(\w+)", line)
            name = name_match.group(1) if name_match else f"block_L{i + 1}"

            # Find the opening brace
            start = i
            brace_depth = 0
            found_opening = False

            for j in range(i, min(i + 5, len(lines))):
                brace_depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    found_opening = True
                    break

            if not found_opening:
                i += 1
                continue

            # Track braces to find closing
            brace_depth = 0
            end = start
            for j in range(start, len(lines)):
                brace_depth += lines[j].count("{") - lines[j].count("}")
                if brace_depth <= 0 and found_opening and j > start:
                    end = j
                    break
            else:
                end = len(lines) - 1

            blocks.append((start + 1, end + 1, name))  # 1-indexed
            i = end + 1
        else:
            i += 1

    # Find blocks that overlap with changed lines
    relevant = []
    for start, end, name in blocks:
        block_lines = set(range(start, end + 1))
        if block_lines & changed_set:
            body = "\n".join(lines[start - 1 : end])
            relevant.append(f"// {label}: {name} (lines {start}-{end})\n{body}")

    return "\n\n".join(relevant) if relevant else None
