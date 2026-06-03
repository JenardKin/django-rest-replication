# Implementation Plan — django-rest-replication

Application-level database replication for Django over REST.
No message brokers, no direct DB access, no cloud lock-in.

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  CAPTURE  — Django signals → ChangeEvent│
└───────────────────┬─────────────────────┘
                    │ UUID v7 (time-ordered, cursor-friendly)
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
│  BACKEND — user business logic hooks    │
└─────────────────────────────────────────┘
```

---

## Phase Status

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 0 | Scaffold | ✅ Done | tooling, CI, AppConfig, AppSettings, testapp |
| 1 | Core Models | ✅ Done | DB schema for the replication system |
| 2 | Backend Adapter | 🔲 Next | user hook interface |
| 3 | Change Capture | 🔲 Planned | signal handlers → ChangeEvent |
| 4 | Task Backends | 🔲 Planned | sync + Celery + django-q |
| 5 | REST API | 🔲 Planned | push/pull endpoints |
| 6 | Sync Engine | 🔲 Planned | cursor-based pull loop |
| 7 | Event Application | 🔲 Planned | apply incoming events |
| 8 | Integration Tests | 🔲 Planned | topology scenarios |
| 9 | DX & Admin | 🔲 Planned | management commands, Django admin |
| 10 | Docs & PyPI | 🔲 Planned | README polish, publish 0.1.0 |
| 11 | NoSQL Support | 🔲 Future | MongoDB, Elasticsearch, Redis targets |

---

## Phase 0 — Scaffold ✅

**Goal:** working skeleton that CI can run against.

**Delivered:**
- `pyproject.toml` — `hatchling` build, `uv` toolchain, `ruff`, `mypy --strict`, `pytest-django`
- `AppSettings` (`conf.py`) — typed, lazy, cache-invalidating settings accessor keyed on `DJANGO_REPLICATION`
- `DjangoRESTReplicationConfig` (`apps.py`) — AppConfig with signal registration hook in `ready()`
- GitHub Actions CI matrix — Python 3.12/3.13 × Django 5.2
- `testapp` — `Organization`, `Product`, `Tag`, `ProductTag` models (stubs for Phase 1 mixins)
- `capture/signals.py` — stub module (real handlers in Phase 3)

---

## Phase 1 — Core Models 🔲

**Goal:** create the DB schema that the entire system writes to and reads from.

**Models to create** (`src/django_rest_replication/models/`):

### `ReplicatedModel` (mixin)
Abstract base class users inherit from.
```python
class ReplicatedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid_utils.uuid7, editable=False)

    def should_replicate(self) -> bool: ...       # override to exclude rows
    def get_tenant_id(self) -> str | None: ...    # override for multi-tenancy

    class Meta:
        abstract = True
```

### `ChangeEvent`
Immutable log of every create/update/delete captured from signals.
```
id          UUID v7 (PK, time-ordered)
node_id     UUID — which node produced it
event_type  Enum[CREATE, UPDATE, DELETE]
model_label str — "app.ModelName"
object_id   str — str(pk)
tenant_id   str | null
payload     JSON — full serialized field values (CREATE/UPDATE)
old_payload JSON | null — previous values for UPDATE (field-level diffing)
created_at  DateTimeField (auto)
```

### `NodeConnection`
Peer nodes this node knows about.
```
id          UUID (PK)
name        str — human label
base_url    str — "https://peer.example.com"
node_id     UUID — remote node's NODE_ID
direction   Enum[PUSH, PULL, BOTH]
is_active   bool
auth_token  str (encrypted at rest via secret rotation)
```

### `ReplicationPolicy`
Controls which models replicate to which nodes.
```
id              UUID (PK)
node            FK → NodeConnection
model_label     str — "app.ModelName" (or "*" for all)
included_fields JSON | null — whitelist; null = all
excluded_fields JSON — blacklist (applied after include)
is_active       bool
```

### `EventDelivery`
Tracks delivery status of each ChangeEvent to each NodeConnection.
```
id          UUID (PK)
event       FK → ChangeEvent
node        FK → NodeConnection
status      Enum[PENDING, DELIVERED, FAILED, SKIPPED]
attempts    int
last_error  str | null
delivered_at DateTimeField | null
```

### `SyncCursor`
Per-node (per-tenant) cursor for pull-based sync.
```
id                    UUID (PK)
node                  FK → NodeConnection
tenant_id             str | null
last_event_id         UUID | null — UUID v7 of last applied event (plain field, not FK)
snapshot_completed_at DateTimeField | null — null = snapshot never run; set = streaming mode
updated_at            DateTimeField (auto)
```

**Deliverables:**
- [x] `src/django_rest_replication/models/` — one file per model + `__init__.py` re-export
- [x] Initial migration (`0001_initial`)
- [x] `ReplicatedModel` mixin wired into `testapp` models
- [x] Unit tests for model field constraints and `ReplicatedModel` defaults

---

## Phase 2 — Backend Adapter 🔲

**Goal:** a stable hook interface users override to inject business logic.

**Interface** (`src/django_rest_replication/backend/base.py`):
```python
class BaseReplicationBackend:
    def on_event_captured(self, event: ChangeEvent) -> None: ...
    def on_before_apply(self, event: ChangeEvent) -> bool: ...   # False = skip
    def on_after_apply(self, event: ChangeEvent) -> None: ...
    def on_delivery_failed(self, delivery: EventDelivery) -> None: ...
    def resolve_conflict(self, local: Model, event: ChangeEvent) -> ConflictResolution: ...
