"""
SyncCursor — tracks the last successfully applied event from a peer node.

One row per (node, tenant_id) pair.  The sync engine advances the cursor only
after an event has been fully applied and acknowledged, ensuring no events are
skipped on failure.
"""

from __future__ import annotations

import uuid_utils
from django.db import models

from django_rest_replication.models.change_event import ChangeEvent
from django_rest_replication.models.node_connection import NodeConnection


class SyncCursor(models.Model):
    """
    Pull cursor for a (NodeConnection, tenant) pair.

    ``last_event`` is the UUID v7 of the most recently applied ChangeEvent from
    the peer.  Null means no events have been applied yet (pull from the start).
    The sync engine uses this as the ``after`` parameter in pull requests.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid_utils.uuid7,
        editable=False,
    )
    node = models.ForeignKey(
        NodeConnection,
        on_delete=models.CASCADE,
        related_name="cursors",
    )
    tenant_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Tenant this cursor tracks. Null for single-tenant setups.",
    )
    last_event = models.ForeignKey(
        ChangeEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Last successfully applied event from this node/tenant stream.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "django_rest_replication"
        unique_together = [("node", "tenant_id")]

    def __str__(self) -> str:
        tenant = self.tenant_id or "—"
        cursor = str(self.last_event_id) if self.last_event_id else "start"
        return f"{self.node.name} / tenant={tenant} @ {cursor}"
