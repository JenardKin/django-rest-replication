"""Phase 2 tests — backend adapter."""

from __future__ import annotations

import uuid

import pytest

from django_rest_replication.backend import (
    BaseReplicationBackend,
    ConflictResolution,
    ReplicationBackend,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event() -> object:
    """Return a minimal ChangeEvent-like object for testing hooks."""
    from django_rest_replication.models import ChangeEvent, EventType

    return ChangeEvent(
        node_id=uuid.uuid4(),
        event_type=EventType.CREATE,
        model_label="testapp.Product",
        object_id=str(uuid.uuid4()),
        payload={},
    )


def make_delivery() -> object:
    """Return a minimal EventDelivery-like object for testing hooks."""
    from django_rest_replication.models import EventDelivery

    return EventDelivery()


# ---------------------------------------------------------------------------
# Import and basic structure
# ---------------------------------------------------------------------------


class TestBackendImport:
    def test_replication_backend_importable_via_dotted_path(self) -> None:
        from django.utils.module_loading import import_string

        cls = import_string("django_rest_replication.backend.ReplicationBackend")
        assert cls is ReplicationBackend

    def test_base_backend_is_abstract(self) -> None:
        import inspect

        assert inspect.isabstract(BaseReplicationBackend)

    def test_conflict_resolution_values(self) -> None:
        assert ConflictResolution.USE_LOCAL == "USE_LOCAL"
        assert ConflictResolution.USE_REMOTE == "USE_REMOTE"


# ---------------------------------------------------------------------------
# ReplicationBackend default behaviour
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReplicationBackend:
    def test_on_before_apply_returns_true(self) -> None:
        backend = ReplicationBackend()
        event = make_event()
        # mypy: event is ChangeEvent at runtime
        from django_rest_replication.models import ChangeEvent

        assert isinstance(event, ChangeEvent)
        assert backend.on_before_apply(event) is True

    def test_resolve_conflict_returns_use_remote(self) -> None:

        backend = ReplicationBackend()
        # local can be any Model instance; use a plain Model stand-in
        from django_rest_replication.models import ChangeEvent, EventType, NodeConnection

        local = NodeConnection()
        event = ChangeEvent(
            node_id=uuid.uuid4(),
            event_type=EventType.CREATE,
            model_label="testapp.Product",
            object_id="x",
        )
        result = backend.resolve_conflict(local, event)
        assert result is ConflictResolution.USE_REMOTE

    def test_on_event_captured_noop(self) -> None:
        backend = ReplicationBackend()
        event = make_event()
        from django_rest_replication.models import ChangeEvent

        assert isinstance(event, ChangeEvent)
        # Should not raise
        backend.on_event_captured(event)

    def test_on_after_apply_noop(self) -> None:
        backend = ReplicationBackend()
        event = make_event()
        from django_rest_replication.models import ChangeEvent

        assert isinstance(event, ChangeEvent)
        backend.on_after_apply(event)

    def test_on_delivery_failed_noop(self) -> None:
        from django_rest_replication.models import EventDelivery

        backend = ReplicationBackend()
        delivery = EventDelivery()
        backend.on_delivery_failed(delivery)


# ---------------------------------------------------------------------------
# Custom subclass
# ---------------------------------------------------------------------------


class TestCustomBackend:
    def test_custom_resolve_conflict_use_local(self) -> None:
        from django_rest_replication.models import ChangeEvent, EventType

        class LocalWinsBackend(ReplicationBackend):
            def resolve_conflict(
                self,
                local: object,
                event: ChangeEvent,
            ) -> ConflictResolution:
                return ConflictResolution.USE_LOCAL

        backend = LocalWinsBackend()
        from django_rest_replication.models import NodeConnection

        local = NodeConnection()
        event = ChangeEvent(
            node_id=uuid.uuid4(),
            event_type=EventType.UPDATE,
            model_label="testapp.Product",
            object_id="y",
        )
        assert backend.resolve_conflict(local, event) is ConflictResolution.USE_LOCAL

    def test_custom_on_before_apply_returns_false(self) -> None:
        from django_rest_replication.models import ChangeEvent, EventType

        class SkipAllBackend(ReplicationBackend):
            def on_before_apply(self, event: ChangeEvent) -> bool:
                return False

        backend = SkipAllBackend()
        event = ChangeEvent(
            node_id=uuid.uuid4(),
            event_type=EventType.CREATE,
            model_label="testapp.Product",
            object_id="z",
        )
        assert backend.on_before_apply(event) is False
