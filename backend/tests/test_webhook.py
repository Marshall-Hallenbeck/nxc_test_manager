"""Tests for webhook signature verification and endpoint authentication."""
import hashlib
import hmac
from unittest.mock import patch

from app.api.webhooks import verify_signature
from app.config import settings


class TestWebhookSignature:
    def test_valid_signature(self):
        secret = "mysecret"
        payload = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        secret = "mysecret"
        payload = b'{"action": "opened"}'
        assert verify_signature(payload, "sha256=invalid", secret) is False

    def test_wrong_secret(self):
        secret = "mysecret"
        wrong_secret = "wrongsecret"
        payload = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(wrong_secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret) is False

    def test_empty_payload(self):
        secret = "mysecret"
        payload = b""
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret) is True


PR_PAYLOAD = {
    "action": "opened",
    "repository": {"full_name": "Pennyw0rth/NetExec"},
    "pull_request": {"number": 1234, "title": "test", "head": {"sha": "abc123"}},
}
PR_HEADERS = {"X-GitHub-Event": "pull_request"}


class TestWebhookEndpointAuth:
    def test_disabled_webhook_returns_404(self, client):
        with patch.object(settings, "webhook_enabled", False):
            resp = client.post("/webhooks/github", json=PR_PAYLOAD, headers=PR_HEADERS)
        assert resp.status_code == 404

    def test_enabled_without_secret_is_rejected(self, client):
        """Regression: the signature check was guarded by `if settings.webhook_secret`,
        so enabling webhooks without configuring a secret silently disabled
        authentication and let any unauthenticated caller queue test runs.
        """
        with (
            patch.object(settings, "webhook_enabled", True),
            patch.object(settings, "webhook_secret", ""),
            patch("app.api.webhooks.run_pr_test.delay") as delay,
        ):
            resp = client.post("/webhooks/github", json=PR_PAYLOAD, headers=PR_HEADERS)

        assert resp.status_code == 500
        assert "secret" in resp.json()["detail"].lower()
        delay.assert_not_called()

    def test_enabled_with_secret_rejects_missing_signature(self, client):
        with (
            patch.object(settings, "webhook_enabled", True),
            patch.object(settings, "webhook_secret", "mysecret"),
            patch("app.api.webhooks.run_pr_test.delay") as delay,
        ):
            resp = client.post("/webhooks/github", json=PR_PAYLOAD, headers=PR_HEADERS)

        assert resp.status_code == 403
        delay.assert_not_called()

    def test_enabled_with_secret_rejects_bad_signature(self, client):
        with (
            patch.object(settings, "webhook_enabled", True),
            patch.object(settings, "webhook_secret", "mysecret"),
            patch("app.api.webhooks.run_pr_test.delay") as delay,
        ):
            resp = client.post(
                "/webhooks/github",
                json=PR_PAYLOAD,
                headers={**PR_HEADERS, "X-Hub-Signature-256": "sha256=deadbeef"},
            )

        assert resp.status_code == 403
        delay.assert_not_called()

    def test_valid_signature_queues_a_run(self, client):
        import json

        secret = "mysecret"
        body = json.dumps(PR_PAYLOAD).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with (
            patch.object(settings, "webhook_enabled", True),
            patch.object(settings, "webhook_secret", secret),
            patch.object(settings, "webhook_repo_filter", "Pennyw0rth/NetExec"),
            patch.object(settings, "webhook_auto_test_events", "opened,synchronize"),
            patch("app.api.webhooks.run_pr_test.delay") as delay,
        ):
            resp = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    **PR_HEADERS,
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        delay.assert_called_once()
