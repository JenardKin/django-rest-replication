"""Phase 7 tests — event application."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from django_rest_replication.application.applier import apply_event, apply_snapshot_row
from django_rest_replication.application.conflicts import ConflictStrategy, resolve
from django_rest_replication.backend.base import ConflictResolution
from django_rest_replication.models import ChangeEvent, EventType


def make_node(**kwargs: object) -> object:
    from django_rest_replication.models import Direction, NodeConnection

    defaults: dict[str, object] = {
        "name": "test-node",
        "base_url": "https://peer.example.com",
        "node_id": uuid.uuid4(),
        "direction": Direction.BOTH,
        "auth_token": "secret",
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
# apply_event — CREATE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_create_event_creates_object() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product_id = str(uuid.uuid4())

    event = make_event(
        object_id=product_id,
        event_type=EventType.CREATE,
        payload={
            "id": product_id,
            "name": "New Product",
            "price": "12.00",
            "organization_id": str(org.pk),
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        },
    )
    result = apply_event(event)
    assert result is True
    assert Product.objects.filter(pk=product_id).exists()
    p = Product.objects.get(pk=product_id)
    assert p.name == "New Product"


# ---------------------------------------------------------------------------
# apply_event — UPDATE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_update_event_updates_object() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    existing = Product.objects.create(name="Old Name", price="1.00", organization=org)

    event = make_event(
        object_id=str(existing.pk),
        event_type=EventType.UPDATE,
        payload={
            "id": str(existing.pk),
            "name": "New Name",
            "price": "2.00",
            "organization_id": str(org.pk),
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-02T00:00:00+00:00",
        },
    )
    result = apply_event(event)
    assert result is True
    existing.refresh_from_db()
    assert existing.name == "New Name"


# ---------------------------------------------------------------------------
# apply_event — DELETE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_delete_event_deletes_object() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product = Product.objects.create(name="Doomed", price="1.00", organization=org)
    pk = str(product.pk)

    event = make_event(
        object_id=pk,
        event_type=EventType.DELETE,
        payload={},
    )
    result = apply_event(event)
    assert result is True
    assert not Product.objects.filter(pk=pk).exists()


# ---------------------------------------------------------------------------
# on_before_apply returns False → skip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_on_before_apply_false_skips_event() -> None:
    from django.test import override_settings

    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product_id = str(uuid.uuid4())
    event = make_event(
        object_id=product_id,
        event_type=EventType.CREATE,
        payload={"id": product_id, "name": "X", "price": "1.00", "organization_id": str(org.pk)},
    )

    class SkipBackend:
        def on_before_apply(self, e: ChangeEvent) -> bool:
            return False

        def on_after_apply(self, e: ChangeEvent) -> None:
            pass

        def on_event_captured(self, e: ChangeEvent) -> None:
            pass

        def on_delivery_failed(self, d: object) -> None:
            pass

        def resolve_conflict(self, local: object, e: ChangeEvent) -> ConflictResolution:
            return ConflictResolution.USE_REMOTE

    with override_settings(
        DJANGO_REPLICATION={
            "NODE_ID": "00000000-0000-0000-0000-000000000001",
            "BACKEND": "django_rest_replication.backend.ReplicationBackend",
            "TASK_BACKEND": "django_rest_replication.tasks.sync.SynchronousTaskBackend",
        }
    ):
        # Patch app_settings.BACKEND directly
        from django_rest_replication import conf

        original = conf.app_settings.BACKEND
        conf.app_settings._cache["BACKEND"] = SkipBackend
        try:
            result = apply_event(event)
        finally:
            conf.app_settings._cache["BACKEND"] = original

    assert result is False
    assert not Product.objects.filter(pk=product_id).exists()


# ---------------------------------------------------------------------------
# Conflict resolution strategies
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_last_write_wins_remote_replaces_local() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product = Product.objects.create(name="Old", price="1.00", organization=org)

    from django_rest_replication.backend.default import ReplicationBackend

    backend = ReplicationBackend()
    event = make_event(object_id=str(product.pk), event_type=EventType.UPDATE)
    resolution = resolve(ConflictStrategy.LAST_WRITE_WINS, product, event, backend)
    assert resolution == ConflictResolution.USE_REMOTE


@pytest.mark.django_db
def test_skip_if_newer_local_wins_when_newer() -> None:
    import datetime

    from django.utils import timezone

    from tests.testapp.models import Organization, Product
    from django_rest_replication.backend.default import ReplicationBackend

    org = Organization.objects.create(name="ACME")
    product = Product.objects.create(name="Old", price="1.00", organization=org)

    backend = ReplicationBackend()
    event = make_event(object_id=str(product.pk), event_type=EventType.UPDATE)
    # Manually set event.created_at to be older than product.updated_at
    ChangeEvent.objects.filter(pk=event.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=1)
    )
    event.refresh_from_db()

    resolution = resolve(ConflictStrategy.SKIP_IF_NEWER, product, event, backend)
    assert resolution == ConflictResolution.USE_LOCAL


# ---------------------------------------------------------------------------
# Loop prevention during apply
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_loop_prevention_during_apply() -> None:
    """Signals should not fire when the loop-prevention flag is set."""
    from tests.testapp.models import Organization, Product

    from django_rest_replication.capture.signals import get_loop_prevention_flag

    org = Organization.objects.create(name="ACME")
    product_id = str(uuid.uuid4())
    event = make_event(
        object_id=product_id,
        event_type=EventType.CREATE,
        payload={
            "id": product_id,
            "name": "Loop Test",
            "price": "1.00",
            "organization_id": str(org.pk),
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        },
    )

    initial_event_count = ChangeEvent.objects.count()
    apply_event(event)
    # The apply should not generate additional ChangeEvents
    final_event_count = ChangeEvent.objects.count()
    assert final_event_count == initial_event_count


# ---------------------------------------------------------------------------
# apply_snapshot_row
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_snapshot_row_creates_object() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product_id = str(uuid.uuid4())
    row = {
        "id": product_id,
        "name": "Snapshot Product",
        "price": "5.00",
        "organization_id": str(org.pk),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    result = apply_snapshot_row("testapp.Product", row)
    assert result is True
    assert Product.objects.filter(pk=product_id).exists()
