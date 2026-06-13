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

# We will mount the static assets once the admin_dashboard is built
try:
    app.mount("/admin/assets", StaticFiles(directory="admin_dashboard/dist/assets"), name="admin-assets")
except RuntimeError:
    print("[Warning] admin_dashboard/dist/assets not found yet. Build the React app first.")

@app.get("/admin")
def admin_dashboard():
    if os.path.exists("admin_dashboard/dist/index.html"):
        return FileResponse("admin_dashboard/dist/index.html")
    return {"error": "Dashboard not built yet. Run npm run build in admin_dashboard."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)