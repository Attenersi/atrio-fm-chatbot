# FM Chatbot

Language: **English** | [Nederlands](README.nl.md)

FM Chatbot is an AI assistant for Facility Management teams. It helps users get fast, policy-aligned answers from internal building and operations documentation while keeping support workflows connected to tickets and review.

It combines a Next.js frontend, FastAPI backend, RAG retrieval over FM docs, and admin quality tooling so teams can improve answers over time instead of treating chatbot behavior as static.

## Who it is for

- FM operations teams handling daily building questions
- Helpdesk and support staff triaging user requests
- Admins and domain experts maintaining documentation, quality, and guardrails

## Benefits

- Faster first responses to common FM questions
- More consistent answers grounded in your own documents
- Reduced repetitive ticket load through better self-service
- Better operational visibility with logs, reviews, and quality workflows

## Core features

- Grounded Q&A over FM documents using retrieval-augmented generation (RAG)
- Guardrails for prompt injection and sensitive output patterns
- Ticket-aware workflows (chat interactions can open and track support tickets)
- Admin console for documents, users, gaps, training review, and quality controls
- LLM profile management for provider/model defaults and diagnostics
- Full role-based feature inventory: [`docs/features.md`](docs/features.md)

## Documentation

**Canonical index** (all guides, technical docs, validation, and governance): [`docs/documentation_map.md`](docs/documentation_map.md)
**End-to-end flow (diagrams):** [`docs/architecture.md`](docs/architecture.md)

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

## Platform components

- Next.js frontend (`frontend/`)
- FastAPI backend (`backend/`)
- SQLite operational data store (users, sessions, tickets, gaps, training rows)
- Chroma vector index for retrieval
- OpenAI-compatible LLM provider integration

## Quality and testing

Run the RAG evaluation suite:

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Interpret:

- `pass_rate` (all cases, including transport failures)
- `api_ok_pass_rate` (logic quality when API responds correctly)

See [`backend/test_runbook.md`](backend/test_runbook.md) for troubleshooting and rerun strategy.
