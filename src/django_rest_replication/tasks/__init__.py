"""Task backend — public API."""

from __future__ import annotations

from django_rest_replication.tasks.base import BaseTaskBackend
from django_rest_replication.tasks.sync import SynchronousTaskBackend

__all__ = [
    "BaseTaskBackend",
    "SynchronousTaskBackend",
]
