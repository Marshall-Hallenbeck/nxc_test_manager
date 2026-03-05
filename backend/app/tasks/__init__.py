"""Celery app and tasks."""

from celery import Celery
from celery.signals import worker_ready
from app.config import settings

celery_app = Celery(
    "netexec_tests",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Initialize Empire listener when the Celery worker starts."""
    from app.services.empire import ensure_empire_listener

    ensure_empire_listener()


from .test_tasks import run_pr_test  # noqa: E402, F401
