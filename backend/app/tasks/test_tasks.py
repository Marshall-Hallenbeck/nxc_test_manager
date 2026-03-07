"""Celery tasks for test execution."""
import logging
from . import celery_app
from app.database import SessionLocal
from app.models.test_run import TestRun, TestRunStatus
from app.services import test_runner, notifier, docker_manager

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="run_pr_test")
def run_pr_test(
    self,
    test_run_id: int,
    target_password: str | None = None,
):
    """Execute a PR test run asynchronously.

    Args:
        test_run_id: ID of the TestRun record in the database
        target_password: Password for target authentication (not stored in DB)
    """
    db = SessionLocal()
    try:
        # Store celery task ID for cancellation
        test_run = db.get(TestRun, test_run_id)
        if not test_run:
            logger.error(f"TestRun {test_run_id} not found")
            return
        test_run.celery_task_id = self.request.id
        db.commit()

        # Run tests
        test_runner.run_test(db, test_run_id, target_password)

        # Refresh to get final state
        db.refresh(test_run)

        # Send notification
        if test_run.status in (TestRunStatus.COMPLETED, TestRunStatus.FAILED):
            label = f"PR #{test_run.pr_number}" if test_run.pr_number else f"branch '{test_run.branch}'"
            notifier.send_test_completion_email(
                pr_number=test_run.pr_number or 0,
                pr_title=test_run.pr_title or label,
                status=test_run.status.value,
                passed=test_run.passed_tests or 0,
                failed=test_run.failed_tests or 0,
                total=test_run.total_tests or 0,
                target_hosts=test_run.target_hosts,
            )
    except Exception as e:
        logger.error(f"Task failed for TestRun {test_run_id}: {e}")
        try:
            test_run = db.get(TestRun, test_run_id)
            if test_run and test_run.status != TestRunStatus.CANCELLED:
                test_run.status = TestRunStatus.FAILED
                test_run.sub_status = None
                db.commit()
        except Exception as db_err:
            logger.error(f"Failed to mark TestRun {test_run_id} as failed: {db_err}")
        raise
    finally:
        db.close()


def cancel_test_run(test_run_id: int) -> bool:
    """Cancel a running or queued test run.

    Returns True if successfully cancelled.
    """
    db = SessionLocal()
    try:
        test_run = db.get(TestRun, test_run_id)
        if not test_run:
            return False

        if test_run.status not in (TestRunStatus.QUEUED, TestRunStatus.RUNNING):
            return False

        # Revoke celery task
        if test_run.celery_task_id:
            celery_app.control.revoke(test_run.celery_task_id, terminate=True)

        # Stop container if running
        if test_run.container_id:
            docker_manager.stop_container(test_run.container_id)

        test_run.status = TestRunStatus.CANCELLED
        test_run.sub_status = None
        db.commit()
        logger.info(f"Cancelled TestRun {test_run_id}")
        return True
    finally:
        db.close()
