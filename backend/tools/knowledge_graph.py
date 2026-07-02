"""
Knowledge Graph Builder — Structural analysis of repository imports,
dependencies, and service boundaries.

Builds a real graph (adjacency list) with:
  - Nodes: files, modules
  - Edges: import/require relationships
  - Cycle detection (circular dependencies)
  - Service boundary identification
"""

import os
import re
import ast
from collections import defaultdict


class KnowledgeGraph:
    """
    A directed graph of file-level import relationships.

    Nodes are relative file paths.
    Edges are (source, target, relationship_type) triples.
    """

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: list[dict] = []
        self._adj: dict[str, list[dict]] = defaultdict(list)
        self.service_boundaries: list[dict] = []

    def add_node(self, file_path: str):
        self.nodes.add(file_path)

    def add_edge(self, source: str, target: str, relationship: str = "imports"):
        edge = {"source": source, "target": target, "relationship": relationship}
        self.edges.append(edge)
        self._adj[source].append({"target": target, "relationship": relationship})

    def get_dependencies(self, file_path: str) -> list[dict]:
        """Return all direct dependencies (outgoing edges) of a file."""
        return self._adj.get(file_path, [])

    def get_dependents(self, file_path: str) -> list[str]:
        """Return all files that depend on (import) the given file."""
        return [e["source"] for e in self.edges if e["target"] == file_path]

    def get_dependency_tree(self, file_path: str, depth: int = 3) -> dict:
        """Return a nested dependency tree rooted at file_path, up to `depth` levels."""
        visited = set()

        def _build(node, d):
            if d <= 0 or node in visited:
                return {"file": node, "deps": []}
            visited.add(node)
            children = []
            for dep in self._adj.get(node, []):
                children.append(_build(dep["target"], d - 1))
            return {"file": node, "deps": children}

        return _build(file_path, depth)

    def find_cycles(self) -> list[list[str]]:
        """Detect all circular dependency cycles using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}
        parent = {}
        cycles = []

        def dfs(u, path):
            color[u] = GRAY
            path.append(u)
            for edge in self._adj.get(u, []):
                v = edge["target"]
                if v not in color:
                    continue
                if color[v] == GRAY:
                    # Found a cycle — extract it
                    cycle_start = path.index(v)
                    cycle = path[cycle_start:] + [v]
                    cycles.append(cycle)
                elif color[v] == WHITE:
                    parent[v] = u
                    dfs(v, path)
            path.pop()
            color[u] = BLACK

        for node in self.nodes:
            if color[node] == WHITE:
                dfs(node, [])

        return cycles

    def identify_service_boundaries(self) -> list[dict]:
        """
        Group files into logical service boundaries by top-level directory.
        Detect cross-boundary edges.
        """
        services: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            parts = node.replace("\\", "/").split("/")
            service = parts[0] if len(parts) > 1 else "root"
            services[service].append(node)

        boundaries = []
        for service_name, files in services.items():
            file_set = set(files)
            internal_edges = 0
            external_edges = []
            for f in files:
                for dep in self._adj.get(f, []):
                    if dep["target"] in file_set:
                        internal_edges += 1
                    else:
                        external_edges.append(
                            {
                                "from": f,
                                "to": dep["target"],
                                "relationship": dep["relationship"],
                            }
                        )
            boundaries.append(
                {
                    "service": service_name,
                    "files": files,
                    "file_count": len(files),
                    "internal_edges": internal_edges,
                    "cross_boundary_edges": external_edges[:10],  # Cap for token budget
                }
            )

        self.service_boundaries = boundaries
        return boundaries

    def to_dict(self) -> dict:
        """Serialize the graph to a JSON-safe dict for storage in pipeline state."""
        return {
            "nodes": list(self.nodes),
            "edges": self.edges[:200],  # Cap for token budget
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "service_boundaries": self.service_boundaries,
            "cycles": self.find_cycles(),
        }


# ---------------------------------------------------------------------------
# Import parsers (per language)
# ---------------------------------------------------------------------------


def _parse_python_imports(file_path: str, content: str) -> list[str]:
    """Extract import targets from a Python file using AST."""
    imports = []
    try:
        tree = ast.parse(content, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except SyntaxError:
        pass
    return imports


def _parse_js_ts_imports(content: str) -> list[str]:
    """Extract import targets from JS/TS using regex."""
    imports = []

    # ES6 imports: import ... from '...'
    for m in re.finditer(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", content):
        imports.append(m.group(1))

    # Dynamic imports: import('...')
    for m in re.finditer(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""", content):
        imports.append(m.group(1))

    # CommonJS: require('...')
    for m in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", content):
        imports.append(m.group(1))

    return imports


