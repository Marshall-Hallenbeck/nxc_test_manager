"""Test run API endpoints."""
import logging
import threading
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db, SessionLocal
from app.config import settings
from app.models.test_run import TestRun, TestRunStatus
from app.schemas.test_run import TestRunCreate, TestRunOut, TestRunDetail, TestRunListOut, CompareOut
from app.services import github, ai_review
from app.tasks.test_tasks import run_pr_test, cancel_test_run

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/prs")
def search_prs(q: str = Query("")):
    """Search open PRs in the NetExec repo by number or title."""
    return github.search_open_prs(q)


@router.post("", response_model=TestRunOut)
def create_test_run(data: TestRunCreate, db: Session = Depends(get_db)):
    """Submit a new test run for a PR."""
    password = data.target_password or settings.default_target_password
    test_run = TestRun(
        pr_number=data.pr_number,
        target_hosts=data.target_hosts or settings.default_target_hosts,
        target_username=data.target_username or settings.default_target_username,
        target_password=password,
        protocols=",".join(data.protocols) if data.protocols else None,
        kerberos=1 if data.kerberos else 0,
        verbose=1 if data.verbose else 0,
        show_errors=1 if data.show_errors else 0,
        ai_review_enabled=1 if data.ai_review else 0,
        line_nums=data.line_nums,
        not_tested=1 if data.not_tested else 0,
        dns_server=data.dns_server,
        status=TestRunStatus.QUEUED,
        total_tests=0,
        passed_tests=0,
        failed_tests=0,
    )
    db.add(test_run)
    db.commit()
    db.refresh(test_run)

    run_pr_test.delay(
        test_run_id=test_run.id,
        target_password=password,
    )

    return test_run


@router.get("", response_model=TestRunListOut)
def list_test_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    pr_number: int | None = None,
    db: Session = Depends(get_db),
):
    """List all test runs with optional filtering."""
    query = db.query(TestRun)

    if status:
        query = query.filter(TestRun.status == status)
    if pr_number:
        query = query.filter(TestRun.pr_number == pr_number)

    total = query.count()
    items = (
        query.order_by(desc(TestRun.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return TestRunListOut(items=items, total=total, page=page, per_page=per_page)


@router.get("/{test_run_id}", response_model=TestRunDetail)
def get_test_run(test_run_id: int, db: Session = Depends(get_db)):
    """Get test run details including results."""
    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return test_run


@router.post("/{test_run_id}/cancel")
def cancel_run(test_run_id: int, db: Session = Depends(get_db)):
    """Cancel a running or queued test run."""
    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    if test_run.status not in (TestRunStatus.QUEUED, TestRunStatus.RUNNING):
        raise HTTPException(status_code=400, detail=f"Cannot cancel test run with status: {test_run.status}")

    success = cancel_test_run(test_run_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel test run")

    return {"status": "cancelled"}


@router.delete("/{test_run_id}")
def delete_test_run(test_run_id: int, db: Session = Depends(get_db)):
    """Delete a completed or cancelled test run."""
    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    if test_run.status in (TestRunStatus.QUEUED, TestRunStatus.RUNNING):
        raise HTTPException(status_code=400, detail="Cannot delete an active test run, cancel it first")

    db.delete(test_run)
    db.commit()
    return {"status": "deleted"}


@router.get("/{test_run_id}/logs")
def get_test_run_logs(test_run_id: int, db: Session = Depends(get_db)):
    """Get all logs for a test run."""
    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return [{"id": log.id, "timestamp": log.timestamp, "log_line": log.log_line, "level": log.level} for log in test_run.logs]


@router.post("/{test_run_id}/review")
def review_test_run(test_run_id: int, db: Session = Depends(get_db)):
    """Trigger an AI review of the test run using Claude CLI.

    Runs in a background thread. Poll GET /{id} for ai_review_status updates.
    """
    if not ai_review.CLAUDE_AVAILABLE:
        raise HTTPException(status_code=503, detail=ai_review.CLAUDE_UNAVAILABLE_REASON or "Claude CLI unavailable")

    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    if test_run.ai_review_status == "running":
        raise HTTPException(status_code=409, detail="Review already in progress")

    # Mark as running
    test_run.ai_review_status = "running"
    test_run.ai_summary = None
    db.commit()

    # Gather data for the review
    results_data = [
        {
            "test_name": r.test_name,
            "target_host": r.target_host,
            "status": r.status,
            "duration": r.duration,
            "output": r.output,
            "error_message": r.error_message,
        }
        for r in test_run.results
    ]
    summary_data = {
        "total": test_run.total_tests,
        "passed": test_run.passed_tests,
        "failed": test_run.failed_tests,
    }
    pr_number = test_run.pr_number
    pr_title = test_run.pr_title

    def run_review_background():
        review_db = SessionLocal()
        try:
            review_text = ai_review.generate_review(
                pr_number=pr_number,
                pr_title=pr_title,
                results=results_data,
                summary=summary_data,
            )
            run = review_db.get(TestRun, test_run_id)
            if run:
                run.ai_summary = review_text
                run.ai_review_status = "completed"
                review_db.commit()
        except Exception as e:
            logger.error(f"AI review failed for TestRun {test_run_id}: {e}")
            run = review_db.get(TestRun, test_run_id)
            if run:
                run.ai_summary = f"Review failed: {e}"
                run.ai_review_status = "failed"
                review_db.commit()
        finally:
            review_db.close()

    thread = threading.Thread(target=run_review_background, daemon=True)
    thread.start()

    return {"status": "running"}


@router.get("/compare")
def compare_test_runs(
    run1: int = Query(...),
    run2: int = Query(...),
    db: Session = Depends(get_db),
):
    """Compare two test runs."""
    tr1 = db.get(TestRun, run1)
    tr2 = db.get(TestRun, run2)

    if not tr1 or not tr2:
        raise HTTPException(status_code=404, detail="One or both test runs not found")

    return CompareOut(run1=tr1, run2=tr2)
