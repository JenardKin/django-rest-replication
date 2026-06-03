"""Serialize model instances to JSON-safe dicts for ChangeEvent payloads."""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any

from django.db import models


def serialize_instance(instance: models.Model) -> dict[str, Any]:
    """
    Serialize all concrete, non-deferred fields to JSON-safe primitives.

    - UUID → str
    - Decimal → str
    - datetime → ISO 8601 str
    - date → ISO 8601 str
    - bytes → hex str
    - everything else natively JSON-safe passes through unchanged
    - unknown types → str() as a fallback
    """
    result: dict[str, Any] = {}
    for field in instance._meta.get_fields():
        # Only concrete, non-relation fields (or FK stored as _id column)
        if not isinstance(field, models.fields.Field):
            continue
        if field.is_relation and not field.many_to_one and not field.one_to_one:
            # Skip reverse relations and M2M
            continue
        if field.is_relation:
            # Store FK as attname (e.g. organization_id)
            attr = field.attname
        else:
            attr = field.attname

        value = getattr(instance, attr, None)
        result[attr] = _to_json_safe(value)
    return result


def _to_json_safe(value: Any) -> Any:
    """Convert a single Python value to a JSON-safe primitive."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, dict)):
        return value
    # Fallback for anything else
    return str(value)
