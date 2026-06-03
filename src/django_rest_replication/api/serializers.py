"""DRF serializers for replication API."""

from __future__ import annotations

from rest_framework import serializers

from django_rest_replication.models import ChangeEvent, EventDelivery


class ChangeEventSerializer(serializers.ModelSerializer[ChangeEvent]):
    """Serializer for ChangeEvent (read-only for GET, writable for POST push)."""

    class Meta:
        model = ChangeEvent
        fields = "__all__"


class EventDeliverySerializer(serializers.ModelSerializer[EventDelivery]):
    """Read-only serializer for EventDelivery."""

    class Meta:
        model = EventDelivery
        fields = "__all__"
