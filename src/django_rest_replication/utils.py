"""Utility helpers shared across the package."""

from __future__ import annotations

import uuid

import uuid_utils as _uuid_utils


def uuid7() -> uuid.UUID:
    """
    Generate a UUID v7 and return it as a stdlib ``uuid.UUID``.

    ``uuid_utils.UUID`` is not a subclass of ``uuid.UUID``, so Django's
    ``UUIDField.to_python()`` rejects it.  This wrapper converts before
    the value reaches the ORM, keeping UUID v7 semantics while staying
    Django-compatible.
    """
    return uuid.UUID(str(_uuid_utils.uuid7()))
