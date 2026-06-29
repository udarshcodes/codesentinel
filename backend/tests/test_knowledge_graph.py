"""
Tests for tools/knowledge_graph.py — import parsing, graph building,
cycle detection, and service boundary identification.
"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.knowledge_graph import (
    KnowledgeGraph,
    build_knowledge_graph,
    _parse_python_imports,
    _parse_js_ts_imports,
    _parse_go_imports,
    _parse_java_imports,
)


class TestParsePythonImports(unittest.TestCase):
    def test_simple_import(self):
        code = "import os\nimport sys\n"
        result = _parse_python_imports("test.py", code)
        self.assertIn("os", result)
        self.assertIn("sys", result)

    def test_from_import(self):
        code = "from os.path import join\nfrom collections import defaultdict\n"
        result = _parse_python_imports("test.py", code)
        self.assertIn("os.path", result)
        self.assertIn("collections", result)

    def test_relative_import(self):
        code = "from .utils import helper\n"
        result = _parse_python_imports("test.py", code)
        self.assertIsInstance(result, list)

    def test_syntax_error(self):
        code = "import os\ndef broken(:\n"
        result = _parse_python_imports("test.py", code)
        self.assertEqual(result, [])


class TestParseJsTsImports(unittest.TestCase):
    def test_es6_import(self):
        code = "import React from 'react';\nimport { useState } from 'react';\n"
        result = _parse_js_ts_imports(code)
        self.assertIn("react", result)

    def test_require(self):
        code = "const express = require('express');\n"
        result = _parse_js_ts_imports(code)
        self.assertIn("express", result)

    def test_relative_import(self):
        code = "import utils from './utils';\n"
        result = _parse_js_ts_imports(code)
        self.assertIn("./utils", result)

    def test_dynamic_import(self):
        code = "const mod = await import('./module');\n"
        result = _parse_js_ts_imports(code)
        self.assertIn("./module", result)


class TestParseGoImports(unittest.TestCase):
    def test_single_import(self):
        code = 'import "fmt"\n'
        result = _parse_go_imports(code)
        self.assertIn("fmt", result)

    def test_block_import(self):
        code = 'import (\n\t"fmt"\n\t"os"\n)\n'
        result = _parse_go_imports(code)
        self.assertIn("fmt", result)
        self.assertIn("os", result)


class TestParseJavaImports(unittest.TestCase):
    def test_simple_import(self):
        code = "import java.util.List;\nimport java.io.File;\n"
        result = _parse_java_imports(code)
        self.assertIn("java.util.List", result)
        self.assertIn("java.io.File", result)

    def test_static_import(self):
        code = "import static org.junit.Assert.assertEquals;\n"
        result = _parse_java_imports(code)
        self.assertIn("org.junit.Assert.assertEquals", result)


class TestKnowledgeGraph(unittest.TestCase):
    def test_add_node_and_edge(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        self.assertIn("a.py", g.nodes)
        self.assertIn("b.py", g.nodes)
        self.assertEqual(len(g.edges), 1)

    def test_get_dependencies(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        deps = g.get_dependencies("a.py")
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["target"], "b.py")

    def test_get_dependents(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_edge("a.py", "b.py", "imports")
        dependents = g.get_dependents("b.py")
        self.assertIn("a.py", dependents)

    def test_find_no_cycles(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        cycles = g.find_cycles()
        self.assertEqual(len(cycles), 0)

    def test_find_cycle(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "a.py")
        cycles = g.find_cycles()
        self.assertGreaterEqual(len(cycles), 1)
        flat = [node for cycle in cycles for node in cycle]
        self.assertIn("a.py", flat)

    def test_dependency_tree(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_node("b.py")
        g.add_node("c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        tree = g.get_dependency_tree("a.py")
        self.assertEqual(tree["file"], "a.py")
        self.assertEqual(len(tree["deps"]), 1)
        self.assertEqual(tree["deps"][0]["file"], "b.py")

    def test_service_boundaries(self):
        g = KnowledgeGraph()
        g.add_node("api/routes.py")
        g.add_node("api/views.py")
        g.add_node("models/user.py")
        g.add_edge("api/routes.py", "models/user.py")
        boundaries = g.identify_service_boundaries()
        service_names = [b["service"] for b in boundaries]
        self.assertIn("api", service_names)
        self.assertIn("models", service_names)

    def test_to_dict(self):
        g = KnowledgeGraph()
        g.add_node("a.py")
        g.add_edge("a.py", "b.py")
        g.add_node("b.py")
        g.identify_service_boundaries()
        result = g.to_dict()
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("cycles", result)
        self.assertIn("node_count", result)


class TestBuildKnowledgeGraph(unittest.TestCase):
    def test_build_from_python_repo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(os.path.join(tmp_dir, "app.py"), "w") as f:
                f.write("from utils import helper\nimport os\n")
            with open(os.path.join(tmp_dir, "utils.py"), "w") as f:
                f.write("import json\ndef helper(): pass\n")

            graph = build_knowledge_graph(tmp_dir)
            self.assertIn("app.py", graph.nodes)
            self.assertIn("utils.py", graph.nodes)
            deps = graph.get_dependencies("app.py")
            targets = [d["target"] for d in deps]
            self.assertIn("utils.py", targets)

    def test_build_from_js_repo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(os.path.join(tmp_dir, "index.js"), "w") as f:
                f.write("import App from './App';\n")
            with open(os.path.join(tmp_dir, "App.js"), "w") as f:
                f.write("export default function App() {}\n")

            graph = build_knowledge_graph(tmp_dir)
            self.assertIn("index.js", graph.nodes)
            self.assertIn("App.js", graph.nodes)

    def test_build_with_cycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(os.path.join(tmp_dir, "a.py"), "w") as f:
                f.write("from b import foo\n")
            with open(os.path.join(tmp_dir, "b.py"), "w") as f:
                f.write("from a import bar\n")

            graph = build_knowledge_graph(tmp_dir)
            cycles = graph.find_cycles()
            self.assertGreaterEqual(len(cycles), 1)

    def test_build_empty_repo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = build_knowledge_graph(tmp_dir)
            self.assertEqual(len(graph.nodes), 0)
            self.assertEqual(len(graph.edges), 0)

    def test_build_from_html_css_repo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(os.path.join(tmp_dir, "index.html"), "w") as f:
                f.write('<html><head><link rel="stylesheet" href="style.css"></head><body><script src="app.js"></script></body></html>')
            with open(os.path.join(tmp_dir, "style.css"), "w") as f:
                f.write('@import url("reset.css");\nbody { color: red; }')
            with open(os.path.join(tmp_dir, "reset.css"), "w") as f:
                f.write('body { margin: 0; }')
            with open(os.path.join(tmp_dir, "app.js"), "w") as f:
                f.write('console.log("hello");')

            graph = build_knowledge_graph(tmp_dir)
            self.assertIn("index.html", graph.nodes)
            self.assertIn("style.css", graph.nodes)
            self.assertIn("reset.css", graph.nodes)
            deps = graph.get_dependencies("index.html")
            targets = [d["target"] for d in deps]
            self.assertIn("style.css", targets)
            self.assertIn("app.js", targets)


if __name__ == "__main__":
    unittest.main()
