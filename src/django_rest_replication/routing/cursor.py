"""Cursor management for the sync engine."""

from __future__ import annotations

import uuid

from django_rest_replication.models.node_connection import NodeConnection
from django_rest_replication.models.sync_cursor import SyncCursor


def get_or_create_cursor(node: NodeConnection, tenant_id: str = "") -> SyncCursor:
    """Return the existing SyncCursor for (node, tenant_id) or create one."""
    cursor, _ = SyncCursor.objects.get_or_create(node=node, tenant_id=tenant_id)
    return cursor


def advance_cursor(cursor: SyncCursor, event_id: uuid.UUID) -> None:
    """Advance the cursor to point at the given event (select_for_update guard)."""
    from django_rest_replication.models.change_event import ChangeEvent

    SyncCursor.objects.select_for_update().filter(pk=cursor.pk).update(
        last_event_id=event_id,
    )
    cursor.last_event_id = event_id  # type: ignore[assignment]


def mark_snapshot_complete(cursor: SyncCursor, watermark: uuid.UUID | None) -> None:
    """Record that the snapshot phase has completed for this cursor."""
    from django.utils import timezone

    now = timezone.now()
    SyncCursor.objects.filter(pk=cursor.pk).update(
        snapshot_completed_at=now,
    )
    cursor.snapshot_completed_at = now  # type: ignore[attr-defined]

    if watermark is not None:
        SyncCursor.objects.filter(pk=cursor.pk).update(last_event_id=watermark)
        cursor.last_event_id = watermark  # type: ignore[assignment]


def needs_snapshot(cursor: SyncCursor) -> bool:
    """Return True if the cursor hasn't completed a snapshot yet."""
    return not bool(getattr(cursor, "snapshot_completed_at", None))
