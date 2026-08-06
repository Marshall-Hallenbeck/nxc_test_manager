"""MCP server exposing the test-run API to AI coding agents.

Tools are generated from the FastAPI routes, so the REST API stays the single
source of truth. Destructive and machine-only routes are excluded.
"""
import asyncio
import logging

from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.openapi import MCPType, RouteMap

from app.config import settings
from app.database import SessionLocal
from app.models.test_run import TestRun, TestRunStatus

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = (TestRunStatus.COMPLETED, TestRunStatus.FAILED, TestRunStatus.CANCELLED)

ROUTE_MAPS = [
    # Run history is not the agent's to destroy.
    RouteMap(methods=["DELETE"], mcp_type=MCPType.EXCLUDE),
    # GitHub-only endpoint; needs an HMAC signature and has no agent use.
    RouteMap(pattern=r"^/webhooks/.*", mcp_type=MCPType.EXCLUDE),
    # Liveness endpoints carry no information an agent acts on.
    RouteMap(pattern=r"^/$", mcp_type=MCPType.EXCLUDE),
    RouteMap(pattern=r"^/health$", mcp_type=MCPType.EXCLUDE),
    RouteMap(mcp_type=MCPType.TOOL),
]


def read_run_state(test_run_id: int) -> dict:
    """Read the current state of a run as a plain dict."""
    db = SessionLocal()
    try:
        run = db.get(TestRun, test_run_id)
        if not run:
            raise ToolError(f"Test run {test_run_id} not found")
        return {
            "id": run.id,
            "pr_number": run.pr_number,
            "branch": run.branch,
            "status": str(run.status),
            "sub_status": run.sub_status,
            "total_tests": run.total_tests,
            "passed_tests": run.passed_tests,
            "failed_tests": run.failed_tests,
            "failures": [
                {
                    "test_name": r.test_name,
                    "target_host": r.target_host,
                    "error_message": r.error_message,
                    "output": r.output,
                }
                for r in run.results
                if r.status == "failed"
            ],
        }
    finally:
        db.close()


def build_mcp(app: FastAPI) -> FastMCP:
    """Build the MCP server from an already-configured FastAPI app.

    Tool names come from each route's explicit `operation_id`, so renaming a
    route handler cannot change them.
    """
    mcp = FastMCP.from_fastapi(
        app=app,
        name="nxc-test-manager",
        route_maps=ROUTE_MAPS,
    )

    @mcp.tool
    async def wait_for_test_run(
        test_run_id: int,
        poll_seconds: int = 10,
        timeout_seconds: int = settings.container_timeout + 300,
    ) -> dict:
        """Block until a test run finishes, then return its result and failures.

        Polls until the run reaches completed, failed, or cancelled. Use this
        after start_test_run instead of calling get_test_run in a loop.
        """
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            state = await asyncio.to_thread(read_run_state, test_run_id)
            if state["status"] in TERMINAL_STATUSES:
                return state
            if asyncio.get_running_loop().time() >= deadline:
                raise ToolError(
                    f"Test run {test_run_id} still {state['status']} after {timeout_seconds}s"
                )
            await asyncio.sleep(poll_seconds)

    return mcp
