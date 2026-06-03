"""Django admin registration for replication models."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from django_rest_replication.models import (
    ChangeEvent,
    EventDelivery,
    NodeConnection,
    ReplicationPolicy,
    SyncCursor,
)


class ReplicationPolicyInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReplicationPolicy
    extra = 0
    fields = ["model_label", "included_fields", "excluded_fields", "is_active"]


@admin.register(NodeConnection)
class NodeConnectionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "base_url", "direction", "is_active"]
    list_filter = ["direction", "is_active"]
    search_fields = ["name", "base_url"]
    inlines = [ReplicationPolicyInline]


@admin.register(ChangeEvent)
class ChangeEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["event_type", "model_label", "object_id", "node_id", "created_at"]
    list_filter = ["event_type", "model_label"]
    search_fields = ["model_label", "object_id"]
    readonly_fields = [f.name for f in ChangeEvent._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(EventDelivery)
class EventDeliveryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["event", "node", "status", "attempts", "delivered_at"]
    list_filter = ["status"]
    search_fields = ["event__model_label", "node__name"]
    actions = ["retry_failed"]

    @admin.action(description="Retry failed deliveries")
    def retry_failed(
        self,
        request: HttpRequest,
        queryset: QuerySet[EventDelivery],
    ) -> None:
        from django_rest_replication.models.event_delivery import DeliveryStatus

        queryset.filter(status=DeliveryStatus.FAILED).update(
            status=DeliveryStatus.PENDING,
            last_error="",
        )


@admin.register(SyncCursor)
class SyncCursorAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["node", "tenant_id", "last_event_id", "snapshot_completed_at"]
    search_fields = ["node__name", "tenant_id"]
    actions = ["reset_cursor"]

    @admin.action(description="Reset cursor to beginning")
    def reset_cursor(
        self,
        request: HttpRequest,
        queryset: QuerySet[SyncCursor],
    ) -> None:
        queryset.update(
            last_event=None,
            snapshot_completed_at=None,
        )
