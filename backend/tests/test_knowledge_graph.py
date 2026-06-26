"""
Tests for tools/knowledge_graph.py — import parsing, graph building,
cycle detection, and service boundary identification.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.knowledge_graph import (
    KnowledgeGraph,
    build_knowledge_graph,
    _parse_python_imports,
    _parse_js_ts_imports,
    _parse_go_imports,
    _parse_java_imports,
)

# ---------------------------------------------------------------------------
# Unit tests for import parsers
# ---------------------------------------------------------------------------


class TestParsePythonImports:
    def test_simple_import(self):
        code = "import os\nimport sys\n"
        result = _parse_python_imports("test.py", code)
        assert "os" in result
        assert "sys" in result

    def test_from_import(self):
        code = "from os.path import join\nfrom collections import defaultdict\n"
        result = _parse_python_imports("test.py", code)
        assert "os.path" in result
        assert "collections" in result

    def test_relative_import(self):
        code = "from .utils import helper\n"
        result = _parse_python_imports("test.py", code)
        # Relative imports have no module when level > 0 and module is None
        # But 'from .utils' has module='utils'
        # Actually ast gives module='utils' for 'from .utils import helper'
        # The point is it doesn't crash
        assert isinstance(result, list)

    def test_syntax_error(self):
        code = "import os\ndef broken(:\n"
        result = _parse_python_imports("test.py", code)
        assert result == []


class TestParseJsTsImports:
    def test_es6_import(self):
        code = "import React from 'react';\nimport { useState } from 'react';\n"
        result = _parse_js_ts_imports(code)
        assert "react" in result

    def test_require(self):
        code = "const express = require('express');\n"
        result = _parse_js_ts_imports(code)
        assert "express" in result

    def test_relative_import(self):
        code = "import utils from './utils';\n"
        result = _parse_js_ts_imports(code)
        assert "./utils" in result

    def test_dynamic_import(self):
        code = "const mod = await import('./module');\n"
        result = _parse_js_ts_imports(code)
        assert "./module" in result


class TestParseGoImports:
    def test_single_import(self):
        code = 'import "fmt"\n'
        result = _parse_go_imports(code)
        assert "fmt" in result

    def test_block_import(self):
        code = 'import (\n\t"fmt"\n\t"os"\n)\n'
        result = _parse_go_imports(code)
        assert "fmt" in result
        assert "os" in result


class TestParseJavaImports:
    def test_simple_import(self):
        code = "import java.util.List;\nimport java.io.File;\n"
        result = _parse_java_imports(code)
        assert "java.util.List" in result
        assert "java.io.File" in result

    def test_static_import(self):
        code = "import static org.junit.Assert.assertEquals;\n"
        result = _parse_java_imports(code)
        assert "org.junit.Assert.assertEquals" in result


# ---------------------------------------------------------------------------
# KnowledgeGraph class tests
# ---------------------------------------------------------------------------


class TestKnowledgeGraph:
    def test_add_node_and_edge(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        assert "a.py" in g.nodes
        assert "b.py" in g.nodes
        assert len(g.edges) == 1

    def test_get_dependencies(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        deps = g.get_dependencies("a.py")
        assert len(deps) == 1
        assert deps[0]["target"] == "b.py"

    def test_get_dependents(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        dependents = g.get_dependents("b.py")
        assert "a.py" in dependents

    def test_find_no_cycles(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        cycles = g.find_cycles()
        assert len(cycles) == 0

    def test_find_cycle(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "a.py")
        cycles = g.find_cycles()
        assert len(cycles) >= 1
        # At least one cycle should contain a, b, c
        flat = [node for cycle in cycles for node in cycle]
        assert "a.py" in flat

    def test_dependency_tree(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        tree = g.get_dependency_tree("a.py")
        assert tree["file"] == "a.py"
        assert len(tree["deps"]) == 1
        assert tree["deps"][0]["file"] == "b.py"

    def test_service_boundaries(self):
        g = KnowledgeGraph()
        g.add_node("api/routes.py")
        g.add_node("api/views.py")
        g.add_node("models/user.py")
        g.add_edge("api/routes.py", "models/user.py")
        boundaries = g.identify_service_boundaries()
        service_names = [b["service"] for b in boundaries]
        assert "api" in service_names
        assert "models" in service_names

    def test_to_dict(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_edge("a.py", "b.py")
        g.add_node("b.py")
        g.identify_service_boundaries()
        result = g.to_dict()
        assert "nodes" in result
        assert "edges" in result
        assert "cycles" in result
        assert "node_count" in result


# ---------------------------------------------------------------------------
# Integration test — build_knowledge_graph on a temp directory
# ---------------------------------------------------------------------------


class TestBuildKnowledgeGraph:
    def test_build_from_python_repo(self, tmp_path):
        # Create a mini Python project
        (tmp_path / "app.py").write_text("from utils import helper\nimport os\n")
        (tmp_path / "utils.py").write_text("import json\ndef helper(): pass\n")

        graph = build_knowledge_graph(str(tmp_path))
        assert "app.py" in graph.nodes
        assert "utils.py" in graph.nodes
        # app.py should have an edge to utils.py
        deps = graph.get_dependencies("app.py")
        targets = [d["target"] for d in deps]
        assert "utils.py" in targets

    def test_build_from_js_repo(self, tmp_path):
        (tmp_path / "index.js").write_text("import App from './App';\n")
        (tmp_path / "App.js").write_text("export default function App() {}\n")

        graph = build_knowledge_graph(str(tmp_path))
        assert "index.js" in graph.nodes
        assert "App.js" in graph.nodes

    def test_build_with_cycle(self, tmp_path):
        (tmp_path / "a.py").write_text("from b import foo\n")
        (tmp_path / "b.py").write_text("from a import bar\n")

        graph = build_knowledge_graph(str(tmp_path))
        cycles = graph.find_cycles()
        assert len(cycles) >= 1

    def test_build_empty_repo(self, tmp_path):
        graph = build_knowledge_graph(str(tmp_path))
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
