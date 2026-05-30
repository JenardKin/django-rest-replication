"""
ReplicationPolicy — controls which models (and which fields) replicate to which nodes.

One policy row = one (node, model_label) rule.
Use model_label="*" to apply a rule to all models on a node.
"""

from __future__ import annotations

import uuid_utils
from django.db import models

from django_rest_replication.models.node_connection import NodeConnection


class ReplicationPolicy(models.Model):
    """
    Routing rule that determines whether events for a given model are sent to a node,
    and optionally restricts which fields are included in the payload.

    Field resolution order:
    1. If ``included_fields`` is non-null, only those fields are included.
    2. Fields listed in ``excluded_fields`` are then removed.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid_utils.uuid7,
        editable=False,
    )
    node = models.ForeignKey(
        NodeConnection,
        on_delete=models.CASCADE,
        related_name="policies",
    )
    model_label = models.CharField(
        max_length=255,
        help_text=(
            'Django app_label.ModelName, e.g. "shop.Product". '
            'Use "*" to match all models on this node.'
        ),
    )
    included_fields = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Whitelist of field names to include. Null means include all fields.",
    )
    excluded_fields = models.JSONField(
        default=list,
        blank=True,
        help_text="Blacklist of field names to exclude (applied after included_fields).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "django_rest_replication"
        ordering = ["node", "model_label"]
        unique_together = [("node", "model_label")]
        verbose_name_plural = "replication policies"

    def __str__(self) -> str:
        return f"{self.model_label} → {self.node.name}"
