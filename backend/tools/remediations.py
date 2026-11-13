"""Small syntax-checked repairs for well-defined scanner findings."""
import ast


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
