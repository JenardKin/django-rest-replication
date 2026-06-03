"""Apply ChangeEvents to the local database."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.apps import apps
from django.db import models

from django_rest_replication.backend.base import ConflictResolution
from django_rest_replication.capture.signals import set_loop_prevention_flag
from django_rest_replication.conf import app_settings
from django_rest_replication.models.change_event import ChangeEvent, EventType
from django_rest_replication.models.mixins import ReplicatedModel

logger = logging.getLogger(__name__)


def _get_model(model_label: str) -> type[models.Model] | None:
    """Resolve 'app_label.ModelName' → model class or None."""
    try:
        app_label, model_name = model_label.split(".", 1)
        return apps.get_model(app_label, model_name)
    except (LookupError, ValueError):
        logger.error("Cannot resolve model label: %s", model_label)
        return None


def apply_event(
    event: ChangeEvent,
    cursor: object | None = None,
) -> bool:
    """
    Apply a single ChangeEvent to the local DB.

    Returns True if applied, False if skipped.
    """
    from django_rest_replication.models.sync_cursor import SyncCursor
    from django_rest_replication.routing.cursor import advance_cursor

    backend = app_settings.BACKEND()

    # 1. Backend hook — skip if False
    if not backend.on_before_apply(event):
        logger.debug("on_before_apply returned False for event %s — skipping", event.pk)
        return False

    # 2. Resolve model class
    model_cls = _get_model(event.model_label)
    if model_cls is None:
        return False

    payload: dict[str, Any] = event.payload or {}
    object_id = event.object_id

    # 3. Check for existing local instance
    local: models.Model | None = None
    try:
        local = model_cls.objects.get(pk=object_id)
    except model_cls.DoesNotExist:
        pass

    # 4. Conflict detection
    if local is not None and event.event_type != EventType.DELETE:
        resolution = backend.resolve_conflict(local, event)
        if resolution == ConflictResolution.USE_LOCAL:
            logger.debug("Conflict: local wins for %s(%s)", event.model_label, object_id)
            return False

    # 5. Set loop-prevention flag
    set_loop_prevention_flag(True)
    try:
        if event.event_type == EventType.DELETE:
            if local is not None:
                local.delete()
        else:
            # CREATE or UPDATE — upsert
            _apply_payload(model_cls, object_id, payload)
    except Exception:
        logger.exception("Failed to apply event %s (%s)", event.pk, event.event_type)
        return False
    finally:
        # 7. Clear loop-prevention flag
        set_loop_prevention_flag(False)

    # 8. Backend after-apply hook
    try:
        backend.on_after_apply(event)
    except Exception:
        logger.exception("on_after_apply raised for event %s", event.pk)

    # 9. Advance cursor if provided
    if cursor is not None:
        from django_rest_replication.models.sync_cursor import SyncCursor
        from django_rest_replication.routing.cursor import advance_cursor

        if isinstance(cursor, SyncCursor):
            try:
                advance_cursor(cursor, uuid.UUID(str(event.pk)))
            except Exception:
                logger.exception("Failed to advance cursor for event %s", event.pk)

    return True


def _apply_payload(
    model_cls: type[models.Model],
    object_id: str,
    payload: dict[str, Any],
) -> None:
    """Upsert the model instance using the payload dict."""
    # Build defaults from payload, excluding the PK field itself
    pk_field = model_cls._meta.pk
    pk_name = pk_field.attname if pk_field else "id"

    # Separate PK from other fields
    defaults: dict[str, Any] = {}
    for field in model_cls._meta.get_fields():
        if not isinstance(field, models.fields.Field):
            continue
        attr = field.attname
        if attr == pk_name:
            continue
        if attr in payload:
            defaults[attr] = payload[attr]

    model_cls.objects.update_or_create(
        **{pk_name: object_id},
        defaults=defaults,
    )


def apply_snapshot_row(
    model_label: str,
    row: dict[str, Any],
    cursor: object | None = None,
) -> bool:
    """Apply a single snapshot row as an upsert. Same logic as CREATE apply."""
    model_cls = _get_model(model_label)
    if model_cls is None:
        return False

    pk_field = model_cls._meta.pk
    pk_name = pk_field.attname if pk_field else "id"
    object_id = row.get(pk_name) or row.get("id")
    if object_id is None:
        logger.error("Snapshot row missing PK for model %s", model_label)
        return False

    set_loop_prevention_flag(True)
    try:
        _apply_payload(model_cls, str(object_id), row)
    except Exception:
        logger.exception("Failed to apply snapshot row for %s", model_label)
        return False
    finally:
        set_loop_prevention_flag(False)

    return True
