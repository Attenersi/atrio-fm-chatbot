# ADR 0001: SQLite as operational database (default)

## Status

Accepted (default for this repository).

## Context

- The backend persists tickets, users, chat, training examples, and related tables in **SQLite** (see [`backend/app/database.py`](../../backend/app/database.py)), typically a single file (`SQLITE_DB_PATH`, default `tickets.db`), with WAL mode enabled for better read concurrency.
- Deployments target **single-tenant** or **low-to-moderate concurrency** (few concurrent writers, modest admin activity).
- The schema is accessed mostly through **raw SQL** and `sqlite3`; Alembic migrations exist for evolution.

SQLite is operationally simple (one file, easy backup), but is **not** the industry default for multi-tenant SaaS with heavy concurrent writes, HA replicas, or strict database-enforced row-level security.

## Decision

Keep **SQLite** as the default and documented operational store for this product **as shipped in this repo**.

## Consequences

- **Pros:** Minimal ops overhead, straightforward local/Docker dev, file-based backup story (see [`backup_and_restore.md`](../backup_and_restore.md)).
- **Cons:** Writer contention under bursty multi-admin load; no built-in multi-primary HA; advanced isolation models require application discipline.
- **Backups:** Must account for WAL/SHM sidecar files and crash consistency (see backup doc).

## Migration threshold (when to plan Postgres or similar)

Consider moving the operational database to **PostgreSQL** (or another server RDBMS) when **any** of the following becomes a sustained requirement:

- Heavy **concurrent write** load (many admins or automations updating tickets/training rows at once) and observable lock/wait issues on SQLite.
- **High availability / read replicas** or failover expectations at the database tier.
- **Multi-tenant** isolation enforced primarily in the database (RLS, separate schemas, etc.).
- Organizational mandate for **managed** DB features (point-in-time recovery, auditing) beyond file copy + WAL.

A migration would likely introduce an ORM or repository layer, replace raw SQL gradually, and reimplement migrations—**non-trivial** today because SQL is embedded throughout `database.py` and related modules.

## Related

- [`docs/architecture.md`](../architecture.md) — system diagram (SQLite as data store).
- [`docs/schema.md`](../schema.md) — table reference.
