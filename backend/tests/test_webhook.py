"""Tests for webhook signature verification."""
import hashlib
import hmac
from app.api.webhooks import verify_signature


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