```

**Default implementation** (`backend/default.py`): no-ops + last-write-wins conflict.

**Deliverables:**
- [ ] `BaseReplicationBackend` ABC
- [ ] `ReplicationBackend` (default, ships with the package)
- [ ] `app_settings.BACKEND` lazy-imports and validates the class
- [ ] Unit tests with a custom backend subclass

---

## Phase 3 — Change Capture 🔲

**Goal:** record every `CREATE`, `UPDATE`, `DELETE` on `ReplicatedModel` subclasses.

**Approach:**
- Connect `post_save` and `post_delete` to the handler in `capture/signals.py`
- Guard: skip if the model is not a `ReplicatedModel` subclass
- Guard: skip if `instance.should_replicate()` returns `False`
- Guard: skip if the event originated from this node (loop prevention via thread-local flag)
- Serialize full payload via DRF serializer or `django.forms.models.model_to_dict`
- For UPDATE: capture `old_payload` via `pre_save` stash
- For M2M: connect `m2m_changed` on explicit through-table models only
- Wrap event creation in `transaction.on_commit` so the event is only written once the DB transaction commits

**Deliverables:**
- [ ] `capture/signals.py` — real handlers
- [ ] `capture/serializer.py` — field value → JSON
- [ ] Thread-local loop-prevention guard
- [ ] Unit tests for create/update/delete/m2m capture
- [ ] Tests that excluded/skipped models produce no events

---

## Phase 4 — Task Backends 🔲

**Goal:** decouple event delivery from the request/response cycle.

**Interface** (`tasks/base.py`):
```python
class BaseTaskBackend:
    def enqueue_delivery(self, delivery_id: UUID) -> None: ...
    def enqueue_pull(self, node_id: UUID, tenant_id: str | None) -> None: ...
```

**Implementations:**
- `tasks/sync.py` — `SynchronousTaskBackend`: calls the transport inline (default, good for tests and small deploys)
- `tasks/celery.py` — `CeleryTaskBackend`: sends to a Celery queue
- `tasks/django_q.py` — `DjangoQTaskBackend`: sends to django-q2

**Deliverables:**
- [ ] `BaseTaskBackend` ABC
- [ ] `SynchronousTaskBackend`
- [ ] `CeleryTaskBackend` (optional extra)
- [ ] `DjangoQTaskBackend` (optional extra)
- [ ] `app_settings.TASK_BACKEND` selects implementation
- [ ] Unit tests for each backend with a mock transport

---

## Phase 5 — REST API 🔲

**Goal:** expose endpoints for pushing and pulling events between nodes.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/replication/events/` | Receive pushed events from a peer |
| `GET`  | `/replication/events/?after=<uuid>&limit=<n>` | Pull events since cursor |
| `GET`  | `/replication/nodes/` | List known peers (admin use) |
| `POST` | `/replication/ack/` | Acknowledge delivered events |
| `GET`  | `/replication/snapshot/manifest/` | Topologically ordered model list + watermark |
| `GET`  | `/replication/snapshot/?model=<label>&after=<uuid>&limit=<n>` | Paginated row export for bootstrap |

**Auth:** shared token in `Authorization: Token <token>` header, validated against `NodeConnection.auth_token`.

**Snapshot manifest response:**
```json
{
  "watermark": "<current max ChangeEvent id — captured before any rows are read>",
  "models": ["shop.Category", "shop.Product", "shop.ProductTag"]
}
```
Models are ordered by Django FK dependency (parents before children) so the
receiver can apply rows without FK constraint errors.  The `watermark` is
captured server-side in a single query *before* any rows are read so that
changes landing during the snapshot are guaranteed to appear in the subsequent
event stream.

