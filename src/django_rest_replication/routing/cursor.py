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
    SyncCursor.objects.select_for_update().filter(pk=cursor.pk).update(
        last_event_id=str(event_id),
    )
    # Refresh the in-memory object to reflect DB state
    cursor.refresh_from_db()


def mark_snapshot_complete(cursor: SyncCursor, watermark: uuid.UUID | None) -> None:
    """Record that the snapshot phase has completed for this cursor."""
    from django.utils import timezone

    now = timezone.now()
    update_kwargs: dict[str, object] = {"snapshot_completed_at": now}
    if watermark is not None:
        update_kwargs["last_event_id"] = str(watermark)
    SyncCursor.objects.filter(pk=cursor.pk).update(**update_kwargs)
    cursor.refresh_from_db()


def needs_snapshot(cursor: SyncCursor) -> bool:
    """Return True if the cursor hasn't completed a snapshot yet."""
    return cursor.snapshot_completed_at is None
