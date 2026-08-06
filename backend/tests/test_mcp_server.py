"""Tests for the MCP server mounted at /mcp."""
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app import mcp_server
from app.main import app as fastapi_app
from app.main import mcp
from app.mcp_server import build_mcp
from app.models.test_result import TestResult
from app.models.test_run import TestRun, TestRunStatus

EXPECTED_TOOLS = {
    "cancel_test_run",
    "compare_test_runs",
    "get_test_run",
    "get_test_run_logs",
    "list_test_runs",
    "rerun_test_run",
    "search_pull_requests",
    "start_ai_review",
    "start_test_run",
    "wait_for_test_run",
}


def make_run(db, status=TestRunStatus.RUNNING, **kwargs):
    run = TestRun(target_hosts="10.0.0.1", status=status, **kwargs)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


class TestToolSurface:
    @pytest.mark.asyncio
    async def test_exposes_exactly_the_intended_tools(self):
        async with Client(mcp) as c:
            names = {t.name for t in await c.list_tools()}
        assert names == EXPECTED_TOOLS

    @pytest.mark.asyncio
    async def test_no_tool_can_delete_a_run(self):
        """DELETE /api/runs/{id} is excluded: run history is not the agent's to destroy."""
        async with Client(mcp) as c:
            names = {t.name for t in await c.list_tools()}
        assert not any("delete" in n for n in names)

    @pytest.mark.asyncio
    async def test_webhook_route_is_not_exposed(self):
        async with Client(mcp) as c:
            names = {t.name for t in await c.list_tools()}
        assert not any("webhook" in n for n in names)


class TestToolNameStability:
    """Tool names must come from explicit operation ids, not handler names.

    FastAPI derives an operation id from the handler name plus path plus method
    when none is given. Under that default, renaming a handler silently renames
    the agent-facing tool.
    """

    def test_every_run_route_declares_an_explicit_operation_id(self):
        missing = [
            r.path
            for r in fastapi_app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/api/runs") and r.operation_id is None
        ]
        assert missing == []

    @pytest.mark.asyncio
    async def test_tool_name_follows_operation_id_not_handler_name(self):
        probe = FastAPI()

        @probe.get("/thing", operation_id="stable_tool_name")
        def a_handler_name_nobody_should_depend_on():
            return {}

        async with Client(build_mcp(probe)) as c:
            names = {t.name for t in await c.list_tools()}

        assert "stable_tool_name" in names
        assert not any("a_handler_name" in n for n in names)


class TestWaitForTestRun:
    @pytest.mark.asyncio
    async def test_returns_immediately_when_already_terminal(self, db):
        run = make_run(db, status=TestRunStatus.COMPLETED, total_tests=3, passed_tests=2, failed_tests=1)
        db.add(TestResult(test_run_id=run.id, test_name="smb_shares", target_host="10.0.0.1", status="failed", error_message="boom"))
        db.add(TestResult(test_run_id=run.id, test_name="smb_users", target_host="10.0.0.1", status="passed"))
        db.commit()

        async with Client(mcp) as c:
            result = await c.call_tool("wait_for_test_run", {"test_run_id": run.id})

        data = result.data
        assert data["status"] == "completed"
        assert data["passed_tests"] == 2
        assert data["failed_tests"] == 1
        assert [f["test_name"] for f in data["failures"]] == ["smb_shares"]
        assert data["failures"][0]["error_message"] == "boom"

    @pytest.mark.asyncio
    async def test_polls_until_status_becomes_terminal(self, db, monkeypatch):
        run = make_run(db, status=TestRunStatus.RUNNING)
        states = [
            {"id": run.id, "status": "queued", "failures": []},
            {"id": run.id, "status": "running", "failures": []},
            {"id": run.id, "status": "failed", "failures": []},
        ]
        monkeypatch.setattr(mcp_server, "read_run_state", lambda run_id: states.pop(0))

        async with Client(mcp) as c:
            result = await c.call_tool("wait_for_test_run", {"test_run_id": run.id, "poll_seconds": 0})

        assert result.data["status"] == "failed"
        assert states == []

    @pytest.mark.asyncio
    async def test_cancelled_counts_as_terminal(self, db):
        run = make_run(db, status=TestRunStatus.CANCELLED)

        async with Client(mcp) as c:
            result = await c.call_tool("wait_for_test_run", {"test_run_id": run.id, "poll_seconds": 0})

        assert result.data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_missing_run_raises(self):
        async with Client(mcp) as c:
            with pytest.raises(ToolError, match="not found"):
                await c.call_tool("wait_for_test_run", {"test_run_id": 999999})

    @pytest.mark.asyncio
    async def test_timeout_raises_instead_of_returning_a_non_terminal_result(self, db, monkeypatch):
        run = make_run(db, status=TestRunStatus.RUNNING)
        monkeypatch.setattr(mcp_server, "read_run_state", lambda run_id: {"id": run_id, "status": "running", "failures": []})

        async with Client(mcp) as c:
            with pytest.raises(ToolError, match="still running"):
                await c.call_tool("wait_for_test_run", {"test_run_id": run.id, "poll_seconds": 0, "timeout_seconds": 0})


class TestMcpMount:
    def test_mcp_endpoint_is_mounted_and_handshakes(self, client):
        """Smoke test: the /mcp mount answers a JSON-RPC initialize."""
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 200
        assert "nxc-test-manager" in response.text

    def test_rest_api_still_serves_alongside_mcp(self, client):
        assert client.get("/health").status_code == 200
        assert client.get("/api/runs").status_code == 200
