import pytest
import inspect
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.llm_router import invoke_llm

def test_production_callers_do_not_pass_tier():
    # We can inspect the invoke_llm signature
    sig = inspect.signature(invoke_llm)
    assert "tier" not in sig.parameters, "tier parameter should not be in invoke_llm signature"

@pytest.mark.asyncio
async def test_supported_task_classes(monkeypatch):
    monkeypatch.setattr("tools.llm_router.get_next_key", lambda: ("fake-key", 1))
    monkeypatch.setattr("tools.llm_router.record_usage", lambda *args, **kwargs: None)
    # Mock LLM response to avoid network calls
    class MockChatGroq:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")
            
        def bind(self, **kwargs):
            return self
            
        def invoke(self, prompt):
            class Response:
                content = '{"result": "success"}'
                usage_metadata = {"total_tokens": 10, "output_tokens": 10}
            return Response()

    monkeypatch.setattr("tools.llm_router.ChatGroq", MockChatGroq)
    monkeypatch.setattr("tools.llm_router.GROQ_API_KEYS", ["fake-key"])
    monkeypatch.setattr("tools.llm_router.get_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr("tools.llm_router.set_cached", lambda *args, **kwargs: None)

    # LIGHT task class
    res = await invoke_llm("prompt", "repo_mapper", task_class="LIGHT", expect_json=True)
    assert res == {"result": "success"}
    
    # DEEP task class
    res = await invoke_llm("prompt", "repo_mapper", task_class="DEEP", expect_json=True)
    assert res == {"result": "success"}

@pytest.mark.asyncio
async def test_unknown_task_class_fallback(monkeypatch):
    monkeypatch.setattr("tools.llm_router.get_next_key", lambda: ("fake-key", 1))
    monkeypatch.setattr("tools.llm_router.record_usage", lambda *args, **kwargs: None)
    models_tried = []
    class MockChatGroq:
        def __init__(self, *args, **kwargs):
            models_tried.append(kwargs.get("model"))
            self.model = kwargs.get("model")
            
        def bind(self, **kwargs):
            return self
            
        def invoke(self, prompt):
            class Response:
                content = '{"result": "fallback"}'
                usage_metadata = {"total_tokens": 10, "output_tokens": 10}
            return Response()

    monkeypatch.setattr("tools.llm_router.ChatGroq", MockChatGroq)
    monkeypatch.setattr("tools.llm_router.GROQ_API_KEYS", ["fake-key"])
    monkeypatch.setattr("tools.llm_router.get_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr("tools.llm_router.set_cached", lambda *args, **kwargs: None)

    # UNKNOWN task class should fallback to token-based heuristic
    # short prompt <= 5000 tokens means it acts like Tier 1
    res = await invoke_llm("short prompt", "repo_mapper", task_class="UNKNOWN", expect_json=True)
    assert res == {"result": "fallback"}
    assert len(models_tried) > 0

@pytest.mark.asyncio
async def test_router_tier_selection_deterministic(monkeypatch):
    monkeypatch.setattr("tools.llm_router.get_next_key", lambda: ("fake-key", 1))
    monkeypatch.setattr("tools.llm_router.record_usage", lambda *args, **kwargs: None)
    models_tried = []
    class MockChatGroq:
        def __init__(self, *args, **kwargs):
            models_tried.append(kwargs.get("model"))
            
        def bind(self, **kwargs):
            return self
            
        def invoke(self, prompt):
            class Response:
                content = '{"result": "success"}'
                usage_metadata = {"total_tokens": 10, "output_tokens": 10}
            return Response()

    monkeypatch.setattr("tools.llm_router.ChatGroq", MockChatGroq)
    monkeypatch.setattr("tools.llm_router.GROQ_API_KEYS", ["fake-key"])
    monkeypatch.setattr("tools.llm_router.get_cached", lambda *args, **kwargs: None)
    monkeypatch.setattr("tools.llm_router.set_cached", lambda *args, **kwargs: None)

    from config import PRIMARY_MODELS
    
    # 1. LIGHT should try PRIMARY_MODELS[0] first
    await invoke_llm("prompt", "repo_mapper", task_class="LIGHT", expect_json=True)
    assert models_tried[-1] == PRIMARY_MODELS[0]
    
    # 2. DEEP should try PRIMARY_MODELS[1] first
    await invoke_llm("prompt", "repo_mapper", task_class="DEEP", expect_json=True)
    assert models_tried[-1] == PRIMARY_MODELS[1]
