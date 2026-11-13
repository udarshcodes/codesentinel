"""Standard-library-only failure reporting, including dependency/import failures."""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def report_failure(environment=None):
    env = os.environ if environment is None else environment
    task = env.get("TASK_ID", "")
    attempt = env.get("WORKER_ATTEMPT_ID", "")
    secret = env.get("WORKER_WEBHOOK_SECRET", "")
    base = env.get("BACKEND_URL", "").rstrip("/")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", task) or not attempt or not secret:
        raise ValueError("Authenticated failure callback configuration is incomplete.")
    if urlsplit(base).scheme != "https":
        raise ValueError("Worker failure callbacks require HTTPS.")
    repo, commit = env.get("REPO_URL", ""), env.get("COMMIT_SHA", "")
    path = f"/api/v1/job/{task}/event"
    now = datetime.now(timezone.utc)
    timestamp = str(now.timestamp())
    payload = {"status": "FAILED", "event": "pipeline_error", "worker_attempt_id": attempt,
               "timestamp": now.isoformat(), "data": {"error": "Worker workflow failed. See its GitHub Actions run for startup or execution diagnostics."}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    signed = f"POST:{path}:{task}:{timestamp}:{attempt}:{commit}:{repo}:".encode() + body
    headers = {"Content-Type": "application/json", "X-Worker-Attempt-Id": attempt, "X-Repo-Url": repo,
               "X-Timestamp": timestamp, "X-Worker-Signature": "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()}
    if commit:
        headers["X-Commit-Sha"] = commit
    try:
        with urlopen(Request(base + path, data=body, headers=headers, method="POST"), timeout=10) as response:
            return response.status
    except HTTPError as error:
        if error.code in (409, 410):
            return error.code  # Already terminal/stale: never bypass the backend fence.
        raise


if __name__ == "__main__":
    try:
        print("Failure callback HTTP status:", report_failure())
    except Exception as error:
        print("Unable to report workflow failure:", type(error).__name__)
        raise SystemExit(1)
