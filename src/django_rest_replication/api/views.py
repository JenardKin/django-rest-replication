"""Replication REST API views."""

from __future__ import annotations

import uuid
from typing import Any

from django.apps import apps
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django_rest_replication.api.auth import NodeTokenAuthentication
from django_rest_replication.api.permissions import IsAuthenticatedNode
from django_rest_replication.api.serializers import ChangeEventSerializer
from django_rest_replication.api.snapshot import (
    build_snapshot_queryset,
    get_current_watermark,
    get_replicated_models,
)
from django_rest_replication.capture.serializer import serialize_instance
from django_rest_replication.conf import app_settings
from django_rest_replication.models import ChangeEvent, DeliveryStatus, EventDelivery
from django_rest_replication.models.mixins import ReplicatedModel
from django_rest_replication.models.node_connection import NodeConnection


def _parse_uuid(value: str) -> uuid.UUID | None:
    """Safely parse a UUID from a string query param."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


class EventView(APIView):
    """
    Unified GET/POST endpoint for events.

    GET  /replication/events/ — pull events since ``after``
    POST /replication/events/ — push events from a peer
    """

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticatedNode]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return ChangeEvents for the requesting peer since ``after``."""
        node: NodeConnection = request.user  # type: ignore[assignment]

        after_str = request.query_params.get("after")
        after = _parse_uuid(after_str) if after_str else None

        try:
            limit = min(
                int(request.query_params.get("limit", app_settings.BATCH_SIZE)),
                app_settings.BATCH_SIZE,
            )
        except (ValueError, TypeError):
            limit = app_settings.BATCH_SIZE

        # Don't send the node its own events back
        qs = ChangeEvent.objects.exclude(node_id=node.node_id).order_by("id")
        if after is not None:
            qs = qs.filter(id__gt=after)
        qs = qs[:limit]

        serializer = ChangeEventSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Accept a list of ChangeEvents from a peer and persist them."""
        data = request.data
        if not isinstance(data, list):
            return Response(
                {"detail": "Expected a list of events."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_ids: list[str] = []
        for item in data:
            serializer = ChangeEventSerializer(data=item)
            if serializer.is_valid():
                # Check for duplicates
                event_id = item.get("id")
                if event_id and ChangeEvent.objects.filter(pk=event_id).exists():
                    created_ids.append(str(event_id))
                    continue
                event = serializer.save()
                created_ids.append(str(event.pk))
                # Enqueue application via task backend
                try:
                    app_settings.TASK_BACKEND().enqueue_delivery(event)
                except Exception:
                    pass
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({"created": created_ids}, status=status.HTTP_201_CREATED)


class AckView(APIView):
    """POST /replication/ack/ — mark EventDelivery records as DELIVERED."""

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticatedNode]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        node: NodeConnection = request.user  # type: ignore[assignment]
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"detail": 'Expected {"event_ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_ids = data.get("event_ids", [])
        if not isinstance(event_ids, list):
            return Response(
                {"detail": "event_ids must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.utils import timezone

        updated = EventDelivery.objects.filter(
            event_id__in=event_ids,
            node=node,
            status=DeliveryStatus.PENDING,
        ).update(
            status=DeliveryStatus.DELIVERED,
            delivered_at=timezone.now(),
        )
        return Response({"acknowledged": updated})


class SnapshotManifestView(APIView):
    """GET /replication/snapshot/manifest/ — return watermark + model list."""

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticatedNode]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        models_list = get_replicated_models()
        labels = [f"{m._meta.app_label}.{m._meta.object_name}" for m in models_list]
        watermark = get_current_watermark()
        return Response(
            {
                "watermark": str(watermark) if watermark else None,
                "models": labels,
            }
        )


class SnapshotView(APIView):
    """GET /replication/snapshot/ — keyset-paginated snapshot of a model."""

    authentication_classes = [NodeTokenAuthentication]
    permission_classes = [IsAuthenticatedNode]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        model_label = request.query_params.get("model", "")
        if not model_label or "." not in model_label:
            return Response(
                {"detail": "model query param required (format: app_label.ModelName)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_label, model_name = model_label.split(".", 1)
        try:
            model_cls = apps.get_model(app_label, model_name)
        except LookupError:
            return Response(
                {"detail": f"Model '{model_label}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not issubclass(model_cls, ReplicatedModel):
            return Response(
                {"detail": f"Model '{model_label}' is not a ReplicatedModel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        after_str = request.query_params.get("after")
        after = _parse_uuid(after_str) if after_str else None

        try:
            limit = min(
                int(request.query_params.get("limit", app_settings.BATCH_SIZE)),
                app_settings.BATCH_SIZE,
            )
        except (ValueError, TypeError):
            limit = app_settings.BATCH_SIZE

        qs = build_snapshot_queryset(model_cls, after)
        page = list(qs[: limit + 1])
        has_more = len(page) > limit
        rows = page[:limit]

        next_cursor: str | None = None
        if has_more and rows:
            next_cursor = str(rows[-1].pk)

        serialized_rows = [serialize_instance(row) for row in rows]

        return Response(
            {
                "model": model_label,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "rows": serialized_rows,
            }
        )
