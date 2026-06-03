"""Synchronous task backend — runs delivery and pull inline (no queue)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from django_rest_replication.tasks.base import BaseTaskBackend

if TYPE_CHECKING:
    from django_rest_replication.models import ChangeEvent

logger = logging.getLogger(__name__)


class SynchronousTaskBackend(BaseTaskBackend):
    """
    Executes push/pull synchronously in the same process.

    Suitable for development and simple single-server deployments.
    Production deployments should use a Celery or Django-Q backend.
    """

    def enqueue_delivery(self, event: ChangeEvent) -> None:
        """Run the push engine synchronously for this event."""
        try:
            from django_rest_replication.routing.pusher import run_push
        except ImportError:
            logger.debug("Pusher not yet available — skipping enqueue_delivery")
            return
        try:
            run_push()
        except Exception:
            logger.exception("Synchronous delivery failed for event %s", event.pk)

    def enqueue_pull(self, node_id: uuid.UUID, tenant_id: str | None = None) -> None:
        """Run the pull engine synchronously."""
        try:
            from django_rest_replication.routing.puller import run_pull
        except ImportError:
            logger.debug("Puller not yet available — skipping enqueue_pull")
            return
        try:
            run_pull()
        except Exception:
            logger.exception("Synchronous pull failed for node %s", node_id)
