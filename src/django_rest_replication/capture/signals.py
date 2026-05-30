"""
Change capture signal handlers.

These are the only entry points for recording model changes. Each handler
is intentionally thin — guard checks, then delegate to the capture pipeline.

Registered in DjangoRESTReplicationConfig.ready() to avoid AppRegistryNotReady.
"""

# Handlers are implemented in Phase 3.
# This module exists so apps.py can import it without error during Phase 0.
