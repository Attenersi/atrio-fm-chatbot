# Developer Handleiding

Taal: [English](README_developers.md) | **Nederlands**

**Volledige documentatie-index**: [`documentation_map.md`](documentation_map.md)

## Projectoverzicht

FM chatbot-stack:

- frontend: Next.js (`frontend/`)
- backend: FastAPI (`backend/`)
- operationele DB: SQLite
- vector DB: Chroma (RAG retrieval)
- modelprovider: OpenAI-compatibel endpoint

## Lokale setup (alleen Docker)

Vereisten: Docker met Compose en `backend/.env` vanuit `backend/.env.example`.

```bash
docker compose up --build
```

Ingest/reindex na documentwijzigingen:

```bash
docker compose exec backend python -m app.ingest
```

## Architectuur en requestflow

Zie **[`architecture.md`](architecture.md)** voor de canonieke Mermaid-diagrammen. Voeg die uitleg niet opnieuw toe in andere documenten; link hierheen.

### Belangrijkste backendmodules

- `backend/app/main.py` - routes + orkestratie
- `backend/app/rag.py` - retrieval + generatie
- `backend/app/classifier.py` - parsing/normalisatie
- `backend/app/database.py` - schema + persistence (zie ook [`schema.md`](schema.md))
- `backend/app/ingest.py` - chunking + embeddings
- `backend/app/prompt_analyzer.py` - suggesties
- `backend/app/prompt_consolidator.py` - merge helpers
- `backend/app/prompt_replay.py` - replay helpers
- `backend/app/llm_profiles.py` - providerprofielen

## API en OpenAPI

FastAPI levert het **actuele** OpenAPI-contract:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

Met standaard Docker Compose-poorten: dezelfde paden op host-poort **8000**.

Routegroepen (alleen ter orientatie — gebruik `/docs` voor details): health (`/health*`), auth (`/api/auth/*`), chat (`/api/chat*`), tickets (`/api/tickets*`), admin (`/api/admin/*`), training quality (`/api/admin/training-quality/*`), LLM-profielen (`/api/admin/llm/*`).

## Waar gedrag aanpassen

- prompt/retrieval: `backend/app/rag.py`
- parsing/fallback: `backend/app/classifier.py`
- ticketheuristiek/finalisatie: `backend/app/main.py`
- schema/migraties: `backend/app/database.py`, `backend/app/db_migrations.py`

## CI

GitHub Actions: [`ci.md`](ci.md).

## Security / RAG

[`prompt_injection_and_guardrails.md`](prompt_injection_and_guardrails.md).

## Kwaliteitsworkflow

### Evaluatie

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Lees beide:

- `pass_rate`
- `api_ok_pass_rate` (`api_ok_only`)

### Admin quality loop

In `/admin/training-quality`:

- eval draaien
- mismatch-groepen analyseren
- suggesties beoordelen
- overrides toepassen/terugdraaien/samenvoegen
- replayen op relevante voorbeelden

## FM-kennis toevoegen/updaten

1. docs aanpassen in `backend/docs_fm/` (of geconfigureerd docs-pad)
2. reindex draaien
3. gerichte tests uitvoeren
4. valideren via chat en knowledge-gap backlog

Architectuur, schema, fine-tuning lifecycle, test runbook en validatie staan in [`documentation_map.md`](documentation_map.md).
