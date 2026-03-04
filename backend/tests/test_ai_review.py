"""Tests for AI review service — Claude CLI probe, prompt building, and review endpoint guard."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from app.services import ai_review


class TestCheckClaudeAvailable:
    """Tests for the startup probe that checks Claude CLI auth status."""

    def setup_method(self):
        """Reset module-level state before each test."""
        ai_review.CLAUDE_AVAILABLE = False
        ai_review.CLAUDE_UNAVAILABLE_REASON = ""

    @patch("app.services.ai_review.subprocess.run")
    def test_authenticated(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"loggedIn": true}', stderr=""
        )
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is True
        assert ai_review.CLAUDE_UNAVAILABLE_REASON == ""

    @patch("app.services.ai_review.subprocess.run")
    def test_not_authenticated(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"loggedIn": false}', stderr=""
        )
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is False
        assert ai_review.CLAUDE_UNAVAILABLE_REASON == "Claude CLI not authenticated"

    @patch("app.services.ai_review.subprocess.run")
    def test_cli_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is False
        assert ai_review.CLAUDE_UNAVAILABLE_REASON == "Claude CLI not installed"

    @patch("app.services.ai_review.subprocess.run")
    def test_cli_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is False
        assert "timed out" in ai_review.CLAUDE_UNAVAILABLE_REASON

    @patch("app.services.ai_review.subprocess.run")
    def test_cli_nonzero_exit(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="some error"
        )
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is False
        assert "exit 1" in ai_review.CLAUDE_UNAVAILABLE_REASON

    @patch("app.services.ai_review.subprocess.run")
    def test_cli_invalid_json(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json at all", stderr=""
        )
        ai_review.check_claude_available()
        assert ai_review.CLAUDE_AVAILABLE is False
        assert "invalid JSON" in ai_review.CLAUDE_UNAVAILABLE_REASON

    @patch("app.services.ai_review.subprocess.run")
    def test_strips_claudecode_env(self, mock_run):
        """Probe should remove CLAUDECODE from env to avoid nested session error."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"loggedIn": true}', stderr=""
        )
        with patch.dict("os.environ", {"CLAUDECODE": "1"}):
            ai_review.check_claude_available()
        call_env = mock_run.call_args.kwargs["env"]
        assert "CLAUDECODE" not in call_env


class TestBuildEnv:
    def test_strips_claudecode(self):
        with patch.dict("os.environ", {"CLAUDECODE": "1", "HOME": "/home/test"}):
            env = ai_review.build_env()
        assert "CLAUDECODE" not in env

    @patch("os.path.exists", return_value=True)
    def test_sets_home_for_docker(self, mock_exists):
        env = ai_review.build_env()
        assert env["HOME"] == "/root"

    @patch("os.path.exists", return_value=False)
    def test_preserves_home_outside_docker(self, mock_exists):
        import os
        env = ai_review.build_env()
        assert env["HOME"] == os.environ.get("HOME", "")


class TestBuildPrompt:
    def test_contains_pr_info(self):
        prompt = ai_review.build_prompt(
            pr_number=42,
            pr_title="Fix SMB auth",
            pr_body="This fixes a bug",
            diff="--- a/file.py\n+++ b/file.py\n+fixed line",
            results=[],
            summary={"total": 5, "passed": 3, "failed": 2},
        )
        assert "PR #42" in prompt
        assert "Fix SMB auth" in prompt
        assert "This fixes a bug" in prompt
        assert "fixed line" in prompt
        assert "Total: 5" in prompt
        assert "Passed: 3" in prompt
        assert "Failed: 2" in prompt

    def test_includes_ai_generated_section(self):
        prompt = ai_review.build_prompt(
            pr_number=1, pr_title="Test", pr_body="", diff="diff",
            results=[], summary={"total": 0, "passed": 0, "failed": 0},
        )
        assert "AI-Generated Code Assessment" in prompt

    def test_truncates_large_diff(self):
        large_diff = "x" * (ai_review.MAX_DIFF_CHARS + 1000)
        prompt = ai_review.build_prompt(
            pr_number=1, pr_title="Test", pr_body="", diff=large_diff,
            results=[], summary={"total": 0, "passed": 0, "failed": 0},
        )
        assert "truncated" in prompt

    def test_formats_failed_results(self):
        results = [
            {
                "test_name": "test_smb",
                "target_host": "10.0.0.1",
                "status": "failed",
                "duration": 1.5,
                "output": "connection refused",
                "error_message": "auth failed",
            }
        ]
        prompt = ai_review.build_prompt(
            pr_number=1, pr_title="Test", pr_body="", diff="diff",
            results=results, summary={"total": 1, "passed": 0, "failed": 1},
        )
        assert "[FAIL] test_smb" in prompt
        assert "target: 10.0.0.1" in prompt
        assert "auth failed" in prompt
        assert "connection refused" in prompt

    def test_formats_passed_results(self):
        results = [
            {
                "test_name": "test_ftp",
                "target_host": "10.0.0.1",
                "status": "passed",
                "duration": 0.5,
                "output": None,
                "error_message": None,
            }
        ]
        prompt = ai_review.build_prompt(
            pr_number=1, pr_title="Test", pr_body="", diff="diff",
            results=results, summary={"total": 1, "passed": 1, "failed": 0},
        )
        assert "[PASS] test_ftp" in prompt


class TestReviewEndpointGuard:
    """Test that POST /review returns 503 when Claude is unavailable.

    Note: The client fixture triggers the app lifespan which calls
    check_claude_available(), so we set module state AFTER client creation.
    """

    @patch("app.api.test_runs.run_pr_test")
    def test_review_returns_503_when_unavailable(self, mock_task, client, db):
        resp = client.post("/api/runs", json={"pr_number": 123})
        run_id = resp.json()["id"]

        from app.models.test_run import TestRun, TestRunStatus
        test_run = db.get(TestRun, run_id)
        test_run.status = TestRunStatus.COMPLETED
        db.commit()

        # Set unavailable AFTER client creation (lifespan already ran)
        ai_review.CLAUDE_AVAILABLE = False
        ai_review.CLAUDE_UNAVAILABLE_REASON = "Claude CLI not installed"

        resp = client.post(f"/api/runs/{run_id}/review")
        assert resp.status_code == 503
        assert "Claude CLI not installed" in resp.json()["detail"]

    @patch("app.services.ai_review.generate_review", return_value="Review text")
    @patch("app.api.test_runs.run_pr_test")
    def test_review_allowed_when_available(self, mock_task, mock_review, client, db):
        resp = client.post("/api/runs", json={"pr_number": 123})
        run_id = resp.json()["id"]

        from app.models.test_run import TestRun, TestRunStatus
        test_run = db.get(TestRun, run_id)
        test_run.status = TestRunStatus.COMPLETED
        db.commit()

        ai_review.CLAUDE_AVAILABLE = True
        ai_review.CLAUDE_UNAVAILABLE_REASON = ""

        resp = client.post(f"/api/runs/{run_id}/review")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
