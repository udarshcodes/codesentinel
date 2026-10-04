import uuid
"""
Tests for api/routes.py — API endpoints for analyze, approve, and webhook.
"""

import os
import sys
import unittest
from unittest.mock import patch
import hmac
import hashlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app


@patch("api.routes.trigger_github_worker")
class TestApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_valid_repo_url(self, mock_worker):
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)
        self.assertIn("tasks", data)

    def test_invalid_repo_url(self, mock_worker):
        response = self.client.post(
            "/api/v1/analyze", json={"repo_url": "not-a-valid-url"}
        )
        self.assertEqual(response.status_code, 400)

    def test_backward_compat_route(self, mock_worker):
        response = self.client.post(
            "/api/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}
        )
        self.assertEqual(response.status_code, 200)

    def test_missing_repo_url(self, mock_worker):
        response = self.client.post("/api/v1/analyze", json={})
        self.assertEqual(response.status_code, 422)

    def test_approve_no_pipeline(self, mock_worker):
        # We must provide approval_token instead of admin_secret
        response = self.client.post(
            "/api/v1/approve/nonexistent-task",
            json={"decision": "approved", "approval_token": "some_token", "fix_id": "fix1", "approval_cycle_id": "cycle1"}
        )
        self.assertEqual(response.status_code, 404)

    def test_frontend_backend_contract(self, mock_worker):
        # 1. POST /api/v1/analyze
        res = self.client.post("/api/v1/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"})
        self.assertEqual(res.status_code, 200)
        task_id = res.json()["task_id"]
        
        # We need the tokens which are not returned directly in real life, but for testing we can fetch them from DB
        from api.job_manager import JobManager, DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT view_token FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
        self.assertIsNotNone(row)
        view_token = row[0]
        conn.close()
        
        # Override the db hashes with raw strings so we can test easily
        import hashlib
        raw_view = "view_123"
        raw_approval = "approval_123"
        hashed_view = hashlib.sha256(raw_view.encode()).hexdigest()
        hashed_approval = hashlib.sha256(raw_approval.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        import json
        initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": "cycle1"}
        conn.execute("UPDATE jobs SET view_token = ?, status = 'WAITING_FOR_APPROVAL', pipeline_state = ? WHERE task_id = ?", (hashed_view, json.dumps(initial_state), task_id))
        
        # Insert approval_credentials record
        from datetime import datetime, timezone, timedelta
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        conn.execute("INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), "cycle1", task_id, "fix1", hashed_approval, expires))
        
        conn.commit()
        conn.close()
        
        # 2. GET /api/v1/job/{task_id}/view
        res = self.client.get(f"/api/v1/job/{task_id}/view", headers={"Authorization": f"Bearer {raw_view}"})
        self.assertEqual(res.status_code, 200)
        view_data = res.json()
        self.assertIn("status", view_data)
        self.assertIn("repo_url", view_data)
        self.assertIn("last_sequence", view_data)
        self.assertNotIn("approval_token", view_data) # Ensure no creds leaked
        
        # 3. GET /api/v1/job/{task_id}/stream-capability
        res = self.client.get(f"/api/v1/job/{task_id}/stream-capability", headers={"Authorization": f"Bearer {raw_view}"})
        self.assertEqual(res.status_code, 200)
        capability = res.json()["capability"]
        
        # 4. (Skipped) GET /api/stream blocks TestClient since it's an infinite SSE stream.
        # We rely on test_sse_integration.py for this.
        
        # 5. POST /api/v1/approve/{task_id}
        res = self.client.post(f"/api/v1/approve/{task_id}", json={"decision": "approved", "approval_token": raw_approval, "fix_id": "fix1", "approval_cycle_id": "cycle1"})
        self.assertEqual(res.status_code, 200, res.text)

    def test_approve_invalid_decision(self, mock_worker):
        # Create job first so it doesn't fail with 404
        from api.job_manager import JobManager, DB_PATH
        JobManager.create_job("invalid-decision-task", "https://github.com/foo/bar")
        import hashlib
        hashed_token = hashlib.sha256(b"some_token").hexdigest()
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        # No longer using legacy approval_token on jobs table
        # We can just skip updating it, we test missing payload anyway.
        conn.close()

        response = self.client.post(
            "/api/v1/approve/invalid-decision-task",
            json={"decision": "maybe", "approval_token": "some_token", "fix_id": "fix1", "approval_cycle_id": "cycle1"}
        )
        self.assertEqual(response.status_code, 422) # Pydantic validation fails

    @patch.dict(os.environ, clear=True)
    def test_webhook_no_event_header(self, mock_worker):
        # Ensure GITHUB_WEBHOOK_SECRET is cleared
        if "GITHUB_WEBHOOK_SECRET" in os.environ:
            del os.environ["GITHUB_WEBHOOK_SECRET"]
        response = self.client.post("/api/v1/webhook/github", json={})
        data = response.json()
        self.assertEqual(data.get("status"), "ignored")

    @patch.dict(os.environ, clear=True)
    def test_webhook_push_to_main(self, mock_worker):
        if "GITHUB_WEBHOOK_SECRET" in os.environ:
            del os.environ["GITHUB_WEBHOOK_SECRET"]
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)

    @patch.dict(os.environ, clear=True)
    def test_webhook_push_to_feature_branch_ignored(self, mock_worker):
        if "GITHUB_WEBHOOK_SECRET" in os.environ:
            del os.environ["GITHUB_WEBHOOK_SECRET"]
        payload = {
            "ref": "refs/heads/feature/something",
            "after": "abc123",
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github", json=payload, headers={"X-GitHub-Event": "push"}
        )
        data = response.json()
        self.assertEqual(data["status"], "ignored")

    @patch.dict(os.environ, clear=True)
    def test_webhook_pr_opened(self, mock_worker):
        if "GITHUB_WEBHOOK_SECRET" in os.environ:
            del os.environ["GITHUB_WEBHOOK_SECRET"]
        payload = {
            "action": "opened",
            "pull_request": {"head": {"sha": "def456"}},
            "repository": {"html_url": "https://github.com/octocat/Hello-World"},
        }
        response = self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        data = response.json()
        self.assertEqual(data["status"], "accepted")

    def test_webhook_signature_verification(self, mock_worker):
        secret = "test_secret_123"
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
            payload = json.dumps(
                {
                    "ref": "refs/heads/main",
                    "after": "abc123",
                    "repository": {
                        "html_url": "https://github.com/octocat/Hello-World"
                    },
                }
            ).encode()

            sig = (
                "sha256="
                + hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
            )

            response = self.client.post(
                "/api/v1/webhook/github",
                content=payload,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
            self.assertEqual(response.status_code, 200)

    def test_webhook_missing_signature_rejected(self, mock_worker):
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "some_secret"}):
            response = self.client.post(
                "/api/v1/webhook/github",
                json={"repository": {"html_url": "https://github.com/foo/bar"}},
                headers={"X-GitHub-Event": "push"},
            )
            self.assertEqual(response.status_code, 403)

    def test_health(self, mock_worker):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch("api.routes.httpx.AsyncClient")
    def test_analyze_multi_repo_empty(self, mock_client, mock_worker):
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get.return_value.status_code = 404
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/nonexistentorg/*"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Could not find any active public repositories", response.json()["detail"]
        )


    @patch("api.job_manager.JobManager.add_worker_event")
    @patch("api.job_manager.JobManager.get_job")
    def test_worker_webhook_signature_verification(self, mock_get_job, mock_add_worker_event, mock_worker):
        mock_add_worker_event.return_value = (True, 1)
        secret = "worker_secret_123"
        task_id = "test-task"
        attempt_id = "test-attempt"
        mock_get_job.return_value = {"status": "DISPATCHING", "worker_attempt_id": attempt_id, "repo_url": "foo"}
        with patch.dict(os.environ, {"WORKER_WEBHOOK_SECRET": secret}):
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            payload_dict = {
                "sequence": 1,
                "status": "QUEUED",
                "event": "started",
                "data": {},
                "timestamp": now_iso
            }
            payload_bytes = json.dumps(payload_dict).encode()
            
            # Construct signature: METHOD:PATH:TASK_ID:TIMESTAMP:ATTEMPT_ID:COMMIT_SHA:REPO_URL:BODY
            timestamp_epoch = str(datetime.now(timezone.utc).timestamp())
            msg = f"POST:/api/v1/job/{task_id}/event:{task_id}:{timestamp_epoch}:{attempt_id}::foo:".encode() + payload_bytes
            sig = "sha256=" + hmac.HMAC(secret.encode(), msg, hashlib.sha256).hexdigest()
            
            response = self.client.post(
                f"/api/v1/job/{task_id}/event",
                content=payload_bytes,
                headers={
                    "X-Worker-Signature": sig,
                    "X-Timestamp": timestamp_epoch,
                    "X-Worker-Attempt-Id": attempt_id,
                    "X-Repo-Url": "foo",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 200, response.text

    @patch("api.job_manager.JobManager.add_worker_event")
    @patch("api.job_manager.JobManager.get_job")
    def test_worker_webhook_replay_protection(self, mock_get_job, mock_add_worker_event, mock_worker):
        secret = "worker_secret_123"
        task_id = "test-task"
        attempt_id = "test-attempt"
        mock_get_job.return_value = {"status": "DISPATCHING", "worker_attempt_id": attempt_id, "repo_url": "foo"}
        with patch.dict(os.environ, {"WORKER_WEBHOOK_SECRET": secret}):
            # Use an expired timestamp (10 minutes ago)
            from datetime import datetime, timedelta, timezone
            expired_time = str((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
            
            payload_dict = {
                "sequence": 1,
                "status": "QUEUED",
                "event": "started",
                "data": {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            payload_bytes = json.dumps(payload_dict).encode()
            
            msg = f"POST:/api/v1/job/{task_id}/event:{task_id}:{expired_time}:{attempt_id}::foo:".encode() + payload_bytes
            sig = "sha256=" + hmac.HMAC(secret.encode(), msg, hashlib.sha256).hexdigest()
            
            response = self.client.post(
                f"/api/v1/job/{task_id}/event",
                content=payload_bytes,
                headers={
                    "X-Worker-Signature": sig,
                    "X-Timestamp": expired_time,
                    "X-Worker-Attempt-Id": attempt_id,
                    "X-Repo-Url": "foo",
                    "Content-Type": "application/json",
                },
            )
            # Should fail replay protection
            assert response.status_code == 403, response.text
            self.assertIn("Expired timestamp", response.json()["detail"])

    def test_worker_webhook_missing_signature(self, mock_worker):
        secret = "worker_secret_123"
        task_id = "test-task"
        with patch.dict(os.environ, {"WORKER_WEBHOOK_SECRET": secret}):
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            payload_dict = {
                "sequence": 1,
                "status": "QUEUED",
                "event": "started",
                "data": {},
                "timestamp": now_iso
            }
            response = self.client.post(
                f"/api/v1/job/{task_id}/event",
                json=payload_dict
            )
            self.assertEqual(response.status_code, 403)
            self.assertIn("Missing X-Worker-Signature", response.json()["detail"])

    def test_admin_auth_flow(self, mock_worker):
        secret = "admin_test_secret"
        with patch.dict(os.environ, {"ADMIN_SECRET": secret}):
            response = self.client.post("/api/v1/admin/login", json={"secret": secret})
            self.assertEqual(response.status_code, 200)
            self.assertIn("admin_session", response.cookies)
            session_id = response.cookies["admin_session"]
            self.assertNotEqual(session_id, secret)

            # Test Telemetry with Cookie
            self.client.cookies = {"admin_session": session_id}
            response2 = self.client.get("/api/v1/admin/telemetry")
            self.assertEqual(response2.status_code, 200)
            self.assertIn("overview", response2.json())

            response3 = self.client.post("/api/v1/admin/logout")
            self.assertEqual(response3.status_code, 200)
            # The cookie should be deleted (set to empty or max-age 0)
            
            # Test Telemetry without Cookie
            response4 = self.client.get("/api/v1/admin/telemetry")
            self.assertEqual(response4.status_code, 401)

    def test_approve_sets_waiting_for_dispatch(self, mock_worker):
        # Create job
        from api.job_manager import JobManager, DB_PATH
        JobManager.create_job("approval-task", "https://github.com/foo/bar")
        
        import hashlib
        import json
        hashed_token = hashlib.sha256(b"some_token").hexdigest()
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": "cycle1"}
        conn.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL', pipeline_state = ? WHERE task_id = ?", (json.dumps(initial_state), "approval-task"))
        
        from datetime import datetime, timezone, timedelta
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        conn.execute("INSERT INTO approval_credentials (credential_id, approval_cycle_id, task_id, fix_id, token_hash, status, expires_at) VALUES (?, ?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), "cycle1", "approval-task", "fix1", hashed_token, expires))
        
        conn.commit()
        conn.close()
    
        # Call approve
        response = self.client.post(
            "/api/v1/approve/approval-task",
            json={"decision": "approved", "approval_token": "some_token", "fix_id": "fix1", "approval_cycle_id": "cycle1"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        
        # Verify status changed to WAITING_FOR_DISPATCH
        job = JobManager.get_job("approval-task")
        self.assertEqual(job["status"], "WAITING_FOR_DISPATCH")
        
        # Ensure trigger_github_worker was NOT called synchronously by approval
        mock_worker.assert_not_called()

    def test_analyze_creates_view_token(self, mock_worker):
        response = self.client.post(
            "/api/v1/analyze",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("view_token", data)
        self.assertTrue(len(data["view_token"]) > 10)

    def test_worker_state_webhook_rejects_pending_approval(self, mock_worker):
        # Create job
        from api.job_manager import JobManager, DB_PATH
        JobManager.create_job("test-webhook-auth", "https://github.com/foo/bar")
        
        import json
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        # Set to WAITING_FOR_APPROVAL with an active worker_attempt_id
        initial_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": "cycle1"}
        conn.execute("UPDATE jobs SET status = 'WAITING_FOR_APPROVAL', pipeline_state = ?, worker_attempt_id = 'worker1' WHERE task_id = ?", (json.dumps(initial_state), "test-webhook-auth"))
        conn.commit()
        conn.close()

        # Generate HMAC Signature
        from datetime import datetime, timezone
        timestamp = str(datetime.now(timezone.utc).timestamp())
        secret = os.getenv("WORKER_WEBHOOK_SECRET", "dummy_secret")
        # Ensure dummy_secret is in env if it wasn't
        if "WORKER_WEBHOOK_SECRET" not in os.environ:
            os.environ["WORKER_WEBHOOK_SECRET"] = secret

        payload_dict = {"status": "WAITING_FOR_DISPATCH", "pipeline_state": {"awaiting_approval": False}}
        payload_bytes = json.dumps(payload_dict).encode()
        msg = f"POST:/api/v1/job/test-webhook-auth/state:test-webhook-auth:{timestamp}:worker1::https://github.com/foo/bar:".encode() + payload_bytes
        sig = "sha256=" + hmac.HMAC(secret.encode(), msg, hashlib.sha256).hexdigest()

        # Worker attempts to update state
        response = self.client.post(
            "/api/v1/job/test-webhook-auth/state",
            content=payload_bytes,
            headers={
                "X-Worker-Attempt-Id": "worker1", 
                "X-Repo-Url": "https://github.com/foo/bar",
                "X-Worker-Signature": sig,
                "X-Timestamp": timestamp,
                "Content-Type": "application/json"
            }
        )
        
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("human approval is pending", response.text)
        
        # Verify job is unchanged
        job = JobManager.get_job("test-webhook-auth")
        self.assertEqual(job["status"], "WAITING_FOR_APPROVAL")
        self.assertEqual(job["pipeline_state"]["awaiting_approval"], True)

    def test_worker_state_webhook_legitimate_flow(self, mock_worker):
        # Create job
        from api.job_manager import JobManager, DB_PATH
        JobManager.create_job("test-webhook-legit", "https://github.com/foo/bar")
        
        import sqlite3
        import json
        conn = sqlite3.connect(DB_PATH)
        # Set to RUNNING with an active worker_attempt_id
        conn.execute("UPDATE jobs SET status = 'RUNNING', worker_attempt_id = 'worker1' WHERE task_id = ?", ("test-webhook-legit",))
        conn.commit()
        conn.close()

        # Generate HMAC Signature
        from datetime import datetime, timezone
        timestamp = str(datetime.now(timezone.utc).timestamp())
        secret = os.getenv("WORKER_WEBHOOK_SECRET", "dummy_secret")
        if "WORKER_WEBHOOK_SECRET" not in os.environ:
            os.environ["WORKER_WEBHOOK_SECRET"] = secret
            
        new_state = {"awaiting_approval": True, "approval_state": "pending", "approval_decision": None, "approval_payload": {"fix_id": "fix1"}, "repair_plan": [{"fix_id": "fix1", "status": "pending"}], "approval_cycle_id": "cycle1"}
        payload_dict = {"status": "WAITING_FOR_APPROVAL", "pipeline_state": new_state}
        payload_bytes = json.dumps(payload_dict).encode()
        msg = f"POST:/api/v1/job/test-webhook-legit/state:test-webhook-legit:{timestamp}:worker1::https://github.com/foo/bar:".encode() + payload_bytes
        sig = "sha256=" + hmac.HMAC(secret.encode(), msg, hashlib.sha256).hexdigest()

        # Worker legitimately transitions to WAITING_FOR_APPROVAL
        response = self.client.post(
            "/api/v1/job/test-webhook-legit/state",
            content=payload_bytes,
            headers={
                "X-Worker-Attempt-Id": "worker1", 
                "X-Repo-Url": "https://github.com/foo/bar",
                "X-Worker-Signature": sig,
                "X-Timestamp": timestamp,
                "Content-Type": "application/json"
            }
        )
        
        self.assertEqual(response.status_code, 200, response.text)
        
        # Verify job updated successfully
        job = JobManager.get_job("test-webhook-legit")
        self.assertEqual(job["status"], "WAITING_FOR_APPROVAL")
        self.assertEqual(job["pipeline_state"]["awaiting_approval"], True)

if __name__ == "__main__":
    unittest.main()
