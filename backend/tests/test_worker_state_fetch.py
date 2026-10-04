import pytest
from unittest.mock import patch, MagicMock
import httpx
import worker

@pytest.mark.asyncio
async def test_worker_state_fetch_retry():
    # Mock the get call to fail twice then succeed
    with patch("worker.authenticated_get") as mock_get, \
         patch("worker.TASK_ID", "test_123"), \
         patch("worker.REPO_URL", "test"), \
         patch("worker.BACKEND_URL", "test"):
        
        mock_response_502 = MagicMock()
        mock_response_502.status_code = 502
        
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"pipeline_state": {"foo": "bar"}}
        
        mock_get.side_effect = [
            httpx.TimeoutException("Timeout"),
            mock_response_502,
            mock_response_200
        ]
        
        with patch("asyncio.sleep"), \
             patch("sys.exit") as mock_exit, \
             patch("worker.post_event"), \
             patch("worker.heartbeat_loop"), \
             patch("worker.langgraph_app.astream") as mock_astream:
            
            async def fake_astream(*args, **kwargs):
                if False:
                    yield
            
            mock_astream.return_value = fake_astream()
            mock_exit.side_effect = SystemExit
            
            try:
                await worker.run_worker()
            except SystemExit:
                pass
            
            assert mock_get.call_count == 3
            mock_exit.assert_not_called()
