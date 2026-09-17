"""
Celery application configuration.
See specification v6/v7, section 4.2: invoices are submitted to a "Mock AGT"
server asynchronously via Celery, triggered immediately after creation.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rm_system",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Luanda",
    enable_utc=True,
)

# Explicit import (not autodiscover_tasks, which only looks for a file
# literally named tasks.py - our task lives in agt_worker.py instead).
import app.workers.agt_worker  # noqa: F401,E402

