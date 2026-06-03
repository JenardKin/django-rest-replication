"""Default (no-op) backend implementation — last-write-wins conflict resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_rest_replication.backend.base import BaseReplicationBackend, ConflictResolution

if TYPE_CHECKING:
    from django.db import models as django_models

    from django_rest_replication.models import ChangeEvent, EventDelivery


class ReplicationBackend(BaseReplicationBackend):
    """No-op backend with sensible defaults. Subclass to customise behaviour."""

    def on_event_captured(self, event: ChangeEvent) -> None:
        """Called after a ChangeEvent is written. No-op by default."""

    def on_before_apply(self, event: ChangeEvent) -> bool:
        """Return True to allow the event to be applied. Always True here."""
        return True

    def on_after_apply(self, event: ChangeEvent) -> None:
        """Called after an event is applied. No-op by default."""

    def on_delivery_failed(self, delivery: EventDelivery) -> None:
        """Called when a delivery has failed. No-op by default."""

    def resolve_conflict(
        self, local: django_models.Model, event: ChangeEvent
    ) -> ConflictResolution:
        """Last-write-wins: the incoming remote event wins."""
        return ConflictResolution.USE_REMOTE
