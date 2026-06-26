import pytest
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.key_dispatcher import get_next_key


def test_select_api_key(monkeypatch):
    monkeypatch.setattr("tools.key_dispatcher.GROQ_API_KEYS", ["key1", "key2"])

    key1, idx = get_next_key()
    assert key1 in ["key1", "key2"]


def test_select_api_key_empty(monkeypatch):
    monkeypatch.setattr("tools.key_dispatcher.GROQ_API_KEYS", [])
    monkeypatch.setattr("tools.key_dispatcher.GROQ_EMERGENCY_KEY", None)

    with pytest.raises(RuntimeError):
        get_next_key()
