# Changelog

All notable changes to `django-rest-replication` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 0: Project scaffold — `pyproject.toml`, `uv` toolchain, `ruff`, `mypy`, `pytest-django`
- Phase 0: `AppSettings` — typed, lazy, cache-invalidating settings accessor
- Phase 0: `DjangoReplicationConfig` — `AppConfig` with signal registration hook
- Phase 0: GitHub Actions CI matrix (Python 3.12/3.13 × Django 5.2)
- Phase 0: `testapp` — minimal Django app skeleton for integration tests
