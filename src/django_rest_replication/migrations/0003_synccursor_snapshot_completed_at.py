"""
Add SyncCursor.snapshot_completed_at.

Null  → snapshot has never run; pull engine must bootstrap before streaming.
Set   → snapshot complete; pull engine goes straight to incremental streaming.

This single field encodes all bootstrap state needed by the Phase 6 pull loop
without requiring a separate model or status enum.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_rest_replication", "0002_synccursor_last_event_fk_to_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="synccursor",
            name="snapshot_completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "Set when the initial bulk snapshot has finished for this cursor. "
                    "Null means the snapshot has never run — the pull engine will run "
                    "the bootstrap phase before switching to incremental streaming."
                ),
            ),
        ),
    ]
