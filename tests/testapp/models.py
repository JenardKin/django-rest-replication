"""
Sample models for the test suite.

These demonstrate the intended usage of django-rest-replication:
  1. Inherit from ReplicatedModel to opt a model into replication
  2. Optionally override should_replicate() for conditional exclusions
  3. Optionally override get_tenant_id() for multi-tenant setups
"""

from django.db import models

from django_rest_replication.models.mixins import ReplicatedModel


class Organization(models.Model):
    """Tenant model — used to test per-tenant cursor isolation."""

    name = models.CharField(max_length=255)

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class Product(ReplicatedModel):
    """Simple replicated model — demonstrates ReplicatedModel in use."""

    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Tenant owner of this record.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    """Many-to-many relationship target — tests M2M change capture."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class ProductTag(models.Model):
    """Explicit through table — tests M2M through-table replication."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "testapp"
        unique_together = (("product", "tag"),)

    def __str__(self) -> str:
        return f"{self.product} — {self.tag}"
