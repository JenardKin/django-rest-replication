"""Phase 4 tests — task backends."""

from __future__ import annotations

import uuid

import pytest

from django_rest_replication.tasks import BaseTaskBackend, SynchronousTaskBackend


class TestTaskBackendImport:
    def test_synchronous_backend_importable(self) -> None:
        from django.utils.module_loading import import_string

        cls = import_string("django_rest_replication.tasks.sync.SynchronousTaskBackend")
        assert cls is SynchronousTaskBackend

    def test_base_task_backend_is_abstract(self) -> None:
        import inspect

        assert inspect.isabstract(BaseTaskBackend)

    def test_synchronous_backend_is_subclass(self) -> None:
        assert issubclass(SynchronousTaskBackend, BaseTaskBackend)


@pytest.mark.django_db(transaction=True)
class TestSynchronousTaskBackend:
    def _make_event(self) -> object:
        from django_rest_replication.models import ChangeEvent, EventType

        return ChangeEvent.objects.create(
            node_id=uuid.uuid4(),
            event_type=EventType.CREATE,
            model_label="testapp.Product",
            object_id=str(uuid.uuid4()),
            payload={},
        )

    def test_enqueue_delivery_does_not_raise(self) -> None:
        backend = SynchronousTaskBackend()
        event = self._make_event()
        from django_rest_replication.models import ChangeEvent

        assert isinstance(event, ChangeEvent)
        # Should not raise even though pusher is not yet fully wired
        backend.enqueue_delivery(event)

    def test_enqueue_pull_does_not_raise(self) -> None:
        backend = SynchronousTaskBackend()
        node_id = uuid.uuid4()
        # Should not raise
        backend.enqueue_pull(node_id)
        backend.enqueue_pull(node_id, tenant_id="tenant-1")
