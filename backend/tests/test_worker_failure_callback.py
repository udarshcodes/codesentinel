import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
import pytest
from tools.worker_failure_callback import report_failure


def test_failure_callback_signs_body_without_worker_dependencies():
    env = {"TASK_ID": "task-1", "WORKER_ATTEMPT_ID": "attempt-1", "WORKER_WEBHOOK_SECRET": "test-secret",
           "BACKEND_URL": "https://backend.example", "REPO_URL": "https://github.com/test/repo", "COMMIT_SHA": "abc"}
    response = MagicMock()
    response.__enter__.return_value.status = 200
    with patch('tools.worker_failure_callback.urlopen', return_value=response) as send:
        assert report_failure(env) == 200
    request = send.call_args.args[0]
    body = json.loads(request.data)
    assert body['status'] == 'FAILED'
    timestamp = request.get_header('X-timestamp')
    prefix = f"POST:/api/v1/job/task-1/event:task-1:{timestamp}:attempt-1:abc:https://github.com/test/repo:"
    expected = 'sha256=' + hmac.new(b'test-secret', prefix.encode() + request.data, hashlib.sha256).hexdigest()
    assert request.get_header('X-worker-signature') == expected
    assert b'test-secret' not in request.data


def test_failure_callback_rejects_non_https_before_transmission():
    env = {"TASK_ID": "task-1", "WORKER_ATTEMPT_ID": "attempt-1", "WORKER_WEBHOOK_SECRET": "test-secret", "BACKEND_URL": "http://example.invalid"}
    with patch('tools.worker_failure_callback.urlopen') as send, pytest.raises(ValueError):
        report_failure(env)
    send.assert_not_called()
