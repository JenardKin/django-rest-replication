"""Snapshot helpers: model discovery, watermark, keyset pagination."""

from __future__ import annotations

import uuid
from typing import Any

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import QuerySet

from django_rest_replication.models.mixins import ReplicatedModel


def get_replicated_models() -> list[type[ReplicatedModel]]:
    """
    Return all registered ReplicatedModel subclasses in topological order.

    Parents (models whose FKs point to other replicated models) are returned
    before their children so that snapshot import can satisfy FK constraints.

    Raises ``ImproperlyConfigured`` if a dependency cycle is detected.
    """
    replicated: list[type[ReplicatedModel]] = [
        m  # type: ignore[misc]
        for m in apps.get_models()
        if issubclass(m, ReplicatedModel) and not m._meta.abstract
    ]

    # Build dependency graph: child → {parents} (only replicated parents)
    replicated_set = set(replicated)
    deps: dict[type[ReplicatedModel], set[type[ReplicatedModel]]] = {
        m: set() for m in replicated
    }
    for model in replicated:
        for field in model._meta.get_fields():
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            related: type[models.Model] = field.related_model  # type: ignore[assignment]
            if related in replicated_set and related is not model:
                deps[model].add(related)  # type: ignore[index]

    # Kahn's algorithm
    result: list[type[ReplicatedModel]] = []
    in_degree = {m: len(parents) for m, parents in deps.items()}
    queue = [m for m, degree in in_degree.items() if degree == 0]

    while queue:
        node = queue.pop(0)
        result.append(node)
        # Find models that depended on this one
        for child, parents in deps.items():
            if node in parents:
                parents.discard(node)
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

    if len(result) != len(replicated):
        raise ImproperlyConfigured(
            "Circular FK dependency detected among ReplicatedModel subclasses."
        )

    return result


def get_current_watermark() -> uuid.UUID | None:
    """Return the current max ChangeEvent.id (UUID v7 = most recent)."""
    from django_rest_replication.models import ChangeEvent

    last = ChangeEvent.objects.order_by("-id").values_list("id", flat=True).first()
    if last is None:
        return None
    return uuid.UUID(str(last))


def build_snapshot_queryset(
    model: type[models.Model], after: uuid.UUID | None
) -> QuerySet[Any]:
    """Keyset-paginated queryset: objects with id > after, ordered by id."""
    qs = model.objects.order_by("id")
    if after is not None:
        qs = qs.filter(id__gt=after)
    return qs
