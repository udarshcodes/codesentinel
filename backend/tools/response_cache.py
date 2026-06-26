import hashlib
import json
import os
import atexit
from collections import OrderedDict

CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".response_cache.json"
)
MAX_CACHE_SIZE = 500


class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key: str) -> str | None:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value: str):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def load(self, file_path: str):
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.set(k, v)
            except Exception:
                pass

    def save(self, file_path: str):
        try:
            with open(file_path, "w") as f:
                json.dump(self.cache, f)
        except Exception:
            pass


_cache = LRUCache(MAX_CACHE_SIZE)
_cache.load(CACHE_FILE)


def save_cache_on_exit():
    _cache.save(CACHE_FILE)


atexit.register(save_cache_on_exit)


def _make_cache_key(prompt: str, model: str) -> str:
    payload = json.dumps({"prompt": prompt, "model": model}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_cached(prompt: str, model: str) -> str | None:
    return _cache.get(_make_cache_key(prompt, model))


def set_cached(prompt: str, model: str, response: str) -> None:
    key = _make_cache_key(prompt, model)
    _cache.set(key, response)
