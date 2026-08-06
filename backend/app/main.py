"""Main FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .api import test_runs, websocket, webhooks
from .mcp_server import build_mcp
from .services import ai_review


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ai_review.check_claude_available()
    # mcp_app is defined below; it exists by the time startup runs. Its lifespan
    # manages MCP session state and must run for the /mcp mount to work.
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(
    title="NetExec Test Manager API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000", "http://127.0.0.1:9000", "http://localhost:3000", "http://frontend:3000"],
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

# Built from the routes above, so it must come after every include_router call.
mcp = build_mcp(app)
mcp_app = mcp.http_app(path="/")
app.mount("/mcp", mcp_app)
