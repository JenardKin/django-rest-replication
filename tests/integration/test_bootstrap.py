"""Integration: bootstrap then stream."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from django_rest_replication.models import NodeConnection
from django_rest_replication.routing.cursor import get_or_create_cursor, needs_snapshot


@pytest.mark.integration
@pytest.mark.django_db
def test_node_with_existing_data_bootstraps_then_streams(
    hub_node: NodeConnection,
    httpx_mock: Any,
) -> None:
    """
    Full integration test:
    1. Simulate remote node with existing Products
    2. Local cursor has snapshot_completed_at=None → bootstrap runs
    3. run_pull fetches manifest, snapshot pages, applies rows
    4. Verify local Products were created
    5. Verify cursor.snapshot_completed_at is set
    6. run_pull again → calls events endpoint, not snapshot
    """
    from django_rest_replication.routing.puller import run_pull
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="Remote Org")
    remote_product_id = str(uuid.uuid4())

    # ----- First run: bootstrap -----
    # Mock manifest
    httpx_mock.add_response(
        url="https://hub.example.com/replication/snapshot/manifest/",
        json={
            "watermark": str(uuid.uuid4()),
            "models": ["testapp.Product"],
        },
    )
    # Mock snapshot page
    httpx_mock.add_response(
        url="https://hub.example.com/replication/snapshot/?model=testapp.Product&limit=500",
        json={
            "model": "testapp.Product",
            "next_cursor": None,
            "has_more": False,
            "rows": [
                {
                    "id": remote_product_id,
                    "name": "Remote Widget",
                    "price": "19.99",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                }
            ],
        },
    )

    cursor = get_or_create_cursor(hub_node)
    assert needs_snapshot(cursor) is True

    run_pull(hub_node)

    # Step 4: local Product created
    assert Product.objects.filter(pk=remote_product_id).exists()

    # Step 5: cursor is bootstrapped
    cursor.refresh_from_db()
    assert cursor.snapshot_completed_at is not None
    assert not needs_snapshot(cursor)

    # ----- Second run: incremental pull -----
    new_product_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    cursor_after = str(cursor.last_event_id) if cursor.last_event_id else None
    expected_params = "limit=500"
    if cursor_after:
        expected_params = f"after={cursor_after}&limit=500"

    httpx_mock.add_response(
        url=f"https://hub.example.com/replication/events/?{expected_params}",
        json=[
            {
                "id": event_id,
                "node_id": str(uuid.uuid4()),
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": new_product_id,
                "tenant_id": None,
                "payload": {
                    "id": new_product_id,
                    "name": "New Remote Widget",
                    "price": "9.99",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-02T00:00:00+00:00",
                    "updated_at": "2024-01-02T00:00:00+00:00",
                },
                "old_payload": None,
                "created_at": "2024-01-02T00:00:00+00:00",
            }
        ],
    )

    run_pull(hub_node)

    # Step 6: new product created via incremental pull
    assert Product.objects.filter(pk=new_product_id).exists()
