"""Tests for the Celery run_pr_test task.

These drive the task body against a mocked session rather than the shared
SQLite test database: the task opens its own SessionLocal, and a second
connection to the same file races the autouse create/drop fixture.
"""
from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.models.test_run import TestRun, TestRunStatus
from app.tasks.test_tasks import run_pr_test

# celery's task decorator is untyped, so a type checker sees the undecorated
# function and misses the Task API that exists at runtime. `.run` is the
# implementation already bound to the Task, which is what a bind=True task
# needs in place of a live worker.
task_body = cast(Any, run_pr_test).run


def call_task(stored_run, run_test_side_effect=None):
    """Run the task body with a mocked DB session."""
    session = MagicMock()
    session.get.return_value = stored_run

    with (
        patch("app.tasks.test_tasks.SessionLocal", return_value=session),
        patch("app.tasks.test_tasks.test_runner.run_test") as run_test,
        patch("app.tasks.test_tasks.notifier.send_test_completion_email") as notify,
        patch("app.tasks.test_tasks.docker_manager.cleanup_source_images") as cleanup,
    ):
        if run_test_side_effect:
            run_test.side_effect = run_test_side_effect
        error = None
        try:
            task_body(test_run_id=1, target_password="pw")
        except Exception as exc:
            error = exc
        return {
            "cleanup": cleanup,
            "notify": notify,
            "session": session,
            "error": error,
        }


def completed_run():
    return TestRun(
        pr_number=1234,
        target_hosts="10.0.0.1",
        status=TestRunStatus.COMPLETED,
        total_tests=5,
        passed_tests=5,
        failed_tests=0,
    )


class TestImageCleanupIsWired:
    def test_cleanup_runs_after_a_completed_run(self):
        result = call_task(completed_run())

        assert result["error"] is None
        result["cleanup"].assert_called_once_with()

    def test_cleanup_is_skipped_when_the_task_fails(self):
        """A failing run must not swallow its error to reach cleanup — the
        exception has to propagate so Celery marks the task failed.
        """
        result = call_task(completed_run(), run_test_side_effect=RuntimeError("boom"))

        assert isinstance(result["error"], RuntimeError)
        result["cleanup"].assert_not_called()

    def test_missing_run_returns_without_cleanup(self):
        result = call_task(None)

        assert result["error"] is None
        result["cleanup"].assert_not_called()


class TestTaskBookkeeping:
    def test_completion_email_is_sent(self):
        result = call_task(completed_run())
        result["notify"].assert_called_once()
        assert result["notify"].call_args.kwargs["pr_number"] == 1234

    def test_session_is_closed(self):
        result = call_task(completed_run())
        result["session"].close.assert_called_once()

    def test_session_is_closed_even_when_the_run_fails(self):
        result = call_task(completed_run(), run_test_side_effect=RuntimeError("boom"))
        result["session"].close.assert_called_once()
