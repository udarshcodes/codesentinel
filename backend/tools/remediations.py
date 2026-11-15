"""Small syntax-checked repairs for well-defined scanner findings."""
import ast
import json
import os
import re


def request_timeout_patch(source, line=None):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    aliases = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.Import)
               for alias in node.names if alias.name == "requests"}
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                  and node.func.value.id in aliases and node.func.attr in {"get", "post", "put", "patch", "delete", "head", "options", "request"}
                  and not any(key.arg in (None, "timeout") for key in node.keywords)]
    if not candidates:
        return None
    node = min(candidates, key=lambda n: abs(n.lineno - int(line or n.lineno)))
    old = ast.get_source_segment(source, node)
    if not old or not old.endswith(")"):
        return None
    prefix = old[:-1].rstrip()
    new = prefix + (" " if prefix.endswith(("(", ",")) else ", ") + "timeout=30)"
    candidate = source.replace(old, new, 1)
    ast.parse(candidate)
    return "<<<SEARCH>>>\n" + old + "\n<<<REPLACE>>>\n" + new + "\n"


def npm_dependency_patch(source, path, finding):
    from agents.dependency_analyzer import compatible_registry_update
    if os.path.basename(path) != "package.json":
        raise ValueError("Automatic npm remediation requires a package.json declaration.")
    version = finding.get("recommended_version")
    if not compatible_registry_update(finding.get("current_version"), version):
        raise ValueError("A registry-confirmed newer same-major release is required.")
    data = json.loads(source)
    changed = False
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        if finding["package"] in data.get(group, {}):
            data[group][finding["package"]] = version
            changed = True
    if not changed:
        raise ValueError("The dependency declaration is missing from the selected manifest.")
    updated = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return "<<<SEARCH>>>\n" + source.strip("\n") + "\n<<<REPLACE>>>\n" + updated


def deferred_effect_state_patch(source, line):
    """Preserve a boolean reset followed by early return in an effect guard."""
    if not isinstance(line, int) or line < 2:
        return None
    lines = source.splitlines(keepends=True)
    index = line - 1
    if index + 2 >= len(lines):
        return None
    call = re.fullmatch(r'(\s*)(set[A-Za-z0-9_$]+)\((true|false)\);\s*', lines[index])
    if not call or lines[index + 1].strip() != 'return;' or lines[index + 2].strip() != '}':
        return None
    if not re.search(r'\bif\s*\(.*\)\s*\{\s*$', lines[index - 1]) or 'useEffect(' not in source:
        return None
    indent, setter, value = call.groups()
    if not re.search(r'\[\s*\w+\s*,\s*' + re.escape(setter) + r'\s*\]\s*=\s*useState\(', source):
        return None
    if 'codesentinelEffectReset' in source:
        return None
    old = lines[index] + lines[index + 1]
    new = (f'{indent}const codesentinelEffectReset = setTimeout(() => {setter}({value}), 0);\n'
           f'{indent}return () => clearTimeout(codesentinelEffectReset);\n')
    return '<<<SEARCH>>>\n' + old.rstrip('\n') + '\n<<<REPLACE>>>\n' + new
