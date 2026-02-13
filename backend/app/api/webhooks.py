"""GitHub webhook endpoint for auto-testing PRs."""
import hashlib
import hmac
import logging
from fastapi import APIRouter, Request, HTTPException
from app.config import settings
from app.database import SessionLocal
from app.models.test_run import TestRun, TestRunStatus
from app.tasks.test_tasks import run_pr_test

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events and auto-queue test runs."""
    if not settings.webhook_enabled:
        raise HTTPException(status_code=404, detail="Webhooks disabled")

    # Verify signature
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.webhook_secret and not verify_signature(body, signature, settings.webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"status": "ignored", "reason": f"event type: {event}"}

    payload = await request.json()
    action = payload.get("action", "")
    allowed_events = [e.strip() for e in settings.webhook_auto_test_events.split(",")]

    if action not in allowed_events:
        return {"status": "ignored", "reason": f"action: {action}"}

    # Check repo filter
    repo_name = payload.get("repository", {}).get("full_name", "")
    if settings.webhook_repo_filter and repo_name != settings.webhook_repo_filter:
        return {"status": "ignored", "reason": f"repo: {repo_name}"}

    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    if not pr_number:
        return {"status": "ignored", "reason": "no PR number"}

    # Create test run
    db = SessionLocal()
    try:
        test_run = TestRun(
            pr_number=pr_number,
            pr_title=pr.get("title"),
            commit_sha=pr.get("head", {}).get("sha"),
            target_hosts=settings.default_target_hosts,
            target_username=settings.default_target_username,
            status=TestRunStatus.QUEUED,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
        )
        db.add(test_run)
        db.commit()
        db.refresh(test_run)

        run_pr_test.delay(test_run_id=test_run.id, target_password=None)
        logger.info(f"Auto-queued test for PR #{pr_number} via webhook ({action})")

        return {"status": "queued", "test_run_id": test_run.id, "pr_number": pr_number}
    finally:
        db.close()
