"""
ChangeEvent — immutable log entry for every captured model mutation.

Written by the capture layer (Phase 3); read by the routing and transport layers.
Never modified after creation.
"""

from __future__ import annotations

import uuid_utils
from django.db import models


class EventType(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"


class ChangeEvent(models.Model):
    """
    Immutable record of a single CREATE, UPDATE, or DELETE on a ReplicatedModel.

    ``id`` is a UUID v7 so events are naturally time-ordered and can be used
    directly as cursors without a separate sequence column.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid_utils.uuid7,
        editable=False,
    )
    node_id = models.UUIDField(
        help_text="NODE_ID of the node that produced this event.",
        db_index=True,
    )
    event_type = models.CharField(
        max_length=6,
        choices=EventType.choices,
        db_index=True,
    )
    model_label = models.CharField(
        max_length=255,
        help_text='Django app_label.ModelName, e.g. "shop.Product".',
        db_index=True,
    )
    object_id = models.CharField(
        max_length=255,
        help_text="str(instance.pk) of the affected object.",
        db_index=True,
    )
    tenant_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Tenant identifier returned by get_tenant_id(); null for single-tenant.",
    )
    payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Full serialized field values for CREATE and UPDATE events.",
    )
    old_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Previous field values captured via pre_save, for UPDATE events only.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "django_rest_replication"
        ordering = ["id"]  # UUID v7 → chronological
        indexes = [
            models.Index(fields=["node_id", "id"], name="ce_node_cursor_idx"),
            models.Index(fields=["tenant_id", "id"], name="ce_tenant_cursor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.model_label}({self.object_id}) @ {self.id}"
