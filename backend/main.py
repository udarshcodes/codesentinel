import os
import shutil
from contextlib import asynccontextmanager
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from api.routes import router as api_router
from api.sse import router as sse_router
from tools.key_dispatcher import get_usage_report
from state import metrics

@asynccontextmanager
async def lifespan(app):
    # --- Startup ---
    if not os.getenv("GROQ_API_KEY"):
        print("[WARNING] GROQ_API_KEY not set!")
    if not os.getenv("GITHUB_TOKEN"):
        print("[WARNING] GITHUB_TOKEN not set!")
    if not shutil.which("semgrep"):
        raise RuntimeError("CRITICAL: semgrep not found in PATH")
    if not shutil.which("bandit"):
        raise RuntimeError("CRITICAL: bandit not found in PATH")
    import tempfile
    temp_repo = os.getenv("TEMP_REPO_PATH", os.path.join(tempfile.gettempdir(), "repos"))
    os.makedirs(temp_repo, exist_ok=True)
    if not os.access(temp_repo, os.W_OK):
        raise RuntimeError(f"CRITICAL: {temp_repo} is not writable")
    yield
    # --- Shutdown (cleanup if needed) ---

app = FastAPI(title="Multi-Agent Bug Detection System", lifespan=lifespan)

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
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
    return JSONResponse(content={
        "queue_depth": metrics.queue_depth,
        "scan_duration_ms": metrics.scan_duration_ms,
        "failed_jobs": metrics.failed_jobs,
        "completed_jobs": metrics.completed_jobs
    })

@app.get("/live")
def live_check():
    return {"status": "live"}

@app.get("/ready")
def ready_check():
    if not shutil.which("semgrep") or not shutil.which("bandit"):
        raise HTTPException(status_code=503, detail="Required SAST tools missing")
    return {"status": "ready"}



ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

@app.get("/admin/token-usage")
def token_usage(x_admin_token: str = Header(None)):
    if not ADMIN_SECRET or x_admin_token != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return get_usage_report()

# Mount the admin dashboard (StaticFiles with html=True handles index.html automatically)
try:
    if os.path.exists("admin_dashboard/dist"):
        app.mount("/admin", StaticFiles(directory="admin_dashboard/dist", html=True), name="admin")
    else:
        @app.get("/admin")
        def admin_dashboard():
            return {"error": "Dashboard not built yet. Run npm run build in admin_dashboard."}
except Exception as e:
    print(f"[Warning] Error mounting admin dashboard: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)