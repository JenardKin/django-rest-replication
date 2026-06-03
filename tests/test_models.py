"""
Phase 1 tests — core models.

Covers:
  - ReplicatedModel: UUID v7 PK default, should_replicate(), get_tenant_id()
  - ChangeEvent: field constraints, __str__, ordering
  - NodeConnection: direction choices, __str__, uniqueness on node_id
  - ReplicationPolicy: unique_together, field defaults, __str__
  - EventDelivery: status default, unique_together, __str__
  - SyncCursor: unique_together, null last_event, __str__
"""

from __future__ import annotations

import uuid

import pytest

from django_rest_replication.models import (
    ChangeEvent,
    DeliveryStatus,
    Direction,
    EventDelivery,
    EventType,
    NodeConnection,
    ReplicatedModel,
    ReplicationPolicy,
    SyncCursor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_node(**kwargs: object) -> NodeConnection:
    defaults: dict[str, object] = {
        "name": "test-node",
        "base_url": "https://peer.example.com",
        "node_id": uuid.uuid4(),
        "direction": Direction.BOTH,
        "auth_token": "secret-token",
    }
    defaults.update(kwargs)
    return NodeConnection.objects.create(**defaults)


def make_event(**kwargs: object) -> ChangeEvent:
    defaults: dict[str, object] = {
        "node_id": uuid.uuid4(),
        "event_type": EventType.CREATE,
        "model_label": "testapp.Product",
        "object_id": str(uuid.uuid4()),
        "payload": {"name": "Widget", "price": "9.99"},
    }
    defaults.update(kwargs)
    return ChangeEvent.objects.create(**defaults)


# ---------------------------------------------------------------------------
# ReplicatedModel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReplicatedModel:
    def test_is_abstract(self) -> None:
        assert ReplicatedModel._meta.abstract is True

    def test_product_has_uuid_pk(self) -> None:
        """Product inherits the UUID v7 primary key from ReplicatedModel."""
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name="ACME")
        product = Product.objects.create(name="Widget", price="9.99", organization=org)
        assert isinstance(product.pk, uuid.UUID)

    def test_should_replicate_default_true(self) -> None:
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name="ACME")
        product = Product.objects.create(name="Widget", price="9.99", organization=org)
        assert product.should_replicate() is True

    def test_get_tenant_id_default_none(self) -> None:
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name="ACME")
        product = Product.objects.create(name="Widget", price="9.99", organization=org)
        assert product.get_tenant_id() is None

    def test_should_replicate_can_be_overridden(self) -> None:
        """Subclasses can override should_replicate to exclude rows."""

        class AlwaysExcluded(ReplicatedModel):
            def should_replicate(self) -> bool:
                return False

            class Meta:
                abstract = True

        instance = AlwaysExcluded.__new__(AlwaysExcluded)
        assert instance.should_replicate() is False

    def test_get_tenant_id_can_be_overridden(self) -> None:
        class TenantAware(ReplicatedModel):
            def get_tenant_id(self) -> str | None:
                return "tenant-42"

            class Meta:
                abstract = True

        instance = TenantAware.__new__(TenantAware)
        assert instance.get_tenant_id() == "tenant-42"


# ---------------------------------------------------------------------------
# ChangeEvent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChangeEvent:
    def test_create_event(self) -> None:
        event = make_event()
        assert event.pk is not None
        assert isinstance(event.pk, uuid.UUID)

    def test_event_type_choices(self) -> None:
        assert EventType.CREATE == "CREATE"
        assert EventType.UPDATE == "UPDATE"
        assert EventType.DELETE == "DELETE"

    def test_tenant_id_nullable(self) -> None:
        event = make_event(tenant_id=None)
        assert event.tenant_id is None

    def test_old_payload_nullable(self) -> None:
        event = make_event(old_payload=None)
        assert event.old_payload is None

    def test_payload_accepts_dict(self) -> None:
        payload = {"name": "Gadget", "price": "19.99"}
        event = make_event(payload=payload)
        event.refresh_from_db()
        assert event.payload == payload

    def test_str(self) -> None:
        event = make_event(event_type=EventType.DELETE, model_label="testapp.Product")
        assert "DELETE" in str(event)
        assert "testapp.Product" in str(event)

    def test_ordering_by_id(self) -> None:
        """Events should be returned in UUID v7 (chronological) order."""
        e1 = make_event()
        e2 = make_event()
        ids = list(ChangeEvent.objects.values_list("id", flat=True))
        assert ids.index(e1.pk) < ids.index(e2.pk)


# ---------------------------------------------------------------------------
# NodeConnection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNodeConnection:
    def test_create_node(self) -> None:
        node = make_node()
        assert node.pk is not None

    def test_direction_choices(self) -> None:
        assert Direction.PUSH == "PUSH"
        assert Direction.PULL == "PULL"
        assert Direction.BOTH == "BOTH"

    def test_default_direction_both(self) -> None:
        node = make_node()
        assert node.direction == Direction.BOTH

    def test_is_active_default_true(self) -> None:
        node = make_node()
        assert node.is_active is True

    def test_node_id_unique(self) -> None:
        from django.db import IntegrityError

        shared_node_id = uuid.uuid4()
        make_node(node_id=shared_node_id)
        with pytest.raises(IntegrityError):
            make_node(node_id=shared_node_id)

    def test_str(self) -> None:
        node_id = uuid.uuid4()
        node = make_node(name="EU Hub", node_id=node_id)
        assert "EU Hub" in str(node)
        assert str(node_id) in str(node)


