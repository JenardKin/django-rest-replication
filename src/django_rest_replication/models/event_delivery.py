"""
EventDelivery — tracks the delivery status of a ChangeEvent to a NodeConnection.

One row per (event, node) pair.  Created by the routing layer; updated by the
transport layer as delivery succeeds, fails, or is retried.
"""

from __future__ import annotations

from django.db import models

from django_rest_replication.models.change_event import ChangeEvent
from django_rest_replication.models.node_connection import NodeConnection
from django_rest_replication.utils import uuid7


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped"


class EventDelivery(models.Model):
    """
    Delivery record for one (ChangeEvent, NodeConnection) pair.

    ``attempts`` is incremented on each delivery attempt.
    ``last_error`` stores the most recent error message for operator visibility.
    ``delivered_at`` is set when status transitions to DELIVERED.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid7,
        editable=False,
    )
    event = models.ForeignKey(
        ChangeEvent,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    node = models.ForeignKey(
        NodeConnection,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    status = models.CharField(
        max_length=9,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "django_rest_replication"
        ordering = ["created_at"]
        unique_together = [("event", "node")]
        indexes = [
            models.Index(fields=["status", "created_at"], name="ed_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_id} → {self.node.name} [{self.status}]"
