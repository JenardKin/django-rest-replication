"""Abstract task backend interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django_rest_replication.models import ChangeEvent


class BaseTaskBackend(ABC):
    @abstractmethod
    def enqueue_delivery(self, event: ChangeEvent) -> None:
        """Enqueue delivery of the given event to all target nodes."""
        ...

    @abstractmethod
    def enqueue_pull(self, node_id: uuid.UUID, tenant_id: str | None = None) -> None:
        """Enqueue a pull operation from the given node."""
        ...
