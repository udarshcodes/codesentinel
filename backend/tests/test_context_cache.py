"""
Tests for tools/context_cache.py — session-scoped in-memory cache.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import context_cache


class TestContextCache:
    def setup_method(self):
        """Clear the cache before each test."""
        context_cache._cache.clear()

    def test_store_and_get(self):
        context_cache.store("https://github.com/foo/bar", "key1", "value1")
        result = context_cache.get("https://github.com/foo/bar", "key1")
        assert result == "value1"

    def test_get_default(self):
        result = context_cache.get(
            "https://github.com/foo/bar", "nonexistent", "default"
        )
        assert result == "default"

    def test_get_missing_returns_none(self):
        result = context_cache.get("https://github.com/foo/bar", "nonexistent")
        assert result is None

    def test_invalidate(self):
        context_cache.store("https://github.com/foo/bar", "key1", "value1")
        context_cache.invalidate("https://github.com/foo/bar")
        result = context_cache.get("https://github.com/foo/bar", "key1")
        assert result is None

    def test_different_repos_isolated(self):
        context_cache.store("https://github.com/foo/bar", "key1", "value1")
        context_cache.store("https://github.com/baz/qux", "key1", "value2")
        assert context_cache.get("https://github.com/foo/bar", "key1") == "value1"
        assert context_cache.get("https://github.com/baz/qux", "key1") == "value2"


class TestLocalizedGraph:
    def setup_method(self):
        context_cache._cache.clear()

    def test_empty_graph(self):
        result = context_cache.get_localized_graph(
            "https://github.com/foo/bar", "app.py"
        )
        assert result == {}

    def test_localized_graph_returns_relevant_modules(self):
        context_cache.store(
            "https://github.com/foo/bar",
            "knowledge_graph",
            {
                "language": "Python",
                "framework": "FastAPI",
                "modules": ["app.routes", "app.models", "utils.helpers"],
                "api_endpoints": [
                    {"handler_file": "app/routes.py", "path": "/api/users"}
                ],
                "db_interactions": [],
            },
        )
        result = context_cache.get_localized_graph(
            "https://github.com/foo/bar", "app/routes.py"
        )
        assert result["language"] == "Python"
        assert len(result["relevant_modules"]) > 0
        assert any("app" in m for m in result["relevant_modules"])

    def test_localized_graph_caps_results(self):
        many_modules = [f"module_{i}" for i in range(20)]
        context_cache.store(
            "https://github.com/foo/bar",
            "knowledge_graph",
            {
                "language": "Python",
                "framework": "Django",
                "modules": many_modules,
                "api_endpoints": [],
                "db_interactions": [],
            },
        )
        result = context_cache.get_localized_graph(
            "https://github.com/foo/bar", "module_1"
        )
        assert len(result.get("relevant_modules", [])) <= 5
