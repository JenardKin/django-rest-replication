"""
ReplicatedModel — abstract base class for models that participate in replication.

Usage:
    from django_rest_replication.models.mixins import ReplicatedModel

    class Product(ReplicatedModel):
        name = models.CharField(max_length=255)
        ...
"""

from __future__ import annotations

from django.db import models

from django_rest_replication.utils import uuid7


class ReplicatedModel(models.Model):
    """
    Abstract mixin that marks a model for replication.

    Provides:
    - UUID v7 primary key (time-ordered, cursor-friendly)
    - should_replicate() hook — override to exclude specific rows
    - get_tenant_id() hook — override to return the tenant identifier for this row
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid7,
        editable=False,
    )

    class Meta:
        abstract = True

    def should_replicate(self) -> bool:
        """Return False to exclude this instance from replication."""
        return True

    def get_tenant_id(self) -> str | None:
        """
        Return the tenant identifier for this instance.

        Override to support multi-tenancy.  Return None for single-tenant setups.
        """
        return None
