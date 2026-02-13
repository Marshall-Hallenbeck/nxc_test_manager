"""Email notification service."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

logger = logging.getLogger(__name__)


def send_test_completion_email(
    pr_number: int,
    pr_title: str,
    status: str,
    passed: int,
    failed: int,
    total: int,
    target_hosts: str,
) -> bool:
    """Send email notification when a test run completes.

    Returns True if sent successfully.
    """
    if not settings.email_enabled:
        logger.debug("Email notifications disabled, skipping")
        return False

    if not settings.smtp_username or not settings.smtp_to:
        logger.info("SMTP not configured, skipping email notification")
        return False

    subject = f"NetExec PR #{pr_number} Tests {status.upper()}"
    body = f"""NetExec E2E Test Results

PR: #{pr_number} - {pr_title}
Status: {status.upper()}
Results: {passed}/{total} passed, {failed} failed
Targets: {target_hosts}

View details at: http://localhost:3000/runs
"""

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Sent notification email for PR #{pr_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
