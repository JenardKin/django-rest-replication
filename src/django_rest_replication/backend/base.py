"""Abstract backend interface — users subclass this to inject business logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db import models as django_models

    from django_rest_replication.models import ChangeEvent, EventDelivery


class ConflictResolution(str, Enum):
    USE_LOCAL = "USE_LOCAL"
    USE_REMOTE = "USE_REMOTE"


class BaseReplicationBackend(ABC):
    @abstractmethod
    def on_event_captured(self, event: ChangeEvent) -> None: ...

    @abstractmethod
    def on_before_apply(self, event: ChangeEvent) -> bool: ...  # False = skip

    @abstractmethod
    def on_after_apply(self, event: ChangeEvent) -> None: ...

    @abstractmethod
    def on_delivery_failed(self, delivery: EventDelivery) -> None: ...

    @abstractmethod
    def resolve_conflict(
        self, local: django_models.Model, event: ChangeEvent
    ) -> ConflictResolution: ...
