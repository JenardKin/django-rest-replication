"""Phase 5 tests — REST API."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from django_rest_replication.models import (
    ChangeEvent,
    DeliveryStatus,
    Direction,
    EventDelivery,
    EventType,
    NodeConnection,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_node(**kwargs: object) -> NodeConnection:
    defaults: dict[str, object] = {
        "name": "test-peer",
        "base_url": "https://peer.example.com",
        "node_id": uuid.uuid4(),
        "direction": Direction.BOTH,
        "auth_token": f"token-{uuid.uuid4().hex}",
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


def authed_client(node: NodeConnection) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {node.auth_token}")
    return client


# ---------------------------------------------------------------------------
# Authentication / Authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuth:
    def test_401_when_no_token(self) -> None:
        client = APIClient()
        resp = client.get("/replication/events/")
        assert resp.status_code == 401

    def test_401_with_invalid_token(self) -> None:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token invalid-token-xyz")
        resp = client.get("/replication/events/")
        # AuthenticationFailed → 401 (DRF behaviour with token auth)
        assert resp.status_code == 401

    def test_inactive_node_is_rejected(self) -> None:
        node = make_node(is_active=False)
        client = authed_client(node)
        resp = client.get("/replication/events/")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /replication/events/ — pull
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEventPull:
    def test_returns_events_for_peer(self) -> None:
        node = make_node()
        make_event()
        make_event()
        client = authed_client(node)
        resp = client.get("/replication/events/")
        assert resp.status_code == 200
        assert len(resp.data) == 2  # type: ignore[arg-type]

    def test_does_not_return_own_events(self) -> None:
        node = make_node()
        # Event produced BY this node — should be excluded
        make_event(node_id=node.node_id)
        # Event produced by another node — should be included
        make_event(node_id=uuid.uuid4())
        client = authed_client(node)
        resp = client.get("/replication/events/")
        assert resp.status_code == 200
        assert len(resp.data) == 1  # type: ignore[arg-type]

    def test_after_param_filters_by_cursor(self) -> None:
        node = make_node()
        e1 = make_event()
        e2 = make_event()
        client = authed_client(node)
        resp = client.get(f"/replication/events/?after={e1.pk}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]  # type: ignore[index]
        assert str(e1.pk) not in ids
        assert str(e2.pk) in ids

    def test_limit_param_respected(self) -> None:
        node = make_node()
        for _ in range(5):
            make_event()
        client = authed_client(node)
        resp = client.get("/replication/events/?limit=3")
        assert resp.status_code == 200
        assert len(resp.data) == 3  # type: ignore[arg-type]

    def test_events_ordered_by_id(self) -> None:
        node = make_node()
        e1 = make_event()
        e2 = make_event()
        client = authed_client(node)
        resp = client.get("/replication/events/")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]  # type: ignore[index]
        assert ids.index(str(e1.pk)) < ids.index(str(e2.pk))


# ---------------------------------------------------------------------------
# POST /replication/events/ — push
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEventPush:
    def test_push_creates_events(self) -> None:
        node = make_node()
        client = authed_client(node)
        payload = [
            {
                "id": str(uuid.uuid4()),
                "node_id": str(uuid.uuid4()),
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": str(uuid.uuid4()),
                "payload": {"name": "Remote Widget"},
                "old_payload": None,
                "tenant_id": None,
            }
        ]
        resp = client.post("/replication/events/", payload, format="json")
        assert resp.status_code == 201
        assert len(resp.data["created"]) == 1  # type: ignore[index]
        assert ChangeEvent.objects.filter(
            model_label="testapp.Product", event_type=EventType.CREATE
        ).exists()

    def test_push_requires_list(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.post("/replication/events/", {"not": "a list"}, format="json")
        assert resp.status_code == 400

    def test_push_duplicate_idempotent(self) -> None:
        node = make_node()
        event_id = str(uuid.uuid4())
        # Create it first
        ChangeEvent.objects.create(
            id=event_id,
            node_id=uuid.uuid4(),
            event_type=EventType.CREATE,
            model_label="testapp.Product",
            object_id=str(uuid.uuid4()),
        )
        client = authed_client(node)
        payload = [
            {
                "id": event_id,
                "node_id": str(uuid.uuid4()),
                "event_type": "CREATE",
                "model_label": "testapp.Product",
                "object_id": str(uuid.uuid4()),
                "payload": {},
            }
        ]
        resp = client.post("/replication/events/", payload, format="json")
        assert resp.status_code == 201
        # Should still only have one event with that ID
        assert ChangeEvent.objects.filter(pk=event_id).count() == 1


# ---------------------------------------------------------------------------
# POST /replication/ack/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAckView:
    def test_ack_marks_deliveries_delivered(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.status == DeliveryStatus.PENDING

        client = authed_client(node)
        resp = client.post(
            "/replication/ack/",
            {"event_ids": [str(event.pk)]},
            format="json",
        )
        assert resp.status_code == 200
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.delivered_at is not None

    def test_ack_wrong_node_does_not_update(self) -> None:
        node1 = make_node()
        node2 = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node1)

        client = authed_client(node2)
        resp = client.post(
            "/replication/ack/",
            {"event_ids": [str(event.pk)]},
            format="json",
        )
        assert resp.status_code == 200
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.PENDING


# ---------------------------------------------------------------------------
# GET /replication/snapshot/manifest/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSnapshotManifest:
    def test_manifest_returns_watermark_and_models(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/manifest/")
        assert resp.status_code == 200
        data = resp.data  # type: ignore[union-attr]
        assert "watermark" in data
        assert "models" in data
        assert isinstance(data["models"], list)

    def test_manifest_models_contain_product(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/manifest/")
        assert resp.status_code == 200
        assert "testapp.Product" in resp.data["models"]  # type: ignore[index]

    def test_manifest_watermark_is_none_when_no_events(self) -> None:
        node = make_node()
        ChangeEvent.objects.all().delete()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/manifest/")
        assert resp.status_code == 200
        assert resp.data["watermark"] is None  # type: ignore[index]

    def test_manifest_watermark_is_set_when_events_exist(self) -> None:
        node = make_node()
        event = make_event()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/manifest/")
        assert resp.status_code == 200
        assert resp.data["watermark"] == str(event.pk)  # type: ignore[index]


# ---------------------------------------------------------------------------
# GET /replication/snapshot/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSnapshotView:
    def _make_product(self, name: str = "Widget") -> object:
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name=f"Org-{uuid.uuid4().hex[:6]}")
        return Product.objects.create(name=name, price="9.99", organization=org)

    def test_snapshot_returns_rows(self) -> None:
        node = make_node()
        self._make_product("Widget A")
        self._make_product("Widget B")
        client = authed_client(node)
        resp = client.get("/replication/snapshot/?model=testapp.Product")
        assert resp.status_code == 200
        data = resp.data  # type: ignore[union-attr]
        assert data["model"] == "testapp.Product"
        assert len(data["rows"]) >= 2

    def test_snapshot_keyset_pagination(self) -> None:
        from tests.testapp.models import Organization, Product

        node = make_node()
        org = Organization.objects.create(name="Org")
        products = [
            Product.objects.create(name=f"P{i}", price="1.00", organization=org)
            for i in range(5)
        ]
        client = authed_client(node)

        # First page: limit=2
        resp = client.get("/replication/snapshot/?model=testapp.Product&limit=2")
        assert resp.status_code == 200
        data = resp.data  # type: ignore[union-attr]
        assert len(data["rows"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # Second page
        cursor = data["next_cursor"]
        resp2 = client.get(f"/replication/snapshot/?model=testapp.Product&limit=2&after={cursor}")
        assert resp2.status_code == 200
        data2 = resp2.data  # type: ignore[union-attr]
        # All rows are non-overlapping
        first_ids = {r["id"] for r in data["rows"]}
        second_ids = {r["id"] for r in data2["rows"]}
        assert first_ids.isdisjoint(second_ids)

    def test_snapshot_invalid_model_returns_400(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/?model=invalid")
        assert resp.status_code == 400

    def test_snapshot_nonexistent_model_returns_404(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/?model=testapp.NonExistent")
        assert resp.status_code == 404

    def test_snapshot_non_replicated_model_returns_400(self) -> None:
        node = make_node()
        client = authed_client(node)
        resp = client.get("/replication/snapshot/?model=testapp.Organization")
        assert resp.status_code == 400
