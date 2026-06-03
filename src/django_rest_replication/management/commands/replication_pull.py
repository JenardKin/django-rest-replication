"""Management command: pull events from peer nodes."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Pull replication events from all active peer nodes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--node",
            type=str,
            default=None,
            help="Name or UUID of a specific node to pull from.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from django_rest_replication.routing.puller import run_pull
        from django_rest_replication.models.node_connection import NodeConnection

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

        run_pull(node)
        self.stdout.write(self.style.SUCCESS("Pull complete."))
