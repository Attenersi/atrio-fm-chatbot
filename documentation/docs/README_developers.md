# Developer Guide

Language: **English** | [Nederlands](README_developers.nl.md)

**Full documentation index**: [`documentation_map.md`](documentation_map.md)

## Project overview

FM chatbot stack:

- frontend: Next.js app (`frontend/`)
- backend: FastAPI service (`backend/`)
- operational DB: SQLite
- vector DB: Chroma (RAG retrieval)
- LLM integration: OpenAI-compatible provider

## Local setup (Docker-only)

Prerequisites: Docker with Compose, and `backend/.env` from `backend/.env.example`.

```bash
docker compose up --build
```

Ingest or reindex after document changes:

```bash
docker compose exec backend python -m app.ingest
```

## Architecture and request flow

See **[`architecture.md`](architecture.md)** for the canonical Mermaid diagrams (system context + chat sequence). Do not duplicate that narrative in other docs; link here.

### Main backend modules

- `backend/app/main.py` - API routes and orchestration
- `backend/app/rag.py` - retrieval and generation pipeline
- `backend/app/classifier.py` - output parsing and normalization
- `backend/app/database.py` - schema and persistence
- `backend/app/ingest.py` - document ingestion and embeddings
- `backend/app/prompt_analyzer.py` - suggestion generation
- `backend/app/prompt_consolidator.py` - merge helpers
- `backend/app/prompt_replay.py` - replay testing helpers
- `backend/app/llm_profiles.py` - provider profile management

## API and OpenAPI

FastAPI serves the **live** OpenAPI contract (always matches running code):

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

With default Docker Compose ports, use the same paths on **port 8000** on the host.

Route groups (for orientation only — prefer `/docs` for details): health (`/health*`), auth (`/api/auth/*`), chat (`/api/chat*`), tickets (`/api/tickets*`), admin (`/api/admin/*`), training quality (`/api/admin/training-quality/*`), LLM profiles (`/api/admin/llm/*`).

## Where to change behavior

- prompt composition and retrieval: `backend/app/rag.py`
- parsing/fallback handling: `backend/app/classifier.py`
- ticket heuristics and final payload rules: `backend/app/main.py`
- db schema and migrations: `backend/app/database.py`, `backend/app/db_migrations.py`

## CI

GitHub Actions: [`ci.md`](ci.md) (canonical [`../../docs/ci.md`](../../docs/ci.md)).

## Security / RAG trust

[`prompt_injection_and_guardrails.md`](prompt_injection_and_guardrails.md) — canonical [`../../docs/prompt_injection_and_guardrails.md`](../../docs/prompt_injection_and_guardrails.md).

## Quality workflow

### Evaluation

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Read both:

- `pass_rate` (all outcomes)
- `api_ok_pass_rate` (logic quality when API succeeds)

### Admin quality loop

In `/admin/training-quality`:

- run eval
- inspect mismatch groups
- analyze suggestions
- apply/rollback/consolidate prompt overrides
- replay affected examples

## Adding/updating FM knowledge

1. Edit files in `backend/docs_fm/` (or configured docs dir)
2. Reindex (`python -m app.ingest` or admin reindex endpoint)
3. Run targeted tests
4. Validate via chat and knowledge-gap backlog

Architecture, schema, training-data lifecycle, test runbook, and validation hubs are all linked from [`documentation_map.md`](documentation_map.md).
