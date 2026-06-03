"""Pull engine — bootstraps new nodes and streams incremental events."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from django_rest_replication.conf import app_settings
from django_rest_replication.models.node_connection import Direction, NodeConnection
from django_rest_replication.models.sync_cursor import SyncCursor
from django_rest_replication.routing.cursor import (
    get_or_create_cursor,
    mark_snapshot_complete,
    needs_snapshot,
)

logger = logging.getLogger(__name__)


def _auth_headers(node: NodeConnection) -> dict[str, str]:
    return {"Authorization": f"Token {node.auth_token}"}


def bootstrap_node(node: NodeConnection, cursor: SyncCursor, client: httpx.Client) -> None:
    """
    Phase A: fetch the snapshot manifest, paginate through all rows, apply
    them as upserts, then mark the cursor as bootstrapped.
    """
    from django_rest_replication.application.applier import apply_snapshot_row

    # 1. Fetch manifest
    try:
        resp = client.get(
            f"{node.base_url.rstrip('/')}/replication/snapshot/manifest/",
            headers=_auth_headers(node),
            timeout=app_settings.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch snapshot manifest from %s: %s", node.name, exc)
        return

    manifest: dict[str, Any] = resp.json()
    watermark_str: str | None = manifest.get("watermark")
    watermark: uuid.UUID | None = uuid.UUID(watermark_str) if watermark_str else None
    model_labels: list[str] = manifest.get("models", [])

    # 2. Paginate through each model
    for label in model_labels:
        after: uuid.UUID | None = None
        while True:
            params: dict[str, Any] = {"model": label, "limit": app_settings.BATCH_SIZE}
            if after is not None:
                params["after"] = str(after)
            try:
                page_resp = client.get(
                    f"{node.base_url.rstrip('/')}/replication/snapshot/",
                    params=params,
                    headers=_auth_headers(node),
                    timeout=app_settings.REQUEST_TIMEOUT,
                )
                page_resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("Snapshot page fetch failed for %s: %s", label, exc)
                break

            page_data: dict[str, Any] = page_resp.json()
            rows: list[dict[str, Any]] = page_data.get("rows", [])
            for row in rows:
                try:
                    apply_snapshot_row(label, row, cursor)
                except Exception:
                    logger.exception("Failed to apply snapshot row for %s", label)

            if not page_data.get("has_more"):
                break
            next_cursor_str: str | None = page_data.get("next_cursor")
            if not next_cursor_str:
                break
            after = uuid.UUID(next_cursor_str)

    # 3. Mark snapshot as complete
    mark_snapshot_complete(cursor, watermark)
    logger.info("Snapshot bootstrap complete for node %s", node.name)


def pull_incremental(node: NodeConnection, cursor: SyncCursor, client: httpx.Client) -> None:
    """Phase B: pull ChangeEvents since cursor, apply, advance."""
    from django_rest_replication.application.applier import apply_event

    # last_event is the FK field; get last_event_id via getattr for mypy compat
    _raw_id = getattr(cursor, "last_event_id", None)
    after: uuid.UUID | None = uuid.UUID(str(_raw_id)) if _raw_id is not None else None

    while True:
        params: dict[str, Any] = {"limit": app_settings.BATCH_SIZE}
        if after is not None:
            params["after"] = str(after)
        try:
            resp = client.get(
                f"{node.base_url.rstrip('/')}/replication/events/",
                params=params,
                headers=_auth_headers(node),
                timeout=app_settings.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Incremental pull failed from %s: %s", node.name, exc)
            break

        events: list[dict[str, Any]] = resp.json()
        if not events:
            break

        for event_data in events:
            event_id_str: str = event_data.get("id", "")
            from django_rest_replication.models.change_event import ChangeEvent, EventType

            # Upsert the event record
            event, _ = ChangeEvent.objects.get_or_create(
                id=event_id_str,
                defaults={
                    "node_id": uuid.UUID(str(event_data.get("node_id"))),
                    "event_type": event_data.get("event_type", EventType.CREATE),
                    "model_label": event_data.get("model_label", ""),
                    "object_id": str(event_data.get("object_id", "")),
                    "tenant_id": event_data.get("tenant_id"),
                    "payload": event_data.get("payload"),
                    "old_payload": event_data.get("old_payload"),
                },
            )

            try:
                apply_event(event, cursor)
            except Exception:
                logger.exception("Failed to apply event %s", event.pk)
                continue

            after = event.pk

        if len(events) < app_settings.BATCH_SIZE:
            break


def run_pull(node: NodeConnection | None = None) -> None:
    """Entry point: iterate active PULL/BOTH nodes, run A or B as needed."""
    nodes: list[NodeConnection]
    if node is not None:
        nodes = [node]
    else:
        nodes = list(
            NodeConnection.objects.filter(
                is_active=True,
                direction__in=[Direction.PULL, Direction.BOTH],
            )
        )

    with httpx.Client() as client:
        for peer in nodes:
            cursor = get_or_create_cursor(peer)
            try:
                if needs_snapshot(cursor):
                    bootstrap_node(peer, cursor, client)
                else:
                    pull_incremental(peer, cursor, client)
            except Exception:
                logger.exception("pull failed for node %s", peer.name)
