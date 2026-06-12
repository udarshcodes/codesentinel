from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from api.sse import router as sse_router

app = FastAPI(title="Multi-Agent Bug Detection System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow Vite local dev server
