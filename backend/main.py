import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from limiter import limiter
from api.routes import router as api_router
from api.sse import router as sse_router
from tools.key_dispatcher import get_usage_report
from state import metrics
import config


import logging

class CapabilityScrubber(logging.Filter):
    def filter(self, record):
        if record.args and len(record.args) > 2:
            try:
                url = record.args[2]
                if "capability=" in url:
                    import re
                    scrubbed = re.sub(r'capability=[^&]+', 'capability=***', url)
                    args_list = list(record.args)
                    args_list[2] = scrubbed
                    record.args = tuple(args_list)
            except Exception:
                pass
        return True

logging.getLogger("uvicorn.access").addFilter(CapabilityScrubber())

@asynccontextmanager
async def lifespan(app):
    if os.getenv("ENVIRONMENT") == "production":
        if not os.getenv("WORKER_WEBHOOK_SECRET"):
            raise RuntimeError("FATAL: WORKER_WEBHOOK_SECRET is required in production environment.")
        if not os.getenv("GITHUB_WEBHOOK_SECRET"):
            raise RuntimeError("FATAL: GITHUB_WEBHOOK_SECRET is required in production environment.")
        
    if not config.GROQ_API_KEYS:
        print("[WARNING] GROQ_API_KEYS not set! LLM analysis will fail.")
    if not os.getenv("GITHUB_TOKEN"):
        print("[WARNING] GITHUB_TOKEN not set!")
    import tempfile

    temp_repo = os.getenv(
        "TEMP_REPO_PATH", os.path.join(tempfile.gettempdir(), "repos")
    )
    os.makedirs(temp_repo, exist_ok=True)
    
    task = asyncio.create_task(resume_waiting_jobs_loop())
    yield
    task.cancel()


async def resume_waiting_jobs_loop():
    import asyncio
    from api.job_manager import JobManager
    from api.routes import trigger_github_worker
    while True:
        try:
            ready_jobs = JobManager.get_waiting_jobs_ready()
            for job in ready_jobs:
                if job.get("status") in ("RUNNING", "DISPATCHING"):
                    worker_attempt_id = JobManager.recover_stale_worker_claim(job["task_id"])
                else:
                    worker_attempt_id = JobManager.claim_waiting_job(job["task_id"])
                    
                if worker_attempt_id:
                    print(f"[AutoResume] Resuming/Dispatching job {job['task_id']} ...")
                    try:
                        await trigger_github_worker(job["task_id"], job["repo_url"], job.get("commit_sha"), worker_attempt_id)
                    except Exception as e:
                        print(f"[AutoResume] Dispatch failed for {job['task_id']}: {e}")
                        JobManager.record_dispatch_failure(job["task_id"], str(e), worker_attempt_id)
        except Exception as e:
            print(f"[AutoResume] Error in loop: {e}")
        await asyncio.sleep(60)

app = FastAPI(title="CodeSentinel", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins_str = os.getenv("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_str.replace(",", " ").split() if o.strip()]

safe_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://salmon-ground-0362fac00.7.azurestaticapps.net",
    "https://codesentinel.udarshgoyal.xyz"
]

safe_origins.extend([o for o in _cors_origins if o != "*"])
safe_origins = list(set(safe_origins))


app.add_middleware(
    CORSMiddleware,
    allow_origins=safe_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(sse_router, prefix="/api")


@app.get("/")
def root():
    return {"message": "System Operational"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/metrics")
def get_metrics():
    return JSONResponse(
        content={
            "queue_depth": metrics.queue_depth,
            "scan_duration_ms": metrics.scan_duration_ms,
            "failed_jobs": metrics.failed_jobs,
            "completed_jobs": metrics.completed_jobs,
        }
    )


@app.get("/live")
def live_check():
    return {"status": "live"}


@app.get("/ready")
def ready_check():
    from api.job_manager import JobManager
    if not JobManager.check_database_ready():
        raise HTTPException(status_code=503, detail="Database not ready")
    
    if os.getenv("ENVIRONMENT") == "production" and not os.getenv("WORKER_WEBHOOK_SECRET"):
        raise HTTPException(status_code=503, detail="Configuration not ready")
        
    return {"status": "ready"}


if not os.getenv("ADMIN_SECRET", ""):
    print(
        "[WARNING] ADMIN_SECRET not set! The /api/v1/admin/login and /api/v1/admin/telemetry endpoints will reject all requests."
    )


# Admin endpoints are now handled in api.routes

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
