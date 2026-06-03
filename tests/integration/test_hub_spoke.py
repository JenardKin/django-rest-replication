"""Integration: hub-and-spoke event flows."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from django_rest_replication.models import Direction, NodeConnection
from django_rest_replication.models.sync_cursor import SyncCursor


@pytest.mark.integration
@pytest.mark.hub_spoke
@pytest.mark.django_db
def test_hub_spoke_event_flows(
    hub_node: NodeConnection,
    httpx_mock: Any,
) -> None:
    """
    Spoke creates event → hub pulls it → verifies correct application.
    """
    from tests.testapp.models import Organization, Product
    from django_rest_replication.models import ChangeEvent, EventType
    from django_rest_replication.routing.cursor import get_or_create_cursor, mark_snapshot_complete
    from django_rest_replication.routing.puller import run_pull

    org = Organization.objects.create(name="Hub Org")
    product_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # Mark snapshot as done so we go straight to incremental
    cursor = get_or_create_cursor(hub_node)
    mark_snapshot_complete(cursor, None)

    # Mock incremental events endpoint
    httpx_mock.add_response(
        url="https://hub.example.com/replication/events/?limit=500",
        json=[
            {
                "id": event_id,
                "node_id": "00000000-0000-0000-0000-000000000099",
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": product_id,
                "tenant_id": None,
                "payload": {
                    "id": product_id,
                    "name": "Hub Product",
                    "price": "49.99",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
                "old_payload": None,
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ],
    )

    run_pull(hub_node)

    # Verify the product was applied locally
    assert Product.objects.filter(pk=product_id, name="Hub Product").exists()
    # Verify the event was recorded
    assert ChangeEvent.objects.filter(pk=event_id).exists()
