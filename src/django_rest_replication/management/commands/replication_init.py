"""Management command: validate setup and print instructions."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validate the replication configuration and print setup instructions."

    def handle(self, *args: object, **options: object) -> None:
        from django_rest_replication.conf import app_settings

        self.stdout.write(self.style.HTTP_INFO("=== Django REST Replication Setup ==="))
        self.stdout.write("")

        # Validate NODE_ID
        node_id = app_settings.NODE_ID
        if node_id is None:
            self.stderr.write(
                self.style.ERROR(
                    "ERROR: NODE_ID is not set in DJANGO_REPLICATION settings.\n"
                    "Add the following to your settings.py:\n\n"
                    "    DJANGO_REPLICATION = {\n"
                    '        "NODE_ID": "<unique-uuid-for-this-node>",\n'
                    "        ...\n"
                    "    }"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"NODE_ID: {node_id}"))

        # Show backend
        self.stdout.write(f"BACKEND: {app_settings.BACKEND}")
        self.stdout.write(f"TASK_BACKEND: {app_settings.TASK_BACKEND}")
        self.stdout.write(f"BATCH_SIZE: {app_settings.BATCH_SIZE}")
        self.stdout.write(f"MAX_RETRIES: {app_settings.MAX_RETRIES}")
        self.stdout.write("")

        # Show registered ReplicatedModel subclasses
        from django_rest_replication.api.snapshot import get_replicated_models

        models = get_replicated_models()
        if models:
            self.stdout.write(self.style.HTTP_INFO("Registered ReplicatedModel subclasses:"))
            for m in models:
                label = f"{m._meta.app_label}.{m._meta.object_name}"
                self.stdout.write(f"  - {label}")
        else:
            self.stdout.write(self.style.WARNING("No ReplicatedModel subclasses registered."))

        self.stdout.write("")
        if node_id is not None:
            self.stdout.write(self.style.SUCCESS("Configuration looks good!"))
