"""Push engine — delivers PENDING EventDelivery records to target nodes."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from django_rest_replication.conf import app_settings
from django_rest_replication.models.event_delivery import DeliveryStatus, EventDelivery
from django_rest_replication.models.node_connection import Direction, NodeConnection

logger = logging.getLogger(__name__)


def _auth_headers(node: NodeConnection) -> dict[str, str]:
    return {"Authorization": f"Token {node.auth_token}"}


def run_push(node: NodeConnection | None = None) -> None:
    """
    Push PENDING EventDelivery records to their target nodes.

    Idempotent: only processes PENDING records; marks them DELIVERED or FAILED.
    """
    qs = EventDelivery.objects.select_related("event", "node").filter(
        status=DeliveryStatus.PENDING,
        node__is_active=True,
        node__direction__in=[Direction.PUSH, Direction.BOTH],
    )
    if node is not None:
        qs = qs.filter(node=node)

    pending = list(qs.order_by("created_at")[: app_settings.BATCH_SIZE])
    if not pending:
        return

    from django.utils import timezone

    from django_rest_replication.api.serializers import ChangeEventSerializer

    with httpx.Client() as client:
        for delivery in pending:
            peer = delivery.node
            event = delivery.event

            # Increment attempt count
            EventDelivery.objects.filter(pk=delivery.pk).update(
                attempts=delivery.attempts + 1
            )

            serializer = ChangeEventSerializer(event)
            payload: list[dict[str, Any]] = [serializer.data]  # type: ignore[list-item]

            try:
                resp = client.post(
                    f"{peer.base_url.rstrip('/')}/replication/events/",
                    json=payload,
                    headers=_auth_headers(peer),
                    timeout=app_settings.REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                EventDelivery.objects.filter(pk=delivery.pk).update(
                    status=DeliveryStatus.DELIVERED,
                    delivered_at=timezone.now(),
                    last_error="",
                )
                logger.debug("Delivered event %s to %s", event.pk, peer.name)
            except httpx.HTTPError as exc:
                error_msg = str(exc)
                new_status = (
                    DeliveryStatus.FAILED
                    if delivery.attempts + 1 >= app_settings.MAX_RETRIES
                    else DeliveryStatus.PENDING
                )
                EventDelivery.objects.filter(pk=delivery.pk).update(
                    status=new_status,
                    last_error=error_msg[:2000],
                )
                logger.warning("Delivery failed for event %s to %s: %s", event.pk, peer.name, exc)
                try:
                    app_settings.BACKEND().on_delivery_failed(delivery)
                except Exception:
                    logger.exception("on_delivery_failed hook raised")
