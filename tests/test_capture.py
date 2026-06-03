"""Phase 3 tests — change capture."""

from __future__ import annotations

import uuid

import pytest

from django_rest_replication.capture.signals import (
    get_loop_prevention_flag,
    set_loop_prevention_flag,
)
from django_rest_replication.models import ChangeEvent, EventType


def make_org() -> object:
    from tests.testapp.models import Organization

    return Organization.objects.create(name="ACME")


# ---------------------------------------------------------------------------
# Serializer unit tests
# ---------------------------------------------------------------------------


class TestSerializeInstance:
    def test_basic_fields_serialized(self) -> None:
        from django_rest_replication.capture.serializer import serialize_instance
        from tests.testapp.models import Organization

        org = Organization(name="X")
        # Don't save — just serialize
        result = serialize_instance(org)
        assert result["name"] == "X"

    @pytest.mark.django_db
    def test_uuid_serialized_as_str(self) -> None:
        from django_rest_replication.capture.serializer import serialize_instance
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name="Test")
        p = Product(id=uuid.uuid4(), name="Widget", price="9.99", organization=org)
        result = serialize_instance(p)
        assert isinstance(result["id"], str)

    @pytest.mark.django_db
    def test_decimal_serialized_as_str(self) -> None:
        import decimal

        from django_rest_replication.capture.serializer import serialize_instance
        from tests.testapp.models import Organization, Product

        org = Organization.objects.create(name="Test")
        p = Product(id=uuid.uuid4(), name="Widget", price=decimal.Decimal("9.99"), organization=org)
        result = serialize_instance(p)
        assert isinstance(result["price"], str)
        assert result["price"] == "9.99"


# ---------------------------------------------------------------------------
# CREATE event
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_create_product_generates_create_event() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    before = ChangeEvent.objects.count()
    Product.objects.create(name="Gadget", price="5.00", organization=org)
    after = ChangeEvent.objects.count()
    assert after == before + 1
    event = ChangeEvent.objects.order_by("-created_at").first()
    assert event is not None
    assert event.event_type == EventType.CREATE
    assert event.model_label == "testapp.Product"


# ---------------------------------------------------------------------------
# UPDATE event
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_update_product_generates_update_event_with_old_payload() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product = Product.objects.create(name="Gadget", price="5.00", organization=org)
    # Clear any CREATE events
    ChangeEvent.objects.all().delete()

    product.name = "Updated Gadget"
    product.save()

    events = ChangeEvent.objects.filter(event_type=EventType.UPDATE)
    assert events.count() == 1
    event = events.first()
    assert event is not None
    assert event.old_payload is not None
    assert event.old_payload["name"] == "Gadget"
    assert event.payload["name"] == "Updated Gadget"


# ---------------------------------------------------------------------------
# DELETE event
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_delete_product_generates_delete_event() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")
    product = Product.objects.create(name="Doomed", price="1.00", organization=org)
    ChangeEvent.objects.all().delete()

    pk = str(product.pk)
    product.delete()

    events = ChangeEvent.objects.filter(event_type=EventType.DELETE)
    assert events.count() == 1
    event = events.first()
    assert event is not None
    assert event.object_id == pk


# ---------------------------------------------------------------------------
# should_replicate=False suppresses event
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_should_replicate_false_suppresses_event() -> None:
    from tests.testapp.models import Organization, Product

    # Monkey-patch should_replicate on the instance
    org = Organization.objects.create(name="ACME")
    product = Product(name="Hidden", price="0.00", organization=org)
    product.should_replicate = lambda: False  # type: ignore[method-assign]

    before = ChangeEvent.objects.count()
    product.save()
    after = ChangeEvent.objects.count()
    assert after == before  # no new events


# ---------------------------------------------------------------------------
# Loop prevention
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_loop_prevention_flag_prevents_event_creation() -> None:
    from tests.testapp.models import Organization, Product

    org = Organization.objects.create(name="ACME")

    set_loop_prevention_flag(True)
    try:
        before = ChangeEvent.objects.count()
        Product.objects.create(name="Silent", price="0.00", organization=org)
        after = ChangeEvent.objects.count()
        assert after == before  # flag blocked capture
    finally:
        set_loop_prevention_flag(False)


def test_loop_prevention_flag_default_false() -> None:
    assert get_loop_prevention_flag() is False


def test_loop_prevention_flag_can_be_set() -> None:
    set_loop_prevention_flag(True)
    assert get_loop_prevention_flag() is True
    set_loop_prevention_flag(False)
    assert get_loop_prevention_flag() is False
