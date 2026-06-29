"""
Tests for tools/response_cache.py — LRU cache with file persistence.
"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.response_cache import LRUCache, _make_cache_key, get_cached, set_cached


class TestLRUCache(unittest.TestCase):
    def test_set_and_get(self):
        cache = LRUCache(10)
        cache.set("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")

    def test_get_missing_returns_none(self):
        cache = LRUCache(10)
        self.assertIsNone(cache.get("nonexistent"))

    def test_eviction(self):
        cache = LRUCache(3)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.set("c", "3")
        cache.set("d", "4")  # Should evict 'a'
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("d"), "4")

    def test_lru_ordering(self):
        cache = LRUCache(3)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.set("c", "3")
        # Access 'a' to make it recently used
        cache.get("a")
        # Now add 'd' — should evict 'b' (least recently used)
        cache.set("d", "4")
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), "1")

    def test_overwrite(self):
        cache = LRUCache(10)
        cache.set("key1", "old")
        cache.set("key1", "new")
        self.assertEqual(cache.get("key1"), "new")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = os.path.join(tmp_dir, "test_cache.json")
            cache = LRUCache(10)
            cache.set("key1", "value1")
            cache.set("key2", "value2")
            cache.save(cache_file)

            # Load into a new cache
            cache2 = LRUCache(10)
            cache2.load(cache_file)
            self.assertEqual(cache2.get("key1"), "value1")
            self.assertEqual(cache2.get("key2"), "value2")

    def test_load_nonexistent_file(self):
        cache = LRUCache(10)
        cache.load("/nonexistent/path.json")
        self.assertIsNone(cache.get("anything"))

    def test_load_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_file = os.path.join(tmp_dir, "corrupt.json")
            with open(cache_file, "w") as f:
                f.write("not valid json!!!")
            cache = LRUCache(10)
            cache.load(cache_file)
            self.assertIsNone(cache.get("anything"))


class TestCacheKeys(unittest.TestCase):
    def test_make_cache_key_deterministic(self):
        key1 = _make_cache_key("hello", "llama3-8b")
        key2 = _make_cache_key("hello", "llama3-8b")
        self.assertEqual(key1, key2)

    def test_different_prompts_different_keys(self):
        key1 = _make_cache_key("hello", "llama3-8b")
        key2 = _make_cache_key("world", "llama3-8b")
        self.assertNotEqual(key1, key2)

    def test_different_models_different_keys(self):
        key1 = _make_cache_key("hello", "llama3-8b")
        key2 = _make_cache_key("hello", "llama3-70b")
        self.assertNotEqual(key1, key2)


class TestModuleLevelCache(unittest.TestCase):
    def test_set_and_get_cached(self):
        set_cached("test_prompt_unique_xyz", "test_model", "test_response")
        result = get_cached("test_prompt_unique_xyz", "test_model")
        self.assertEqual(result, "test_response")

    def test_get_cached_miss(self):
        result = get_cached("nonexistent_prompt_xyz", "test_model")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
