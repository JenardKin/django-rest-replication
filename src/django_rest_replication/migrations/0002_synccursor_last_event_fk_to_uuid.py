"""
Replace SyncCursor.last_event ForeignKey with a plain UUIDField.

Rationale:
- The cursor only needs the UUID value to use as an `after` parameter in pull
  requests; it never needs to JOIN to the ChangeEvent row.
- The FK constraint was checked on every cursor advance (write overhead).
- ON DELETE SET NULL forced a full SyncCursor scan whenever ChangeEvents were
  pruned, which is unacceptable at scale.
- Storing a bare UUID lets the event log be archived/pruned independently of
  cursor state.

The underlying column name does not change (still ``last_event_id``), so this
migration only drops the FK constraint and removes the DB-level reference.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_rest_replication", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="synccursor",
            name="last_event",
            field=models.UUIDField(
                blank=True,
                null=True,
                help_text="UUID v7 of the last successfully applied event from this node/tenant stream.",
            ),
        ),
        migrations.RenameField(
            model_name="synccursor",
            old_name="last_event",
            new_name="last_event_id",
        ),
    ]
