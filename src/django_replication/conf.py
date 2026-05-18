"""
AppSettings — single source of truth for all DJANGO_REPLICATION settings.

Usage in host app's settings.py:

    DJANGO_REPLICATION = {
        "NODE_ID": "your-node-uuid-here",
        "BACKEND": "django_replication.backend.ReplicationBackend",
        "TASK_BACKEND": "django_replication.tasks.sync.SynchronousTaskBackend",
        "TENANT_MODEL": None,          # e.g. "myapp.Organization"
        "TENANT_FIELD": "tenant_id",
        "BATCH_SIZE": 500,
        "MAX_RETRIES": 3,
        "RETRY_BACKOFF": 60,
        "PRUNE_AFTER_DAYS": 30,
        "REQUEST_TIMEOUT": 30,
    }
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.test.signals import setting_changed
from django.utils.module_loading import import_string

# Sentinel — used to distinguish "not set" from None
_UNSET: Any = object()

DEFAULTS: dict[str, Any] = {
    "NODE_ID": None,
    "BACKEND": "django_replication.backend.ReplicationBackend",
    "TASK_BACKEND": "django_replication.tasks.sync.SynchronousTaskBackend",
    "TENANT_MODEL": None,
    "TENANT_FIELD": "tenant_id",
    "BATCH_SIZE": 500,
    "MAX_RETRIES": 3,
    "RETRY_BACKOFF": 60,
    "PRUNE_AFTER_DAYS": 30,
    "REQUEST_TIMEOUT": 30,
}

# Settings whose string values are import paths that should be lazily imported
IMPORT_STRINGS: frozenset[str] = frozenset({"BACKEND", "TASK_BACKEND"})


class AppSettings:
    """
    Lazy settings accessor.  Reads from DJANGO_REPLICATION dict, falls back
    to DEFAULTS, and performs lazy imports for class-path settings.

    Cached on first access; cache is invalidated when settings change
    (important for testing with @override_settings).
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        setting_changed.connect(self._handle_setting_changed)

    def _handle_setting_changed(self, *, setting: str, **kwargs: Any) -> None:
        if setting == "DJANGO_REPLICATION":
            self._cache.clear()

    @property
    def _user_settings(self) -> dict[str, Any]:
        return getattr(settings, "DJANGO_REPLICATION", {})

    def __getattr__(self, name: str) -> Any:
        if name not in DEFAULTS:
            raise AttributeError(f"Invalid setting: {name!r}")

        if name in self._cache:
            return self._cache[name]

        value = self._user_settings.get(name, DEFAULTS[name])

        if name in IMPORT_STRINGS and isinstance(value, str):
            value = import_string(value)

        self._cache[name] = value
        return value


app_settings = AppSettings()
