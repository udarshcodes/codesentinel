import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import router as api_router
from api.sse import router as sse_router
from tools.key_dispatcher import get_usage_report

app = FastAPI(title="Multi-Agent Bug Detection System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow Vite local dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(sse_router, prefix="/api")

@app.get("/")
def root():
    return {"message": "System Operational"}

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "asdfgh")

@app.get("/admin/token-usage")
def token_usage(x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return get_usage_report()

# Mount the entire dist folder for admin dashboard
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
    uvicorn.run(app, host="0.0.0.0", port=8000)