"""Integration test fixtures."""

from __future__ import annotations

import uuid

import pytest

from django_rest_replication.models import Direction, NodeConnection


@pytest.fixture()
def hub_node() -> NodeConnection:
    """Simulate a hub NodeConnection (the remote peer)."""
    return NodeConnection.objects.create(
        name="hub",
        base_url="https://hub.example.com",
        node_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        direction=Direction.PULL,
        auth_token="hub-token",
        is_active=True,
    )


@pytest.fixture()
def spoke_node() -> NodeConnection:
    """Simulate a spoke NodeConnection (the remote peer)."""
    return NodeConnection.objects.create(
        name="spoke",
        base_url="https://spoke.example.com",
        node_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        direction=Direction.BOTH,
        auth_token="spoke-token",
        is_active=True,
    )
