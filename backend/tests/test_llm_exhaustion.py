import pytest
import sys
import os
import json
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.llm_router import invoke_llm, LLMExhaustionError, MAX_RETRIES_PER_TIER
from config import PRIMARY_MODELS, FALLBACK_MODEL

@pytest.mark.asyncio
async def test_llm_exhaustion_error_raised(monkeypatch):
    def mock_get_next(*args, **kwargs):
        raise RuntimeError("All API keys exhausted including emergency key.")

    monkeypatch.setattr("tools.llm_router.get_next_key", mock_get_next)
    monkeypatch.setattr("tools.llm_router.GROQ_API_KEYS", ["mock"])
    
    with pytest.raises(LLMExhaustionError, match="LLM Exhaustion"):
        await invoke_llm("test prompt", "test_agent")

@pytest.mark.asyncio
async def test_llm_router_iteration(monkeypatch):
    """Test that the router tries Tier 1, then Tier 2, then fallback on schema failures."""
    models_tried = []
    
    class MockChatGroq:
        def __init__(self, model, **kwargs):
            self.model = model
            models_tried.append(model)
        
        def bind(self, **kwargs):
            return self
            
        def invoke(self, prompt):
            class Response:
                content = "not valid json"
                usage_metadata = {"total_tokens": 10, "output_tokens": 5}
            return Response()

    monkeypatch.setattr("tools.llm_router.ChatGroq", MockChatGroq)
    monkeypatch.setattr("tools.llm_router.GROQ_API_KEYS", ["mock"])
    
    def mock_get_next(*args, **kwargs):
        return "mock_key", 0
        
    monkeypatch.setattr("tools.llm_router.get_next_key", mock_get_next)
    
    with pytest.raises(LLMExhaustionError):
        await invoke_llm("test prompt", "test_agent", expect_json=True)
    
    # It should try PRIMARY_MODELS[0] 3 times, PRIMARY_MODELS[1] 3 times, FALLBACK_MODEL 3 times
    assert len(models_tried) == 9
    assert models_tried[0:3] == [PRIMARY_MODELS[0]] * 3
    assert models_tried[3:6] == [PRIMARY_MODELS[1]] * 3
    assert models_tried[6:9] == [FALLBACK_MODEL] * 3