**Snapshot page response:**
```json
{
  "model": "shop.Product",
  "next_cursor": "<last pk in this batch or null>",
  "has_more": true,
  "rows": [
    {"id": "...", "name": "...", ...}
  ]
}
```
`rows` use the identical payload format as `ChangeEvent.payload` so the Phase 7
applier handles snapshot rows and streamed events through the same code path.

**Deliverables:**
- [ ] `api/serializers.py` — `ChangeEventSerializer`, `EventDeliverySerializer`
- [ ] `api/views.py` — `EventPushView`, `EventPullView`, `AckView`, `SnapshotManifestView`, `SnapshotView`
- [ ] `api/urls.py`
- [ ] `api/authentication.py` — node token auth
- [ ] `api/permissions.py` — `IsAuthenticatedNode`
- [ ] `api/snapshot.py` — model topological sort, keyset-paginated queryset builder
- [ ] URL include instructions in README
- [ ] Unit tests for each endpoint (happy path + auth failure + invalid payload)
- [ ] Unit tests for topological sort with FK dependency cycles (should raise clearly)

---

## Phase 6 — Sync Engine 🔲

**Goal:** pull events from peers and push pending deliveries.

**Pull loop** (`routing/puller.py`) — two-phase per cursor:

*Phase A — Bootstrap snapshot (runs once per cursor when `snapshot_completed_at` is null):*
1. `GET /replication/snapshot/manifest/` → receive ordered model list + `watermark`
2. For each model in order, paginate `GET /replication/snapshot/?model=<label>&after=<cursor>&limit=BATCH_SIZE` until `has_more=false`
3. Apply each page of rows as upserts via the Phase 7 applier (same code path as events)
4. On completion, set `cursor.last_event_id = watermark` and `cursor.snapshot_completed_at = now()`
5. If interrupted, resume from the last successful page — keyset pagination makes this safe

*Phase B — Incremental streaming (runs on every pull when `snapshot_completed_at` is set):*
1. Load active `NodeConnection` records with `direction IN [PULL, BOTH]`
2. For each node, load `SyncCursor` (per tenant if multi-tenant)
3. `GET /replication/events/?after=<last_event_id>&limit=BATCH_SIZE`
4. Pass events to Phase 7 application layer
5. Advance `last_event_id` on success

The watermark recorded at the start of the snapshot guarantees that any writes
landing *during* the snapshot export appear in the event stream when Phase B
begins.  Because the applier uses `update_or_create`, duplicate rows (snapshot
row + subsequent event) are handled safely with no special-casing.

**Push loop** (`routing/pusher.py`):
1. Load `EventDelivery` records with `status=PENDING`
2. Group by node, `POST /replication/events/` in batches
3. Update delivery status; retry with backoff up to `MAX_RETRIES`

**Deliverables:**
- [ ] `routing/puller.py` — two-phase pull logic
- [ ] `routing/pusher.py`
- [ ] `routing/cursor.py` — cursor read/advance/snapshot helpers
- [ ] Management command `replication_pull` (wraps puller)
- [ ] Management command `replication_push` (wraps pusher)
- [ ] Unit tests with `pytest-httpx` mocking the peer HTTP calls
- [ ] Integration test: node with pre-existing data bootstraps correctly and then streams

---

## Phase 7 — Event Application 🔲

**Goal:** apply incoming events to the local database correctly.

**Apply pipeline** (`application/applier.py`):
1. Deserialize `ChangeEvent.payload` into model field values
2. Call `backend.on_before_apply(event)` — skip if False
3. Look up existing object by `object_id`
4. **Conflict detection:** if local `updated_at > event.created_at`, call `backend.resolve_conflict()`
5. Apply: `Model.objects.update_or_create()` for CREATE/UPDATE, `.delete()` for DELETE
6. Set thread-local loop-prevention flag during apply so signals don't re-capture
7. Call `backend.on_after_apply(event)`
8. Write `EventDelivery` as DELIVERED and advance cursor

**Conflict strategies (built-in):**
- `LAST_WRITE_WINS` (default)
- `SKIP_IF_NEWER` — local wins
- `RAISE` — surface to `backend.resolve_conflict()`

**Deliverables:**
- [ ] `application/applier.py`
- [ ] `application/conflicts.py`
- [ ] Unit tests: create/update/delete application
- [ ] Unit tests: conflict resolution paths

---

## Phase 8 — Integration & Topology Tests 🔲

