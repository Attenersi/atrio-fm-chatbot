# Backend

Taal: [English](README.md) | **Nederlands**

FastAPI-service voor:

- authenticatie en sessies
- chatorchestratie (sync + stream)
- ticketbeheer en statusupdates
- adminoperaties (users, docs, gaps, training quality)
- logging voor training- en kwaliteitsworkflows

**Architectuur (diagrammen, EN)**: [`docs/architecture.md`](../docs/architecture.md). **SQLite-tabellen (EN)**: [`docs/schema.md`](../docs/schema.md).

## Setup (alleen Docker)

Gebruik Compose vanuit de root:

```bash
docker compose up --build
```

De frontend-image bakt **`NEXT_PUBLIC_API_URL` tijdens de build**. Standaard: `http://localhost:8000`. Voor een andere API-URL: zet `NEXT_PUBLIC_API_URL` en herbouw de frontend (`docker compose build --no-cache frontend`). Zie ook [`docker-compose.override.yml.example`](../docker-compose.override.yml.example) voor hot reload.

## Omgevingsvariabelen

Maak `backend/.env` vanuit `backend/.env.example`.

Gebruikelijk verplicht:

- `LLM_API_KEY` (of legacy `NVIDIA_API_KEY`)
- `LLM_BASE_URL` (of legacy `NVIDIA_BASE_URL`)
- `LLM_MODEL`
- `EMBED_MODEL`
- `DOCS_DIR`
- `CHROMA_DIR`
- `SQLITE_DB_PATH`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

Optioneel:

- SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`)
- bootstrap user (`AUTH_BOOTSTRAP_USER_USERNAME`, `AUTH_BOOTSTRAP_USER_PASSWORD`)

## Starten

Backend draait via Docker Compose (`backend` service in `docker-compose.yml`).

## Document ingest

```bash
docker compose exec backend python -m app.ingest
```

Dit bouwt de vectorindex opnieuw op vanuit `docs_fm/` (of het geconfigureerde docs-pad).

## Kernmodules

- `app/main.py` - routes + orchestratie
- `app/rag.py` - retrieval en generatie
- `app/classifier.py` - parsing/normalisatie modeloutput
- `app/database.py` - SQLite schema en queries
- `app/ingest.py` - chunking en embedding ingest
- `app/llm.py` - LLM/embedding clients
- `app/prompt_analyzer.py` - suggestie-analyse
- `app/prompt_consolidator.py` - merge helpers
- `app/prompt_replay.py` - replay helpers

## API en OpenAPI

Interactieve API-docs (van de draaiende app):

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)

Gebruik deze i.p.v. statische routelijsten. Zie ook [`docs/README_developers.nl.md`](../docs/README_developers.nl.md).

## Kwaliteitstests

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Volg:

- `pass_rate`
- `api_ok_pass_rate` / `api_ok_only`

Referentie: `backend/test_runbook.md`.

## Onderhoud

- Utilities: `backend/scripts/`
- Migraties/helpers: `backend/app/db_migrations.py`
- Publicatiechecklist: `../docs/github_publish_checklist.md`
