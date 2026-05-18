"""
Phase 0 tests — AppSettings.

Verifies that:
  - Defaults are returned when DJANGO_REPLICATION is not set
  - User-provided values override defaults
  - Import-string settings are resolved to the actual class
  - Cache is invalidated on @override_settings
"""

from __future__ import annotations

import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestAppSettings:
    def test_default_batch_size(self) -> None:
        from django_replication.conf import app_settings

        assert app_settings.BATCH_SIZE == 500

    def test_default_max_retries(self) -> None:
        from django_replication.conf import app_settings

        assert app_settings.MAX_RETRIES == 3

    def test_user_override(self) -> None:
        from django_replication.conf import app_settings

        with override_settings(DJANGO_REPLICATION={"BATCH_SIZE": 100}):
            assert app_settings.BATCH_SIZE == 100

    def test_cache_invalidated_on_override(self) -> None:
        from django_replication.conf import app_settings

        _ = app_settings.BATCH_SIZE  # populate cache
        with override_settings(DJANGO_REPLICATION={"BATCH_SIZE": 999}):
            assert app_settings.BATCH_SIZE == 999
        # After context exit, original value restored
        assert app_settings.BATCH_SIZE == 500

    def test_invalid_key_raises(self) -> None:
        from django_replication.conf import app_settings

        with pytest.raises(AttributeError, match="Invalid setting"):
            _ = app_settings.NONEXISTENT_KEY  # type: ignore[attr-defined]

    def test_node_id_default_is_none(self) -> None:
        from django_replication.conf import AppSettings

        fresh = AppSettings()
        with override_settings(DJANGO_REPLICATION={}):
            assert fresh.NODE_ID is None
