import pytest
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.llm_router import _select_api_key

def test_select_api_key(monkeypatch):
    monkeypatch.setattr("config.GROQ_API_KEYS", ["key1", "key2"])
    
    key1 = _select_api_key()
    assert key1 in ["key1", "key2"]
    
def test_select_api_key_empty(monkeypatch):
    monkeypatch.setattr("config.GROQ_API_KEYS", [])
    
    key = _select_api_key()
    assert key is None