def _parse_go_imports(content: str) -> list[str]:
    """Extract import paths from Go files."""
    imports = []
    # Single import: import "pkg"
    for m in re.finditer(r'import\s+"([^"]+)"', content):
        imports.append(m.group(1))
    # Block import: import ( "pkg1" \n "pkg2" )
    block = re.search(r"import\s*\((.*?)\)", content, re.DOTALL)
    if block:
        for m in re.finditer(r'"([^"]+)"', block.group(1)):
            imports.append(m.group(1))
    return imports


def _parse_java_imports(content: str) -> list[str]:
    """Extract import packages from Java files."""
    imports = []
    for m in re.finditer(r"import\s+(static\s+)?([a-zA-Z0-9_.]+)\s*;", content):
        imports.append(m.group(2))
    return imports


def _parse_rust_imports(content: str) -> list[str]:
    """Extract use/mod/extern crate targets from Rust files."""
    imports = []
    # use statements: use crate::module::item;
    for m in re.finditer(r"use\s+(?:crate::)?([a-zA-Z0-9_:]+)", content):
        imports.append(m.group(1))
    # mod declarations: mod module_name;
    for m in re.finditer(r"mod\s+([a-zA-Z0-9_]+)\s*;", content):
        imports.append(m.group(1))
    # extern crate: extern crate name;
    for m in re.finditer(r"extern\s+crate\s+([a-zA-Z0-9_]+)", content):
        imports.append(m.group(1))
    return imports


def _parse_html_imports(content: str) -> list[str]:
    """Extract script src and stylesheet link href from HTML files."""
    imports = []
    for m in re.finditer(
        r'<script[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE
    ):
        imports.append(m.group(1))
    for m in re.finditer(r'<link[^>]+href=["\']([^"\']+)["\']', content, re.IGNORECASE):
        imports.append(m.group(1))
    return imports


def _parse_css_imports(content: str) -> list[str]:
    """Extract @import url(...) or @import "..." from CSS files."""
    imports = []
    for m in re.finditer(
        r'@import\s+(?:url\()?["\']?([^"\')\s]+)["\']?\)?', content, re.IGNORECASE
    ):
        imports.append(m.group(1))
    return imports


# ---------------------------------------------------------------------------
# Resolve import string → relative file path
# ---------------------------------------------------------------------------

_EXTENSION_MAP = {
    ".py": [".py"],
    ".js": [".js", ".jsx", ".ts", ".tsx"],
    ".jsx": [".js", ".jsx", ".ts", ".tsx"],
    ".ts": [".js", ".jsx", ".ts", ".tsx"],
    ".tsx": [".js", ".jsx", ".ts", ".tsx"],
    ".go": [".go"],
    ".java": [".java"],
    ".rs": [".rs"],
    ".html": [".html", ".htm"],
    ".css": [".css"],
}


