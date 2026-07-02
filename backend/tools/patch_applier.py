import os
import shutil
import difflib
import re
import ast


def strip_markdown(text: str, target_file: str) -> str:
    """Removes markdown code fences if present, unless targeting a markdown file."""
    if target_file.endswith(".md"):
        return text.strip("\n")

    lines = text.splitlines()
    cleaned = [line for line in lines if not re.match(r"^\s*```.*$", line)]
    return "\n".join(cleaned).strip("\n")


def strip_conversational_comments(text: str) -> str:
    """Removes common LLM conversational phrasing masquerading as comments."""
    lines = text.splitlines()
    cleaned = [
        line
        for line in lines
        if not re.match(
            r"^\s*#\s*(However|Here is|The above|Note that|To fix)", line, re.IGNORECASE
        )
    ]
    return "\n".join(cleaned)


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
        with open(full_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            content = f.read()
            original_newlines = f.newlines

        content = content.replace("\r\n", "\n")

        # Create backup before patching
        backup_path = full_path + ".bak"
        shutil.copy2(full_path, backup_path)

        # Very basic parse for <<<SEARCH>>> and <<<REPLACE>>>
        # Split by <<<SEARCH>>>
        blocks = diff_content.split("<<<SEARCH>>>")[1:]
        if not blocks:
            # Fallback for LLMs that ignored instructions and just returned code
            # We won't apply it automatically because it's too risky.
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return {
                "success": False,
                "stderr": "No <<<SEARCH>>> blocks found in output.",
            }

        modifications = 0
        for block in blocks:
            if "<<<REPLACE>>>" not in block:
                continue

            parts = block.split("<<<REPLACE>>>")
            if len(parts) != 2:
                continue

            search_str = strip_markdown(parts[0], target_file)
            replace_str = strip_markdown(parts[1].split("<<<")[0], target_file)

            replace_str = strip_conversational_comments(replace_str)

            # --- Attempt 1: Exact match ---
            if search_str in content:
                content = content.replace(search_str, replace_str, 1)
                modifications += 1
                continue

            # --- Attempt 2: Strip trailing whitespace per line and retry ---
            search_stripped = "\n".join(
                line.rstrip() for line in search_str.splitlines()
            )
            content_stripped_for_compare = "\n".join(
                line.rstrip() for line in content.splitlines()
            )
            if search_stripped and search_stripped in content_stripped_for_compare:
                # Find the position in the stripped version and rebuild
                idx = content_stripped_for_compare.index(search_stripped)
                # Map back to original: count newlines to find line range
                before_lines = content_stripped_for_compare[:idx].count("\n")
                search_line_count = search_stripped.count("\n") + 1
                original_lines = content.splitlines(keepends=True)
                # Replace the matched line range
                replace_lines = replace_str.splitlines(keepends=True)
                if not replace_str.endswith("\n") and replace_lines:
                    replace_lines[-1] = (
                        replace_lines[-1]
                        if replace_lines[-1].endswith("\n")
                        else replace_lines[-1] + "\n"
                    )
                new_lines = (
                    original_lines[:before_lines]
                    + replace_lines
                    + original_lines[before_lines + search_line_count :]
                )
                content = "".join(new_lines)
                modifications += 1
                continue

            # --- Attempt 3: Fuzzy line-by-line matching ---
            search_lines = search_str.strip().splitlines()
            content_lines = content.splitlines()

            if len(search_lines) >= 2:
                best_ratio = 0.0
                best_start = -1

                for i in range(len(content_lines) - len(search_lines) + 1):
                    candidate = content_lines[i : i + len(search_lines)]
                    ratio = difflib.SequenceMatcher(
                        None,
                        "\n".join(s.strip() for s in search_lines),
                        "\n".join(s.strip() for s in candidate),
                    ).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_start = i

                if best_ratio >= 0.85 and best_start >= 0:
                    # Replace the matched range
                    replace_lines = replace_str.strip().splitlines()
                    content_lines[best_start : best_start + len(search_lines)] = (
                        replace_lines
                    )
                    content = "\n".join(content_lines) + "\n"
                    modifications += 1
                    print(
                        f"[PatchApplier] Fuzzy match applied (ratio={best_ratio:.2f}) in {target_file}"
                    )
                    continue

            if os.path.exists(backup_path):
                os.remove(backup_path)
            return {
                "success": False,
                "stderr": f"Search block not found in {target_file}:\n{search_str[:100]}...",
            }

        if modifications == 0:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return {"success": False, "stderr": "No replacements were made."}

        # Pass 2: AST syntax verification for Python files on FULL content
        if target_file.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                return {
                    "success": False,
                    "stderr": f"SyntaxError after patch application: {e}",
                }

        write_newline = "\n"
        if isinstance(original_newlines, tuple):
            write_newline = original_newlines[0]
        elif isinstance(original_newlines, str):
            write_newline = original_newlines

        with open(full_path, "w", encoding="utf-8", newline=write_newline) as f:
            f.write(content)

        if os.path.exists(backup_path):
            os.remove(backup_path)
        return {"success": True, "stderr": ""}

    except Exception as e:
        # Attempt rollback from backup
        backup_path = full_path + ".bak"
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, full_path)
            os.remove(backup_path)
        return {"success": False, "stderr": str(e)}
