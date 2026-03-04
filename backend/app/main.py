"""Main FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .api import test_runs, websocket, webhooks
from .services import ai_review


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ai_review.check_claude_available()
    yield


app = FastAPI(
    title="NetExec Test Manager API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3333", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "NetExec Test Manager API", "status": "running"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "claude_available": ai_review.CLAUDE_AVAILABLE,
        "claude_unavailable_reason": ai_review.CLAUDE_UNAVAILABLE_REASON,
    }


app.include_router(test_runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
