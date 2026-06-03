"""Backend adapter — public API."""

from __future__ import annotations

from django_rest_replication.backend.base import BaseReplicationBackend, ConflictResolution
from django_rest_replication.backend.default import ReplicationBackend

__all__ = [
    "BaseReplicationBackend",
    "ConflictResolution",
    "ReplicationBackend",
]
