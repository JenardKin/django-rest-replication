"""Phase 6 tests — sync engine (routing)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from django_rest_replication.models import (
    ChangeEvent,
    DeliveryStatus,
    Direction,
    EventDelivery,
    EventType,
    NodeConnection,
)
from django_rest_replication.models.sync_cursor import SyncCursor
from django_rest_replication.routing.cursor import (
    advance_cursor,
    get_or_create_cursor,
    mark_snapshot_complete,
    needs_snapshot,
)


def make_node(**kwargs: object) -> NodeConnection:
    defaults: dict[str, object] = {
        "name": "peer",
        "base_url": "https://peer.example.com",
        "node_id": uuid.uuid4(),
        "direction": Direction.BOTH,
        "auth_token": f"tok-{uuid.uuid4().hex}",
        "is_active": True,
    }
    defaults.update(kwargs)
    return NodeConnection.objects.create(**defaults)


def make_event(**kwargs: object) -> ChangeEvent:
    defaults: dict[str, object] = {
        "node_id": uuid.uuid4(),
        "event_type": EventType.CREATE,
        "model_label": "testapp.Product",
        "object_id": str(uuid.uuid4()),
        "payload": {"name": "Widget"},
    }
    defaults.update(kwargs)
    return ChangeEvent.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCursorHelpers:
    def test_get_or_create_cursor_creates(self) -> None:
        node = make_node()
        cursor = get_or_create_cursor(node)
        assert cursor.node == node
        assert cursor.tenant_id == ""

    def test_get_or_create_cursor_idempotent(self) -> None:
        node = make_node()
        c1 = get_or_create_cursor(node)
        c2 = get_or_create_cursor(node)
        assert c1.pk == c2.pk

    def test_needs_snapshot_true_when_no_snapshot(self) -> None:
        node = make_node()
        cursor = get_or_create_cursor(node)
        assert needs_snapshot(cursor) is True

    def test_needs_snapshot_false_after_complete(self) -> None:
        node = make_node()
        cursor = get_or_create_cursor(node)
        mark_snapshot_complete(cursor, None)
        cursor.refresh_from_db()
        assert needs_snapshot(cursor) is False

    def test_advance_cursor_updates_last_event(self) -> None:
        node = make_node()
        event = make_event()
        cursor = get_or_create_cursor(node)
        advance_cursor(cursor, uuid.UUID(str(event.pk)))
        cursor.refresh_from_db()
        assert cursor.last_event_id == event.pk

    def test_mark_snapshot_complete_sets_watermark(self) -> None:
        node = make_node()
        event = make_event()
        cursor = get_or_create_cursor(node)
        mark_snapshot_complete(cursor, uuid.UUID(str(event.pk)))
        cursor.refresh_from_db()
        assert cursor.snapshot_completed_at is not None
        assert cursor.last_event_id == event.pk


# ---------------------------------------------------------------------------
# run_pull — bootstrap (snapshot needed)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_pull_bootstrap_applies_snapshot_rows(httpx_mock: Any) -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product_id = str(uuid.uuid4())

    node = make_node(base_url="https://peer.example.com", direction=Direction.PULL)

    # Mock manifest
    httpx_mock.add_response(
        url="https://peer.example.com/replication/snapshot/manifest/",
        json={
            "watermark": None,
            "models": ["testapp.Product"],
        },
    )

    # Mock snapshot page
    httpx_mock.add_response(
        url="https://peer.example.com/replication/snapshot/?model=testapp.Product&limit=500",
        json={
            "model": "testapp.Product",
            "next_cursor": None,
            "has_more": False,
            "rows": [
                {
                    "id": product_id,
                    "name": "Remote Widget",
                    "price": "9.99",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                }
            ],
        },
    )

    from django_rest_replication.routing.puller import run_pull

    run_pull(node)

    # Product should have been created
    assert Product.objects.filter(pk=product_id).exists()

    # Cursor should be marked as bootstrapped
    cursor = SyncCursor.objects.get(node=node)
    assert cursor.snapshot_completed_at is not None


@pytest.mark.django_db
def test_run_pull_incremental_advances_cursor(httpx_mock: Any) -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    node = make_node(base_url="https://peer.example.com", direction=Direction.PULL)

    # Mark snapshot as already done
    cursor = get_or_create_cursor(node)
    mark_snapshot_complete(cursor, None)
    cursor.refresh_from_db()
    assert not needs_snapshot(cursor)

    product_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # Mock events endpoint
    httpx_mock.add_response(
        url="https://peer.example.com/replication/events/?limit=500",
        json=[
            {
                "id": event_id,
                "node_id": str(uuid.uuid4()),
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": product_id,
                "tenant_id": None,
                "payload": {
                    "id": product_id,
                    "name": "Streamed Widget",
                    "price": "5.00",
                    "organization_id": str(org.pk),
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
                "old_payload": None,
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ],
    )

    from django_rest_replication.routing.puller import run_pull

    run_pull(node)

    # Product should be created
    assert Product.objects.filter(pk=product_id).exists()
    # Cursor should have advanced
    cursor.refresh_from_db()
    assert cursor.last_event_id is not None


# ---------------------------------------------------------------------------
# run_push
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_push_delivers_pending_events(httpx_mock: Any) -> None:
    node = make_node(base_url="https://peer.example.com", direction=Direction.PUSH)
    event = make_event()
    delivery = EventDelivery.objects.create(event=event, node=node)
    assert delivery.status == DeliveryStatus.PENDING

    httpx_mock.add_response(
        url="https://peer.example.com/replication/events/",
        json={"created": [str(event.pk)]},
        status_code=201,
    )

    from django_rest_replication.routing.pusher import run_push

    run_push(node)

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.DELIVERED
    assert delivery.delivered_at is not None


@pytest.mark.django_db
def test_run_push_marks_failed_on_http_error(httpx_mock: Any) -> None:
    import httpx as _httpx

    node = make_node(base_url="https://peer.example.com", direction=Direction.PUSH)
    event = make_event()
    delivery = EventDelivery.objects.create(event=event, node=node)

    # Simulate connection error
    httpx_mock.add_exception(
        _httpx.ConnectError("Connection refused"),
        url="https://peer.example.com/replication/events/",
    )

    from django_rest_replication.routing.pusher import run_push

    run_push(node)

    delivery.refresh_from_db()
    # After 1 attempt (< MAX_RETRIES=3), should still be PENDING
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.last_error != ""
