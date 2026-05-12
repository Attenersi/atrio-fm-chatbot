# FM Chatbot

Language: **English** | [Nederlands](README.nl.md)

FM Chatbot is a Facility Management assistant platform with:

- Next.js frontend (`frontend/`)
- FastAPI backend (`backend/`)
- SQLite operational data store (users, sessions, tickets, gaps, training rows)
- Chroma vector index for retrieval (RAG)
- OpenAI-compatible LLM provider integration

## What the app does

The assistant answers FM questions using RAG, applies guardrails, may open tickets, and logs interactions for review. **End-to-end flow (diagrams)** lives in one place: [`docs/architecture.md`](docs/architecture.md).

## Documentation

**Canonical index** (all guides, technical docs, validation, and governance): [`docs/documentation_map.md`](docs/documentation_map.md)

## Quick start (Docker-only)

Recommended for all platforms: Compose behaves the same on Windows, macOS, and Linux.

Prerequisites:

- Docker Desktop (or Docker Engine + Compose plugin)
- valid `backend/.env` (copy from `backend/.env.example` and set real secrets)

Native install without Docker (venv + npm), including **PowerShell and bash** commands: [`SECOND_COMPUTER_SETUP.md`](SECOND_COMPUTER_SETUP.md).

### 1) Build and run

```bash
docker compose up --build
```

Open `http://localhost:3000`.

### 2) Ingest FM docs (first run and after docs changes)

```bash
docker compose exec backend python -m app.ingest
```

### 3) Useful ops commands

```bash
# stop services
docker compose down

# view backend logs
docker compose logs -f backend

# view frontend logs
docker compose logs -f frontend
```

## Main product areas

- `/chat` - user conversations and automated ticket creation
- `/dashboard` - ticket list, stats, filters, status updates
- `/help` - in-app help and operational guidance
- `/admin` - docs, users, knowledge gaps, training review, quality tools
- `/admin/training-quality` - eval runs, analyzer suggestions, prompt overrides
- `/admin/llm` - LLM profile management and task defaults

## Quality and testing

Run the RAG evaluation suite:

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Interpret:

- `pass_rate` (all cases, including transport failures)
- `api_ok_pass_rate` (logic quality when API responds correctly)

See [`backend/test_runbook.md`](backend/test_runbook.md) for troubleshooting and rerun strategy.
