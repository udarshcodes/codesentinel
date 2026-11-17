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
    found = False
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        if finding["package"] in data.get(group, {}):
            found = True
            if data[group][finding['package']] == version:
                continue
            data[group][finding["package"]] = version
            changed = True
    if not found:
        raise ValueError("The dependency declaration is missing from the selected manifest.")
    if not changed:
        return None
    updated = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return "<<<SEARCH>>>\n" + source.strip("\n") + "\n<<<REPLACE>>>\n" + updated


def python_dependency_patch(source, path, finding):
    from agents.dependency_analyzer import compatible_registry_update
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    version = finding.get('recommended_version')
    if not compatible_registry_update(finding.get('current_version'), version):
        raise ValueError('A registry-confirmed newer same-major release is required.')
    if os.path.basename(path) == 'pyproject.toml':
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        values = tomllib.loads(source).get('project', {}).get('dependencies', [])
    elif os.path.basename(path) == 'requirements.txt':
        values = [line.split(' #', 1)[0].strip() for line in source.splitlines()
                  if line.strip() and not line.lstrip().startswith('#')]
    else:
        raise ValueError('Automatic Python remediation requires a static dependency manifest.')
    matches = [(value, Requirement(value)) for value in values
               if canonicalize_name(Requirement(value).name) == canonicalize_name(finding['package'])]
    if len(matches) != 1:
        raise ValueError('The selected dependency must have one unambiguous declaration.')
    original, requirement = matches[0]
    pins = [specifier.version for specifier in requirement.specifier if specifier.operator == '==']
    if pins == [version]:
        return None
    if requirement.url or pins != [finding['current_version']]:
        raise ValueError('The selected manifest does not contain the expected pinned version.')
    remaining = [str(specifier) for specifier in requirement.specifier if specifier.operator != '==']
    if not SpecifierSet(','.join(remaining)).contains(version):
        raise ValueError('The verified update violates another declared constraint.')
    requirement.specifier = SpecifierSet(','.join(remaining + ['==' + version]))
    updated = str(requirement)
    if os.path.basename(path) == 'pyproject.toml':
        tokens = [json.dumps(original, ensure_ascii=False)]
        if "'" not in original:
            tokens.append("'" + original + "'")
        token = next((value for value in tokens if source.count(value) == 1), None)
        if not token:
            raise ValueError('Cannot safely locate the quoted dependency declaration.')
        original, updated = token, json.dumps(updated, ensure_ascii=False)
    elif source.count(original) != 1:
        raise ValueError('Cannot safely locate the requirement declaration.')
    return '<<<SEARCH>>>\n' + original + '\n<<<REPLACE>>>\n' + updated + '\n'


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
