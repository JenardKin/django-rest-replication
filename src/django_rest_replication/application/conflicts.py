"""Conflict resolution strategies for event application."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django_rest_replication.backend.base import BaseReplicationBackend, ConflictResolution
    from django_rest_replication.models import ChangeEvent


class ConflictStrategy(StrEnum):
    LAST_WRITE_WINS = "LAST_WRITE_WINS"
    SKIP_IF_NEWER = "SKIP_IF_NEWER"
    RAISE = "RAISE"


def resolve(
    strategy: ConflictStrategy,
    local: models.Model,
    event: ChangeEvent,
    backend: BaseReplicationBackend,
) -> ConflictResolution:
    """Apply the given strategy and return a ConflictResolution."""
    from django_rest_replication.backend.base import ConflictResolution

    if strategy == ConflictStrategy.LAST_WRITE_WINS:
        return ConflictResolution.USE_REMOTE

    if strategy == ConflictStrategy.SKIP_IF_NEWER:
        local_ts = getattr(local, "updated_at", None)
        event_ts = event.created_at
        if local_ts is not None and event_ts is not None and local_ts > event_ts:
            return ConflictResolution.USE_LOCAL
        return ConflictResolution.USE_REMOTE

    if strategy == ConflictStrategy.RAISE:
        raise ValueError(
            f"Conflict detected for {event.model_label}({event.object_id}): "
            f"local updated_at={getattr(local, 'updated_at', None)}, "
            f"event created_at={event.created_at}"
        )

    # Delegate to backend
    return backend.resolve_conflict(local, event)
