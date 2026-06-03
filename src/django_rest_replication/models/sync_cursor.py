"""
SyncCursor — tracks the last successfully applied event from a peer node.

One row per (node, tenant_id) pair.  The sync engine advances the cursor only
after an event has been fully applied and acknowledged, ensuring no events are
skipped on failure.
"""

from __future__ import annotations

from django.db import models

from django_rest_replication.models.node_connection import NodeConnection
from django_rest_replication.utils import uuid7


class SyncCursor(models.Model):
    """
    Pull cursor for a (NodeConnection, tenant) pair.

    ``last_event_id`` is the UUID v7 of the most recently applied ChangeEvent
    from the peer.  Null means no events have been applied yet (pull from the
    start).  The sync engine uses this as the ``after`` parameter in pull
    requests.

    Stored as a plain UUIDField (not a FK) so that:
    - No FK constraint is checked on every cursor advance.
    - Pruning old ChangeEvents does not null-out or block cursor rows.
    - The cursor position is preserved even after event log archival.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid7,
        editable=False,
    )
    node = models.ForeignKey(
        NodeConnection,
        on_delete=models.CASCADE,
        related_name="cursors",
    )
    tenant_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Tenant this cursor tracks. Empty string for single-tenant setups.",
    )
    last_event_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID v7 of the last successfully applied event from this node/tenant stream.",
    )
    snapshot_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set when the initial bulk snapshot has finished for this cursor. "
            "Null means the snapshot has never run — the pull engine will run "
            "the bootstrap phase before switching to incremental streaming."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "django_rest_replication"
        unique_together = [("node", "tenant_id")]

    def __str__(self) -> str:
        tenant = self.tenant_id if self.tenant_id else "—"
        cursor = str(self.last_event_id) if self.last_event_id is not None else "start"
        return f"{self.node.name} / tenant={tenant} @ {cursor}"
