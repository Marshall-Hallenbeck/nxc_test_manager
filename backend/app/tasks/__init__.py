"""Celery app and tasks."""
from celery import Celery
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

from .test_tasks import run_pr_test  # noqa: E402, F401
