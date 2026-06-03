"""Management command: push events to peer nodes."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Push pending events to all active peer nodes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--node",
            type=str,
            default=None,
            help="Name or UUID of a specific node to push to.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from django_rest_replication.models.node_connection import NodeConnection
        from django_rest_replication.routing.pusher import run_push

        node_arg = options.get("node")
        node = None
        if node_arg:
            try:
                import uuid as _uuid

                node = NodeConnection.objects.get(node_id=_uuid.UUID(str(node_arg)))
            except (NodeConnection.DoesNotExist, ValueError):
                try:
                    node = NodeConnection.objects.get(name=str(node_arg))
                except NodeConnection.DoesNotExist:
                    self.stderr.write(self.style.ERROR(f"Node '{node_arg}' not found."))
                    return

        run_push(node)
        self.stdout.write(self.style.SUCCESS("Push complete."))