**Goal:** prove the full pipeline works end-to-end in realistic topologies.

**Scenarios:**
- Hub-and-spoke: 1 hub, 2 spokes; changes on any node replicate through hub
- Peer-to-peer: 2 nodes, mutual replication, no duplicate events
- Multi-tenant: events for tenant A never appear in tenant B's cursor
- Large batch: 10,000 events, cursor paging, correct ordering
- Failure recovery: delivery fails twice, succeeds on retry; cursor does not advance on failure

**Test infrastructure:**
- `conftest.py` fixtures for in-process "multi-node" simulation using `pytest-httpx`
- Separate pytest markers: `hub_spoke`, `p2p`, `integration`

**Deliverables:**
- [ ] `tests/integration/` directory
- [ ] Topology fixtures in `conftest.py`
- [ ] All scenarios passing under `pytest -m integration`

---

## Phase 9 — DX & Admin 🔲

**Goal:** make the library easy to operate and debug.

**Management commands:**
- `replication_init` — interactive setup wizard (node UUID, first peer URL)
- `replication_status` — print cursor positions, pending deliveries, error counts
- `replication_pull` — one-shot pull
- `replication_push` — one-shot push

**Django Admin:**
- `NodeConnection` — CRUD, inline `ReplicationPolicy`
- `ChangeEvent` — read-only list with filters by model/node/date
- `EventDelivery` — read-only list with retry action
- `SyncCursor` — read-only, with manual reset action

**Deliverables:**
- [ ] `management/commands/` — 4 commands above
- [ ] `admin.py` — registrations above
- [ ] Manual smoke test documented in CONTRIBUTING.md

---

## Phase 10 — Docs & PyPI Publish 🔲

**Goal:** ship a usable 0.1.0 release.

**Deliverables:**
- [ ] README Quick Start completed
- [ ] Architecture section verified against final implementation
- [ ] `CHANGELOG.md` — all phases summarized under `[0.1.0]`
- [ ] `pyproject.toml` classifiers reviewed
- [ ] `uv run pytest` + `ruff check` + `mypy` all green
- [ ] `git tag v0.1.0` + `uv build` + `uv publish` to PyPI
- [ ] GitHub Release with changelog excerpt

---

## Phase 11 — NoSQL Support 🔲

**Goal:** allow replicated events to be applied to NoSQL stores, making the
library useful for teams whose read models or search indices live outside SQL.

**Scope:** the replication system's own tables (`ChangeEvent`, `NodeConnection`,
etc.) stay on SQL. NoSQL applies to the *application* layer — where the
`ReplicationBackend.on_before_apply` / `on_after_apply` hooks fire.

**Approach options (to be decided at phase start):**

| Option | Description | Tradeoff |
|--------|-------------|----------|
| Backend-only | Users write a custom `Backend` subclass that writes to MongoDB/ES | Zero lib complexity; full flexibility |
| Built-in adapters | Ship `MongoBackend`, `ElasticsearchBackend` as optional extras | More surface area; easier for users |
| Hybrid | Provide base classes + helper utilities; users compose | Middle ground |

**Candidate targets:**

| Store | Package | Use case |
|-------|---------|---------|
| MongoDB | `motor` (async) / `pymongo` | Document store for replicated models |
| Elasticsearch | `elasticsearch-py` | Search index kept in sync via replication |
| Redis | `redis-py` | Cache invalidation / pub-sub on replication events |
| DynamoDB | `boto3` | AWS NoSQL target |

**Deliverables:**
- [ ] Decision: backend-only, built-in adapters, or hybrid
- [ ] At least one reference adapter (likely MongoDB) with integration tests
- [ ] Optional extras in `pyproject.toml` per NoSQL target
- [ ] CI job for at least one NoSQL target
- [ ] Documentation: "Writing a NoSQL backend adapter"

---

## Database Targets

### SQL databases (Phases 0–10)

The replication system's own tables (`ChangeEvent`, `NodeConnection`, etc.) require
ACID transactions and relational integrity — SQL is the right tool here.

| Database | Tier | Driver | CI |
|----------|------|--------|----|
| PostgreSQL 14+ | **Primary** | built-in `psycopg` | ✅ Every PR |
| MSSQL / SQL Server 2019+ | **Secondary** | `mssql-django` | 🔲 Planned |
| MySQL 8.0+ / MariaDB 10.5+ | **Supported** | built-in `mysqlclient` | 🔲 Planned |
| Oracle 19c+ | **Supported** | built-in `cx_Oracle` | 🔲 Planned |
| CockroachDB | **Supported** | `django-cockroachdb` | 🔲 Planned |
| SQLite | **Dev fallback only** | built-in | ✅ Every PR (no `DATABASE_URL`) |