def _resolve_import(
    import_str: str,
    source_file: str,
    repo_root: str,
    all_files: set[str],
    source_ext: str,
) -> str | None:
    """
    Try to resolve an import string to a relative file path within the repo.
    Returns None if it's an external/stdlib import.
    """
    # Skip obvious external packages
    if import_str.startswith(("http://", "https://", "@", "node:")):
        return None

    candidates = []

    if source_ext == ".py":
        # Python: convert dotted module path to file path
        module_path = import_str.replace(".", "/")
        candidates.append(module_path + ".py")
        candidates.append(module_path + "/__init__.py")
    elif source_ext in (".js", ".jsx", ".ts", ".tsx"):
        # JS/TS: relative imports start with ./ or ../
        if import_str.startswith("."):
            source_dir = os.path.dirname(source_file)
            resolved = os.path.normpath(os.path.join(source_dir, import_str))
            resolved = resolved.replace("\\", "/")
            # Try with various extensions
            for ext in [".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts"]:
                candidates.append(resolved + ext)
            candidates.append(resolved)  # Could already have extension
        else:
            return None  # npm package
    elif source_ext == ".go":
        # Go: internal imports contain the module path
        parts = import_str.split("/")
        candidates.append("/".join(parts) + ".go")
        if len(parts) >= 1:
            candidates.append(parts[-1] + ".go")
    elif source_ext == ".java":
        # Java: com.example.Class → com/example/Class.java
        candidates.append(import_str.replace(".", "/") + ".java")
    elif source_ext == ".rs":
        # Rust: crate::module → module.rs or module/mod.rs
        mod_path = import_str.replace("::", "/")
        candidates.append(mod_path + ".rs")
        candidates.append(mod_path + "/mod.rs")
    elif source_ext in (".html", ".css"):
        source_dir = os.path.dirname(source_file)
        clean_imp = import_str.lstrip("/")
        resolved_rel = os.path.normpath(os.path.join(source_dir, import_str)).replace(
            "\\", "/"
        )
        candidates.append(resolved_rel)
        candidates.append(clean_imp)

    for candidate in candidates:
        normalized = candidate.replace("\\", "/").lstrip("/")
        if normalized in all_files:
            return normalized
        for f in all_files:
            if f == normalized or f.endswith("/" + normalized):
                return f
            if f.startswith(normalized + "/") or ("/" + normalized + "/") in ("/" + f):
                return f

    return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_knowledge_graph(repo_root: str) -> KnowledgeGraph:
    """
    Walk the repository, parse imports in all source files, and build
    a KnowledgeGraph with file-level nodes and import edges.
    """
    graph = KnowledgeGraph()
    all_files: set[str] = set()
    file_contents: dict[str, str] = {}

    # Collect all source files
    for root, dirs, files in os.walk(repo_root):
        # Skip non-source directories
        dirs[:] = [
            d
            for d in dirs
            if d
            not in (
                ".git",
                "node_modules",
                "venv",
                ".venv",
                "__pycache__",
                "dist",
                "build",
                ".next",
                "target",
                "vendor",
            )
        ]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext in (
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".go",
                ".java",
                ".rs",
                ".html",
                ".css",
            ):
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, repo_root).replace("\\", "/")
                all_files.add(rel_path)
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        file_contents[rel_path] = f.read(10000)  # Cap per file
                except Exception:
                    pass

    # Add nodes
    for fp in all_files:
        graph.add_node(fp)

    # Parse imports and add edges
    for rel_path, content in file_contents.items():
        ext = os.path.splitext(rel_path)[1]

        if ext == ".py":
            raw_imports = _parse_python_imports(rel_path, content)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            raw_imports = _parse_js_ts_imports(content)
        elif ext == ".go":
            raw_imports = _parse_go_imports(content)
        elif ext == ".java":
            raw_imports = _parse_java_imports(content)
        elif ext == ".rs":
            raw_imports = _parse_rust_imports(content)
        elif ext == ".html":
            raw_imports = _parse_html_imports(content)
        elif ext == ".css":
            raw_imports = _parse_css_imports(content)
        else:
            continue

        for imp in raw_imports:
            resolved = _resolve_import(imp, rel_path, repo_root, all_files, ext)
            if resolved and resolved != rel_path:
                graph.add_edge(rel_path, resolved, "imports")

    # Identify service boundaries
    graph.identify_service_boundaries()

    return graph
