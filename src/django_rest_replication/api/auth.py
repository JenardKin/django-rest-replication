"""DRF authentication: NodeTokenAuthentication."""

from __future__ import annotations

from typing import Any

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from django_rest_replication.models.node_connection import NodeConnection


class NodeTokenAuthentication(BaseAuthentication):
    """
    Authenticate a peer node by its auth token.

    Reads ``Authorization: Token <token>`` header, looks up the matching
    active NodeConnection, and returns it as the request user.
    """

    keyword = "Token"

    def authenticate(self, request: Request) -> tuple[NodeConnection, None] | None:
        auth_header: str = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(f"{self.keyword} "):
            return None

        token = auth_header[len(self.keyword) + 1:].strip()
        if not token:
            return None

        try:
            node = NodeConnection.objects.get(auth_token=token, is_active=True)
        except NodeConnection.DoesNotExist:
            raise AuthenticationFailed("Invalid or inactive node token.")

        return node, None

    def authenticate_header(self, request: Any) -> str:
        return self.keyword
