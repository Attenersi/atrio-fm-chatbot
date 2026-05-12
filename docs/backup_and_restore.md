# Backup and restore

Operational data is **mostly files** on disk. This page describes what to back up, how often, and how to restore. **Cadence and retention are organizational choices** (compliance, RPO/RTO); the product does not run backup jobs for you.

## What to back up

| Asset | Env var (default) | Notes |
| --- | --- | --- |
| Operational database | `SQLITE_DB_PATH` (`tickets.db`) | SQLite may create **WAL** (`-wal`) and **SHM** (`-shm`) siblings. Copy all three together for a crash-consistent snapshot, or use SQLite’s **backup API** / `.backup` while the app is quiet. |
| Vector index | `CHROMA_DIR` (`chroma_db/`) | Entire directory. Out of sync with DB/docs if restored alone. |
| FM document corpus | `DOCS_DIR` (`docs_fm/`) | Source files for RAG; needed if you rebuild Chroma from ingest. |
| Training exports | `TRAINING_DATA_DIR` (`data/`) | JSONL/CSV/manifest artifacts; regenerable from DB when auto-refresh is enabled, but backups avoid rework. |

Personal and ticket content may appear in the DB and exports; treat backups like production data ([`gdpr_data_retention.md`](gdpr_data_retention.md)).

## Recommended practices

- **Snapshot together:** Where possible, capture **SQLite + `CHROMA_DIR` + `DOCS_DIR`** from the same maintenance window so retrieval matches indexed chunks.
- **Quiet window or hot backup:** For SQLite, avoid copying only the main `.db` while WAL is active without using a proper backup method—read [SQLite backup](https://www.sqlite.org/backup.html) guidance.
- **Test restores:** Periodically restore to a non-production path and run smoke checks (health, ingest idempotency, sample chat).
- **Off-site copies:** Encrypt backup media; restrict access.

## Restore procedure (outline)

1. **Stop** the backend (and anything writing to the DB or Chroma paths).
2. **Replace** `SQLITE_DB_PATH` file (and WAL/SHM if applicable), `CHROMA_DIR`, and optionally `DOCS_DIR` / `TRAINING_DATA_DIR` from backup.
3. **Start** the backend; verify `/health` and a sample RAG query.
4. If Chroma is missing or corrupt but DB and docs exist, run **ingest** (`python -m app.ingest` or Docker equivalent) to rebuild embeddings.

## Related

- [`adr/0001-sqlite-operational-database.md`](adr/0001-sqlite-operational-database.md) — why SQLite and when to migrate.
- [`schema.md`](schema.md) — tables in the SQLite file.
