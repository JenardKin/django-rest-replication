"""DRF permissions for replication endpoints."""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from django_rest_replication.models.node_connection import NodeConnection


class IsAuthenticatedNode(BasePermission):
    """Allow access only to authenticated NodeConnection instances."""

    message = "Authentication as a valid node is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.user, NodeConnection)
