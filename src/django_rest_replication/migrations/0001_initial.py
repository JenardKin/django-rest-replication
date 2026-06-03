"""Initial migration — Phase 1 core models."""

import django.db.models.deletion
from django.db import migrations, models

import django_rest_replication.utils


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []

    operations = [
        # ------------------------------------------------------------------ #
        # NodeConnection — no FKs, must come first                           #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="NodeConnection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=django_rest_replication.utils.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable label for this peer, e.g. 'EU warehouse'.",
                        max_length=255,
                    ),
                ),
                (
                    "base_url",
                    models.CharField(
                        help_text="Root URL of the peer, e.g. 'https://peer.example.com'.",
                        max_length=2048,
                    ),
                ),
                (
                    "node_id",
                    models.UUIDField(
                        help_text="The NODE_ID declared by the peer in its DJANGO_REPLICATION settings.",
                        unique=True,
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        choices=[
                            ("PUSH", "Push (send to peer)"),
                            ("PULL", "Pull (receive from peer)"),
                            ("BOTH", "Both (push and pull)"),
                        ],
                        default="BOTH",
                        max_length=4,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "auth_token",
                    models.CharField(
                        help_text="Shared bearer token used to authenticate requests to/from this peer.",
                        max_length=512,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
                "app_label": "django_rest_replication",
            },
        ),
        # ------------------------------------------------------------------ #
        # ChangeEvent — no FKs to other replication models                   #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ChangeEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=django_rest_replication.utils.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "node_id",
                    models.UUIDField(
                        db_index=True, help_text="NODE_ID of the node that produced this event."
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[("CREATE", "Create"), ("UPDATE", "Update"), ("DELETE", "Delete")],
                        db_index=True,
                        max_length=6,
                    ),
                ),
                (
                    "model_label",
                    models.CharField(
                        db_index=True,
                        help_text='Django app_label.ModelName, e.g. "shop.Product".',
                        max_length=255,
                    ),
                ),
                (
                    "object_id",
                    models.CharField(
                        db_index=True,
                        help_text="str(instance.pk) of the affected object.",
                        max_length=255,
                    ),
                ),
                (
                    "tenant_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Tenant identifier returned by get_tenant_id(); null for single-tenant.",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        blank=True,
                        help_text="Full serialized field values for CREATE and UPDATE events.",
                        null=True,
                    ),
                ),
                (
                    "old_payload",
                    models.JSONField(
                        blank=True,
                        help_text="Previous field values captured via pre_save, for UPDATE events only.",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ["id"],
                "app_label": "django_rest_replication",
                "indexes": [
                    models.Index(fields=["node_id", "id"], name="ce_node_cursor_idx"),
                    models.Index(fields=["tenant_id", "id"], name="ce_tenant_cursor_idx"),
                ],
            },
        ),
        # ------------------------------------------------------------------ #
        # ReplicationPolicy — FK to NodeConnection                           #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="ReplicationPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=django_rest_replication.utils.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policies",
                        to="django_rest_replication.nodeconnection",
                    ),
                ),
                (
                    "model_label",
                    models.CharField(
                        help_text='Django app_label.ModelName, e.g. "shop.Product". Use "*" to match all models on this node.',
                        max_length=255,
                    ),
                ),
                (
                    "included_fields",
                    models.JSONField(
                        blank=True,
                        default=None,
                        help_text="Whitelist of field names to include. Null means include all fields.",
                        null=True,
                    ),
                ),
                (
                    "excluded_fields",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Blacklist of field names to exclude (applied after included_fields).",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "replication policies",
                "ordering": ["node", "model_label"],
                "app_label": "django_rest_replication",
                "unique_together": {("node", "model_label")},
            },
        ),
        # ------------------------------------------------------------------ #
        # EventDelivery — FKs to ChangeEvent and NodeConnection              #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="EventDelivery",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=django_rest_replication.utils.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="django_rest_replication.changeevent",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="django_rest_replication.nodeconnection",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("DELIVERED", "Delivered"),
                            ("FAILED", "Failed"),
                            ("SKIPPED", "Skipped"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=9,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["created_at"],
                "app_label": "django_rest_replication",
                "unique_together": {("event", "node")},
                "indexes": [
                    models.Index(fields=["status", "created_at"], name="ed_status_created_idx"),
                ],
            },
        ),
        # ------------------------------------------------------------------ #
        # SyncCursor — FKs to NodeConnection and ChangeEvent                 #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name="SyncCursor",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=django_rest_replication.utils.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cursors",
                        to="django_rest_replication.nodeconnection",
                    ),
                ),
                (
                    "tenant_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Tenant this cursor tracks. Empty string for single-tenant setups.",
                        max_length=255,
                    ),
                ),
                (
                    "last_event",
                    models.ForeignKey(
                        blank=True,
                        help_text="Last successfully applied event from this node/tenant stream.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="django_rest_replication.changeevent",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "app_label": "django_rest_replication",
                "unique_together": {("node", "tenant_id")},
            },
        ),
    ]
