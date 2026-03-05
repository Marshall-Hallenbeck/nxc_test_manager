"""Empire C2 listener initialization for e2e tests."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

LISTENER_NAME = "http-listener"


def ensure_empire_listener() -> None:
    """Check if Empire is reachable and create an HTTP listener if none exists.

    This is best-effort: if Empire is unreachable, log a warning and continue.
    The empire_exec tests will fail, but other tests are unaffected.
    """
    base_url = f"http://{settings.empire_host}:{settings.empire_port}"

    # Check if Empire is reachable
    try:
        resp = httpx.get(f"{base_url}/", timeout=5)
        resp.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        logger.warning(
            "Empire not reachable at %s — empire_exec tests will fail",
            base_url,
        )
        return

    # Authenticate
    try:
        token_resp = httpx.post(
            f"{base_url}/token",
            data={
                "username": settings.empire_username,
                "password": settings.empire_password,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]
    except Exception as e:
        logger.warning("Empire auth failed: %s", e)
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Check if listener already exists
    try:
        listeners_resp = httpx.get(
            f"{base_url}/api/v2/listeners",
            headers=headers,
            timeout=10,
        )
        listeners_resp.raise_for_status()
        listeners = listeners_resp.json().get("records", [])
        if any(entry["name"] == LISTENER_NAME for entry in listeners):
            logger.info("Empire listener '%s' already exists", LISTENER_NAME)
            return
    except Exception as e:
        logger.warning("Failed to check Empire listeners: %s", e)
        return

    # Create HTTP listener
    try:
        create_resp = httpx.post(
            f"{base_url}/api/v2/listeners",
            headers=headers,
            json={
                "name": LISTENER_NAME,
                "template": "http",
                "options": {
                    "Name": LISTENER_NAME,
                    "Host": "http://0.0.0.0",
                    "BindIP": "0.0.0.0",
                    "Port": "8080",
                },
            },
            timeout=10,
        )
        create_resp.raise_for_status()
        logger.info("Created Empire listener '%s'", LISTENER_NAME)
    except Exception as e:
        logger.warning("Failed to create Empire listener: %s", e)
