# Changelog

All notable changes to `django-rest-replication` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 1: `ReplicatedModel` — abstract mixin with UUID v7 PK, `should_replicate()`, `get_tenant_id()`
- Phase 1: `ChangeEvent` — immutable event log with UUID v7 cursor-friendly PK
- Phase 1: `NodeConnection` — peer registry with direction (PUSH/PULL/BOTH) and auth token
- Phase 1: `ReplicationPolicy` — per-node/per-model field-level routing rules
- Phase 1: `EventDelivery` — delivery tracking (PENDING/DELIVERED/FAILED/SKIPPED) per event/node pair
- Phase 1: `SyncCursor` — per-node/per-tenant pull cursor backed by ChangeEvent FK
- Phase 1: Initial migration (`0001_initial`) for all core models
- Phase 1: `testapp.Product` updated to inherit from `ReplicatedModel`
- Phase 1: Unit tests for all Phase 1 models (`tests/test_models.py`)
- Phase 0: Project scaffold — `pyproject.toml`, `uv` toolchain, `ruff`, `mypy`, `pytest-django`
- Phase 0: `AppSettings` — typed, lazy, cache-invalidating settings accessor
- Phase 0: `DjangoRESTReplicationConfig` — `AppConfig` with signal registration hook
- Phase 0: GitHub Actions CI matrix (Python 3.12/3.13 × Django 5.2)
- Phase 0: `testapp` — minimal Django app skeleton for integration tests
