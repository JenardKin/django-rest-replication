# django-rest-replication

[![CI](https://github.com/JenardKin/django-rest-replication/actions/workflows/ci.yml/badge.svg)](https://github.com/JenardKin/django-rest-replication/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/django-rest-replication)](https://pypi.org/project/django-rest-replication/)
[![Python](https://img.shields.io/pypi/pyversions/django-rest-replication)](https://pypi.org/project/django-rest-replication/)
[![Django](https://img.shields.io/badge/django-5.2%20LTS-green)](https://docs.djangoproject.com/en/5.2/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Application-level database replication for Django over REST.**

Replicate Django model changes across multiple Django applications without
requiring database-level access, message brokers, or proprietary cloud services.
Works with any database Django supports.

---

## Why?

Most database replication solutions require direct database access (pg_logical,
Debezium), are cloud-only, or require heavyweight infrastructure.

`django-rest-replication` works at the **application layer**: it uses Django
signals to capture changes, stores them as structured log entries, and
exchanges them between nodes via a standard REST API.

**Key features:**

- **Topology-agnostic** — hub-and-spoke, peer-to-peer, or hybrid; configure
  via the Django admin, not code
- **Multi-tenant** — per-tenant event streams and cursors; tenants are
  isolated by default
- **Per-table / per-field policies** — control exactly what replicates where,
  with field-level overrides per node
- **Cursor-based sync** — O(new events) performance regardless of total log
  size; no offset pagination degradation
- **Sync or async** — toggle between synchronous (cron-friendly) and
  Celery / django-q delivery with one setting
- **No extra infrastructure** — only requires a database and HTTP connectivity
  between nodes

---

## Requirements

- Python 3.12+
- Django 5.2 LTS
- Django REST Framework 3.15+

---

## Quick Start

> Full documentation is in progress. This section will be completed in Phase 10.

```python
# 1. Install
pip install django-rest-replication

# 2. Add to INSTALLED_APPS
INSTALLED_APPS = [
    ...
    "django_rest_replication",
]

# 3. Configure
DJANGO_REPLICATION = {
    "NODE_ID": "your-node-uuid",
    "BACKEND": "django_rest_replication.backend.ReplicationBackend",
}

# 4. Add the mixin to models you want to replicate
from django_rest_replication.models.mixins import ReplicatedModel

class Product(ReplicatedModel):
    name = models.CharField(max_length=255)
    ...

# 5. Run migrations and the setup wizard
python manage.py migrate
python manage.py replication_init
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│  CAPTURE  — Django signals → ChangeEvent│
└───────────────────┬─────────────────────┘
                    │ UUID v7 — time-ordered, cursor-friendly
┌───────────────────▼─────────────────────┐
│  ROUTING  — Policy → EventDelivery      │
└───────────────────┬─────────────────────┘
                    │ per NodeConnection
┌───────────────────▼─────────────────────┐
│  TRANSPORT — httpx, cursor-based REST   │
└───────────────────┬─────────────────────┘
                    │ incoming events
┌───────────────────▼─────────────────────┐
│  APPLICATION — apply → ack → advance    │
└─────────────────────────────────────────┘
              ↕ at every stage
┌─────────────────────────────────────────┐
│  BACKEND — your business logic hooks    │
└─────────────────────────────────────────┘
```

---

## Status

This project is currently in active development. See the
[GitHub Issues](https://github.com/JenardKin/django-rest-replication/issues)
for the implementation roadmap.

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Scaffold — tooling, CI, testapp | ✅ Done |
| 1 | Core models | ✅ Done |
| 2 | Backend adapter | 🔲 Next |
| 3 | Change capture | 🔲 Planned |
| 4 | Task backends (sync/async) | 🔲 Planned |
| 5 | REST API | 🔲 Planned |
| 6 | Sync engine | 🔲 Planned |
| 7 | Event application | 🔲 Planned |
| 8 | Integration & topology tests | 🔲 Planned |
| 9 | Developer experience & admin | 🔲 Planned |
| 10 | Docs & PyPI publish | 🔲 Planned |
| 11 | NoSQL support (MongoDB, Elasticsearch, Redis) | 🔲 Future |

---

## License

MIT — see [LICENSE](LICENSE).
