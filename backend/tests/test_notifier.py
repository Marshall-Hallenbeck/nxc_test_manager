"""Tests for completion-email notifications."""
from unittest.mock import MagicMock, patch

from app.config import settings
from app.services import notifier

EMAIL_ARGS = {
    "pr_number": 1234,
    "pr_title": "Add a protocol",
    "status": "completed",
    "passed": 10,
    "failed": 0,
    "total": 10,
    "target_hosts": "10.0.0.1",
}


def send_and_capture():
    """Send a notification against a stubbed SMTP server, return the message."""
    server = MagicMock()
    with patch.object(notifier.smtplib, "SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        sent = notifier.send_test_completion_email(**EMAIL_ARGS)
    return sent, server.send_message.call_args


class TestNotificationDisabled:
    def test_disabled_email_sends_nothing(self):
        with patch.object(settings, "email_enabled", False):
            sent, call = send_and_capture()
        assert sent is False
        assert call is None

    def test_unconfigured_smtp_sends_nothing(self):
        with (
            patch.object(settings, "email_enabled", True),
            patch.object(settings, "smtp_username", ""),
        ):
            sent, call = send_and_capture()
        assert sent is False
        assert call is None


class TestNotificationContent:
    def send_with_base_url(self, base_url):
        with (
            patch.object(settings, "email_enabled", True),
            patch.object(settings, "smtp_username", "user"),
            patch.object(settings, "smtp_to", "admin@example.com"),
            patch.object(settings, "app_base_url", base_url),
        ):
            return send_and_capture()

    def test_body_links_to_the_configured_base_url(self):
        """Regression: the body hardcoded http://localhost:3000/runs, but the
        stack publishes the UI through nginx on port 9000, so every
        notification linked to a port nothing listens on.
        """
        sent, call = self.send_with_base_url("http://netexec.example:9000")
        assert sent is True
        body = call.args[0].get_payload()[0].get_payload()
        assert "http://netexec.example:9000/runs" in body
        assert "localhost:3000" not in body

    def test_trailing_slash_does_not_double_up(self):
        _sent, call = self.send_with_base_url("http://netexec.example:9000/")
        body = call.args[0].get_payload()[0].get_payload()
        assert "http://netexec.example:9000/runs" in body
        assert "//runs" not in body

    def test_subject_and_results_are_reported(self):
        _sent, call = self.send_with_base_url("http://localhost:9000")
        msg = call.args[0]
        assert "PR #1234" in msg["Subject"]
        assert "COMPLETED" in msg["Subject"]
        body = msg.get_payload()[0].get_payload()
        assert "10/10 passed" in body
        assert "10.0.0.1" in body