# ---------------------------------------------------------------------------
# ReplicationPolicy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReplicationPolicy:
    def test_create_policy(self) -> None:
        node = make_node()
        policy = ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        assert policy.pk is not None

    def test_included_fields_default_none(self) -> None:
        node = make_node()
        policy = ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        assert policy.included_fields is None

    def test_excluded_fields_default_empty_list(self) -> None:
        node = make_node()
        policy = ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        assert policy.excluded_fields == []

    def test_is_active_default_true(self) -> None:
        node = make_node()
        policy = ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        assert policy.is_active is True

    def test_unique_together_node_model_label(self) -> None:
        from django.db import IntegrityError

        node = make_node()
        ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        with pytest.raises(IntegrityError):
            ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")

    def test_wildcard_model_label(self) -> None:
        node = make_node()
        policy = ReplicationPolicy.objects.create(node=node, model_label="*")
        assert policy.model_label == "*"

    def test_str(self) -> None:
        node = make_node(name="Spoke A")
        policy = ReplicationPolicy.objects.create(node=node, model_label="testapp.Product")
        assert "testapp.Product" in str(policy)
        assert "Spoke A" in str(policy)


# ---------------------------------------------------------------------------
# EventDelivery
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEventDelivery:
    def test_create_delivery(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.pk is not None

    def test_status_default_pending(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.status == DeliveryStatus.PENDING

    def test_attempts_default_zero(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.attempts == 0

    def test_last_error_default_empty(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.last_error == ""

    def test_delivered_at_default_null(self) -> None:
        node = make_node()
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert delivery.delivered_at is None

    def test_unique_together_event_node(self) -> None:
        from django.db import IntegrityError

        node = make_node()
        event = make_event()
        EventDelivery.objects.create(event=event, node=node)
        with pytest.raises(IntegrityError):
            EventDelivery.objects.create(event=event, node=node)

    def test_delivery_status_choices(self) -> None:
        assert DeliveryStatus.PENDING == "PENDING"
        assert DeliveryStatus.DELIVERED == "DELIVERED"
        assert DeliveryStatus.FAILED == "FAILED"
        assert DeliveryStatus.SKIPPED == "SKIPPED"

    def test_str(self) -> None:
        node = make_node(name="Spoke B")
        event = make_event()
        delivery = EventDelivery.objects.create(event=event, node=node)
        assert "Spoke B" in str(delivery)
        assert "PENDING" in str(delivery)


# ---------------------------------------------------------------------------
# SyncCursor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSyncCursor:
    def test_create_cursor(self) -> None:
        node = make_node()
        cursor = SyncCursor.objects.create(node=node)
        assert cursor.pk is not None

    def test_last_event_default_null(self) -> None:
        node = make_node()
        cursor = SyncCursor.objects.create(node=node)
        assert cursor.last_event_id is None

    def test_tenant_id_default_empty_string(self) -> None:
        node = make_node()
        cursor = SyncCursor.objects.create(node=node)
        assert cursor.tenant_id == ""

    def test_unique_together_node_tenant(self) -> None:
        from django.db import IntegrityError

        node = make_node()
        SyncCursor.objects.create(node=node, tenant_id="")
        with pytest.raises(IntegrityError):
            SyncCursor.objects.create(node=node, tenant_id="")

    def test_multiple_tenants_same_node(self) -> None:
        node = make_node()
        c1 = SyncCursor.objects.create(node=node, tenant_id="tenant-1")
        c2 = SyncCursor.objects.create(node=node, tenant_id="tenant-2")
        assert c1.pk != c2.pk

    def test_advance_cursor(self) -> None:
        node = make_node()
        event = make_event()
        cursor = SyncCursor.objects.create(node=node)
        cursor.last_event_id = event.pk
        cursor.save()
        cursor.refresh_from_db()
        assert cursor.last_event_id == event.pk

    def test_str_no_event(self) -> None:
        node = make_node(name="Spoke C")
        cursor = SyncCursor.objects.create(node=node)
        assert "Spoke C" in str(cursor)
        assert "start" in str(cursor)

    def test_str_with_event(self) -> None:
        node = make_node(name="Spoke C")
        event = make_event()
        cursor = SyncCursor.objects.create(node=node, last_event_id=event.pk)
        assert str(event.pk) in str(cursor)

    def test_snapshot_completed_at_default_null(self) -> None:
        node = make_node()
        cursor = SyncCursor.objects.create(node=node)
        assert cursor.snapshot_completed_at is None

    def test_snapshot_completed_at_can_be_set(self) -> None:
        from django.utils import timezone

        node = make_node()
        cursor = SyncCursor.objects.create(node=node)
        now = timezone.now()
        cursor.snapshot_completed_at = now
        cursor.save()
        cursor.refresh_from_db()
        assert cursor.snapshot_completed_at is not None
