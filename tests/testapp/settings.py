"""
Minimal Django settings for running the test suite.

Two logical "sites" are represented via DJANGO_REPLICATION settings:
  - hub:   the central aggregating node
  - spoke: an on-premise / edge node

Integration tests swap DJANGO_REPLICATION["NODE_ID"] via @override_settings
to simulate each side of the connection.
"""

from __future__ import annotations

SECRET_KEY = "django-replication-test-secret-not-for-production"

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_rest_replication",
    "tests.testapp",
]

DEFAULT_AUTO_FIELD = "django.db.models.UUIDField"

ROOT_URLCONF = "tests.testapp.urls"

USE_TZ = True

# ---------------------------------------------------------------------------
# django-rest-replication — default test configuration (hub node)
# ---------------------------------------------------------------------------
DJANGO_REPLICATION = {
    "NODE_ID": "00000000-0000-0000-0000-000000000001",  # hub
    "BACKEND": "django_rest_replication.backend.ReplicationBackend",
    "TASK_BACKEND": "django_rest_replication.tasks.sync.SynchronousTaskBackend",
    "TENANT_MODEL": None,
    "TENANT_FIELD": "tenant_id",
    "BATCH_SIZE": 500,
    "MAX_RETRIES": 3,
    "RETRY_BACKOFF": 60,
    "PRUNE_AFTER_DAYS": 30,
    "REQUEST_TIMEOUT": 30,
}

# ---------------------------------------------------------------------------
# DRF defaults
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "django_rest_replication.api.auth.NodeTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}
