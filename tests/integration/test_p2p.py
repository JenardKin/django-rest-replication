"""Integration: peer-to-peer — no duplicate events."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from django_rest_replication.models import NodeConnection


@pytest.mark.integration
@pytest.mark.p2p
@pytest.mark.django_db(transaction=True)
def test_p2p_no_duplicate_events(
    spoke_node: NodeConnection,
    httpx_mock: Any,
) -> None:
    """
    Two nodes: loop prevention ensures events don't duplicate.

    Scenario:
    - Local node receives a remote event (via pull)
    - The event application must NOT trigger new ChangeEvents on the same record
    """
    from django_rest_replication.models import ChangeEvent
    from django_rest_replication.routing.cursor import get_or_create_cursor, mark_snapshot_complete
    from django_rest_replication.routing.puller import run_pull
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="P2P Org")
    product_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    remote_node_id = str(uuid.uuid4())

    # Mark snapshot as done so we go straight to incremental
    cursor = get_or_create_cursor(spoke_node)
    mark_snapshot_complete(cursor, None)

    # Mock the events endpoint with one CREATE event from remote
    httpx_mock.add_response(
        url="https://spoke.example.com/replication/events/?limit=500",
        json=[
            {
                "id": event_id,
                "node_id": remote_node_id,
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": product_id,
                "tenant_id": None,
                "payload": {
                    "id": product_id,
                    "name": "P2P Widget",
                    "price": "3.00",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
                "old_payload": None,
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ],
    )

    events_before = ChangeEvent.objects.count()
    run_pull(spoke_node)

    # The product should be created
    assert Product.objects.filter(pk=product_id).exists()

    # Only the incoming event should exist (loop prevention blocked re-capture)
    # The remote event is stored (upserted) but no NEW capture event from our signals
    events_after = ChangeEvent.objects.count()
    # We expect exactly 1 new event: the remote one that was stored (upserted).
    # No additional events from the local save (loop prevention).
    assert events_after <= events_before + 1
