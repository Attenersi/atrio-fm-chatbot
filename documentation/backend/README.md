# Backend

Language: **English** | [Nederlands](README.nl.md)

FastAPI service for:

- auth and session handling
- chat orchestration (sync and stream)
- ticket CRUD and status changes
- admin operations (users, docs, gaps, training quality)
- training-data capture and review workflows

**Architecture (diagrams)**: [`../docs/architecture.md`](../docs/architecture.md). **SQLite tables**: [`../docs/schema.md`](../docs/schema.md).

## Setup (Docker-only)

Use root-level Compose:

```bash
docker compose up --build
```

## Environment

Create `backend/.env` from `backend/.env.example`.

Required (typical):

- `LLM_API_KEY` (or legacy `NVIDIA_API_KEY`)
- `LLM_BASE_URL` (or legacy `NVIDIA_BASE_URL`)
- `LLM_MODEL`
- `EMBED_MODEL`
- `DOCS_DIR`
- `CHROMA_DIR`
- `SQLITE_DB_PATH`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

Optional:

- SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`)
- bootstrap user (`AUTH_BOOTSTRAP_USER_USERNAME`, `AUTH_BOOTSTRAP_USER_PASSWORD`)

## Run

Backend runs via Docker Compose (`backend` service in `docker-compose.yml`).

## Ingest documents

```bash
docker compose exec backend python -m app.ingest
```

This rebuilds the vector index from `docs_fm/` (or configured docs path).

## Core modules

- `app/main.py` - API routes + orchestration
- `app/rag.py` - retrieval and generation pipeline
- `app/classifier.py` - parsing/normalization of model output
- `app/database.py` - SQLite schema and queries
- `app/ingest.py` - chunking and embedding ingestion
- `app/llm.py` - LLM and embedding API wrappers
- `app/prompt_analyzer.py` - suggestion analysis
- `app/prompt_consolidator.py` - rule merge helpers
- `app/prompt_replay.py` - replay evaluation helpers

## API and OpenAPI

Interactive API docs (generated from the running app):

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)

Use these instead of static route lists. High-level grouping is also summarized in [`../docs/README_developers.md`](../docs/README_developers.md).

## Quality testing

Run evaluation:

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Track:

- `pass_rate`
- `api_ok_pass_rate` / `api_ok_only`

Reference: [`test_runbook.md`](test_runbook.md) (canonical: `backend/test_runbook.md` in a full clone).

## Maintenance notes

- Utilities: `backend/scripts/`
- Migrations/helpers: `backend/app/db_migrations.py`
- Publish safety checklist: [`../docs/github_publish_checklist.md`](../docs/github_publish_checklist.md)
