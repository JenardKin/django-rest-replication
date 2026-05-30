"""
NodeConnection — registry of peer nodes this node can communicate with.

Configured via the Django admin (Phase 9) or the replication_init wizard (Phase 9).
"""

from __future__ import annotations

import uuid_utils
from django.db import models


class Direction(models.TextChoices):
    PUSH = "PUSH", "Push (send to peer)"
    PULL = "PULL", "Pull (receive from peer)"
    BOTH = "BOTH", "Both (push and pull)"


class NodeConnection(models.Model):
    """
    A known peer node.

    ``direction`` controls whether this node pushes events to the peer,
    pulls events from the peer, or does both.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid_utils.uuid7,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable label for this peer, e.g. 'EU warehouse'.",
    )
    base_url = models.CharField(
        max_length=2048,
        help_text="Root URL of the peer, e.g. 'https://peer.example.com'.",
    )
    node_id = models.UUIDField(
        unique=True,
        help_text="The NODE_ID declared by the peer in its DJANGO_REPLICATION settings.",
    )
    direction = models.CharField(
        max_length=4,
        choices=Direction.choices,
        default=Direction.BOTH,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    auth_token = models.CharField(
        max_length=512,
        help_text="Shared bearer token used to authenticate requests to/from this peer.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "django_rest_replication"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.node_id})"