**To run tests locally:**
```bash
# PostgreSQL (primary)
DATABASE_URL=postgres://user:pass@localhost:5432/test_db uv run pytest

# MSSQL (requires mssql-django)
pip install "django-rest-replication[mssql]"
DATABASE_URL="mssql://user:pass@localhost:1433/test_db?driver=ODBC+Driver+18+for+SQL+Server" uv run pytest

# MySQL
DATABASE_URL=mysql://user:pass@localhost:3306/test_db uv run pytest
```

### NoSQL databases (Phase 11)

NoSQL support is a future phase. See [Phase 11](#phase-11--nosql-support-) below.
The replication system's own tables will always remain on a SQL backend;
NoSQL applies only to the *application* layer where replicated data is written.

### Database compatibility notes

- **UUID v7 PKs** — `uuid` (PostgreSQL), `uniqueidentifier` (MSSQL), `char(32)` (MySQL/Oracle). All handled transparently by Django's `UUIDField`.
- **`JSONField`** — `jsonb` (PostgreSQL), `nvarchar(max)` (MSSQL), `json` (MySQL 5.7+). No JSON-operator queries (`->`, `->>`) are used — plain reads/writes only, keeping code cross-database.
- **`SyncCursor.tenant_id`** uses `""` as the single-tenant sentinel instead of `NULL` — `unique_together` with `NULL` is not enforced consistently across SQL dialects.
- **Index name lengths** — all names ≤ 21 chars (PostgreSQL limit: 63, MSSQL limit: 128, Oracle limit: 128).
- **No raw SQL** — all queries go through the Django ORM. Raw SQL is explicitly prohibited in this library.

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Primary key type | UUID v7 | Time-ordered → natural cursor key; no sequence contention |
| HTTP client | `httpx` | Async-capable, great test support via `pytest-httpx` |
| Serialization | DRF serializers | Consistent with the REST API layer |
| Cursor design | `after=<uuid>` | O(new events) — no OFFSET degradation |
| Loop prevention | Thread-local flag | Prevents signal re-fire during apply without DB round-trip |
| Conflict default | Last-write-wins | Safe default; users override via `Backend.resolve_conflict()` |
| Task delivery | Pluggable | Same code works in simple deploys (sync) and scaled deploys (Celery) |
| No raw SQL | ORM only | Keeps the library portable across all Django-supported databases |
| Bootstrap strategy | Watermark + keyset snapshot | Watermark captured before rows are read; changes during export land in event stream naturally; no locks required (same pattern as Debezium incremental snapshots) |
| Snapshot pagination | Keyset (`after=<pk>`) not OFFSET | OFFSET degrades linearly on large tables; keyset is O(1) per page via PK index |
| Snapshot payload format | Same JSON as `ChangeEvent.payload` | Snapshot rows flow through the identical Phase 7 applier — no separate code path |
| Model export order | Topological sort via Django meta FK graph | Prevents FK constraint errors on the receiver; auto-derived, no user config needed |
| `SyncCursor.last_event_id` | Plain `UUIDField`, not FK | No constraint overhead on advance; event log can be pruned without nulling cursors |
| Snapshot state | `SyncCursor.snapshot_completed_at` | Null = snapshot required; set = streaming mode. Single field, no extra model |

---

## Settings Reference

```python
DJANGO_REPLICATION = {
    "NODE_ID": "your-node-uuid",                            # required
    "BACKEND": "django_rest_replication.backend.ReplicationBackend",
    "TASK_BACKEND": "django_rest_replication.tasks.sync.SynchronousTaskBackend",
    "TENANT_MODEL": None,       # e.g. "myapp.Organization"
    "TENANT_FIELD": "tenant_id",
    "BATCH_SIZE": 500,
    "MAX_RETRIES": 3,
    "RETRY_BACKOFF": 60,        # seconds
    "PRUNE_AFTER_DAYS": 30,
    "REQUEST_TIMEOUT": 30,      # seconds
}
```

---

## Immediate Next Steps (Phase 2)

1. Create `src/django_rest_replication/backend/base.py` — `BaseReplicationBackend` ABC
2. Create `src/django_rest_replication/backend/default.py` — `ReplicationBackend` (no-op + last-write-wins)
3. Validate `app_settings.BACKEND` lazy-imports and type-checks the class
4. Write unit tests with a custom backend subclass
5. Update `CHANGELOG.md` with Phase 2 entries
