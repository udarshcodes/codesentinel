import pytest
import sys
import httpx
from unittest.mock import patch, MagicMock

import worker
from tools.llm_router import LLMExhaustionError

@pytest.mark.asyncio
async def test_llm_exhaustion_persistence_failure():
    # We want to mock authenticated_post to always throw or return 500
    with patch("worker.authenticated_post") as mock_post, \
         patch("worker.authenticated_get") as mock_get, \
         patch("worker.TASK_ID", "test_123"), \
         patch("worker.REPO_URL", "test"), \
         patch("worker.BACKEND_URL", "test"):
        
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {}
        mock_get.return_value = mock_get_response
        
        # Simulate network timeout then 503 then 502
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        mock_response_503.text = "Service Unavailable"
        
        mock_response_502 = MagicMock()
        mock_response_502.status_code = 502
        mock_response_502.text = "Bad Gateway"
        
        mock_post.side_effect = [
            httpx.TimeoutException("Connection timed out"),
            mock_response_503,
            mock_response_502
        ]
        
        # We need to simulate the worker catching LLMExhaustionError. 
        # The easiest way is to mock langgraph_app.astream to raise it.
        with patch("worker.langgraph_app.astream") as mock_astream, \
             patch("sys.exit") as mock_exit:
             
            mock_astream.side_effect = LLMExhaustionError("WAITING_FOR_LLM_CAPACITY", model="gpt", reset_time=60.0, last_error="Rate limit exceeded")
            mock_exit.side_effect = SystemExit
            
            # Disable asyncio.sleep so the test runs fast
            with patch("asyncio.sleep"):
                try:
                    await worker.run_worker()
                except SystemExit:
                    pass
                
            # It should have called sys.exit(1) because 3 attempts failed
            mock_exit.assert_called_with(1)
            # 1 call from initial pipeline_started event + 3 from the exhaustion retries
            assert mock_post.call_count == 4
