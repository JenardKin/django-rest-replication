"""
Change capture signal handlers.

These are the only entry points for recording model changes. Each handler
is intentionally thin — guard checks, then delegate to the capture pipeline.

Registered in DjangoRESTReplicationConfig.ready() to avoid AppRegistryNotReady.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_save

from django_rest_replication.capture.serializer import serialize_instance
from django_rest_replication.conf import app_settings
from django_rest_replication.models.change_event import EventType
from django_rest_replication.models.mixins import ReplicatedModel

# ---------------------------------------------------------------------------
# Loop prevention — thread-local flag to break capture cycles
# ---------------------------------------------------------------------------

_creating: threading.local = threading.local()


def get_loop_prevention_flag() -> bool:
    """Return True if we are currently inside a replication apply operation."""
    return bool(getattr(_creating, "active", False))


def set_loop_prevention_flag(value: bool) -> None:
    """Set the loop-prevention flag for the current thread."""
    _creating.active = value


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _serialize_old_payload(
    sender: type[models.Model],
    instance: models.Model,
    **kwargs: Any,
) -> None:
    """
    pre_save: stash the current DB state before the save overwrites it.

    Only runs when updating an existing record (not on INSERT).
    """
    if kwargs.get("raw"):
        return
    if not isinstance(instance, ReplicatedModel):
        return
    # _state.adding=True means this is a new row — no old payload to capture
    if instance._state.adding:
        instance.__replication_old_payload__ = None  # type: ignore[attr-defined]
        return
    try:
        db_instance = sender.objects.get(pk=instance.pk)
        instance.__replication_old_payload__ = serialize_instance(db_instance)  # type: ignore[attr-defined]
    except sender.DoesNotExist:
        instance.__replication_old_payload__ = None  # type: ignore[attr-defined]


def _handle_post_save(
    sender: type[models.Model],
    instance: models.Model,
    created: bool,
    **kwargs: Any,
) -> None:
    """post_save: write a CREATE or UPDATE ChangeEvent inside on_commit."""
    if kwargs.get("raw"):
        return
    if not isinstance(instance, ReplicatedModel):
        return
    if get_loop_prevention_flag():
        return
    if not instance.should_replicate():
        return

    event_type = EventType.CREATE if created else EventType.UPDATE
    payload = serialize_instance(instance)
    old_payload: dict[str, Any] | None = getattr(
        instance, "__replication_old_payload__", None
    )
    node_id = uuid.UUID(str(app_settings.NODE_ID))
    model_label = f"{instance._meta.app_label}.{instance._meta.object_name}"
    object_id = str(instance.pk)
    tenant_id: str | None = instance.get_tenant_id()

    def _commit() -> None:
        from django_rest_replication.models.change_event import ChangeEvent

        event = ChangeEvent.objects.create(
            node_id=node_id,
            event_type=event_type,
            model_label=model_label,
            object_id=object_id,
            tenant_id=tenant_id,
            payload=payload,
            old_payload=old_payload if event_type == EventType.UPDATE else None,
        )
        app_settings.BACKEND().on_event_captured(event)
        app_settings.TASK_BACKEND().enqueue_delivery(event)

    transaction.on_commit(_commit)


def _handle_post_delete(
    sender: type[models.Model],
    instance: models.Model,
    **kwargs: Any,
) -> None:
    """post_delete: write a DELETE ChangeEvent inside on_commit."""
    if not isinstance(instance, ReplicatedModel):
        return
    if get_loop_prevention_flag():
        return
    if not instance.should_replicate():
        return

    node_id = uuid.UUID(str(app_settings.NODE_ID))
    model_label = f"{instance._meta.app_label}.{instance._meta.object_name}"
    object_id = str(instance.pk)
    tenant_id: str | None = instance.get_tenant_id()
    # Capture last known payload before deletion
    payload = serialize_instance(instance)

    def _commit() -> None:
        from django_rest_replication.models.change_event import ChangeEvent

        event = ChangeEvent.objects.create(
            node_id=node_id,
            event_type=EventType.DELETE,
            model_label=model_label,
            object_id=object_id,
            tenant_id=tenant_id,
            payload=payload,
            old_payload=None,
        )
        app_settings.BACKEND().on_event_captured(event)
        app_settings.TASK_BACKEND().enqueue_delivery(event)

    transaction.on_commit(_commit)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def connect_signals() -> None:
    """Wire up Django signals for all ReplicatedModel subclasses."""
    pre_save.connect(_serialize_old_payload, sender=None, dispatch_uid="replication_pre_save")
    post_save.connect(_handle_post_save, sender=None, dispatch_uid="replication_post_save")
    post_delete.connect(
        _handle_post_delete, sender=None, dispatch_uid="replication_post_delete"
    )
