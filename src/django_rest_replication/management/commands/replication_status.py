"""Management command: print replication status table."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print the current replication status: cursors, pending deliveries, errors."

    def handle(self, *args: object, **options: object) -> None:
        from django_rest_replication.models import (
            DeliveryStatus,
            EventDelivery,
            NodeConnection,
        )
        from django_rest_replication.models.sync_cursor import SyncCursor

        self.stdout.write(self.style.HTTP_INFO("=== Replication Status ==="))
        self.stdout.write("")

        # ----- Node connections -----
        nodes = NodeConnection.objects.all().order_by("name")
        if not nodes.exists():
            self.stdout.write(self.style.WARNING("No NodeConnection records found."))
            return

        for node in nodes:
            status_line = (
                f"Node: {node.name} | direction={node.direction} "
                f"| active={node.is_active} | url={node.base_url}"
            )
            self.stdout.write(self.style.HTTP_INFO(status_line))

            # Cursors
            cursors = SyncCursor.objects.filter(node=node)
            if cursors.exists():
                for cursor in cursors:
                    tenant = cursor.tenant_id or "(default)"
                    bootstrapped = "yes" if cursor.snapshot_completed_at else "NO"
                    last = str(cursor.last_event_id) if cursor.last_event_id else "none"
                    self.stdout.write(
                        f"  Cursor [{tenant}]: bootstrapped={bootstrapped} "
                        f"last_event={last}"
                    )
            else:
                self.stdout.write("  Cursor: none")

            # Pending deliveries
            pending = EventDelivery.objects.filter(
                node=node, status=DeliveryStatus.PENDING
            ).count()
            failed = EventDelivery.objects.filter(
                node=node, status=DeliveryStatus.FAILED
            ).count()
            delivered = EventDelivery.objects.filter(
                node=node, status=DeliveryStatus.DELIVERED
            ).count()
            self.stdout.write(
                f"  Deliveries: pending={pending} failed={failed} delivered={delivered}"
            )
            self.stdout.write("")
