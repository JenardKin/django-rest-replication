"""URL configuration for the replication API."""

from __future__ import annotations

from django.urls import path

from django_rest_replication.api.views import (
    AckView,
    EventView,
    SnapshotManifestView,
    SnapshotView,
)

urlpatterns = [
    path("events/", EventView.as_view(), name="replication-events"),
    path("ack/", AckView.as_view(), name="replication-ack"),
    path(
        "snapshot/manifest/", SnapshotManifestView.as_view(), name="replication-snapshot-manifest"
    ),
    path("snapshot/", SnapshotView.as_view(), name="replication-snapshot"),
]
