# Backend

FastAPI service for authentication, chat orchestration, ticketing, admin operations,
knowledge-gap handling, and training-data logging.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Environment

Create `backend/.env` and configure at minimum:

- `NVIDIA_API_KEY`
- `NVIDIA_BASE_URL` (default is NVIDIA OpenAI-compatible endpoint)
- `LLM_MODEL`
- `EMBED_MODEL`
- `DOCS_DIR`
- `CHROMA_DIR`
- `SQLITE_DB_PATH`
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`

Optional:
- SMTP settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`)
- bootstrap non-admin account (`AUTH_BOOTSTRAP_USER_USERNAME`, `AUTH_BOOTSTRAP_USER_PASSWORD`)

Start from `backend/.env.example` and keep real secrets only in local `.env`.

## Run service

Development:

```powershell
.\venv\Scripts\python.exe -m app.main
```

Alternative:

```powershell
uvicorn app.main:app --reload --port 8000
```

## Ingest docs

```powershell
.\venv\Scripts\python.exe -m app.ingest
```

This rebuilds the Chroma index from files in `docs_fm/` (or your configured `DOCS_DIR`).

## Core modules

- `app/main.py` - FastAPI routes and chat/ticket orchestration
- `app/rag.py` - retrieval and generation prompt pipeline
- `app/classifier.py` - LLM JSON parsing/fallback
- `app/database.py` - SQLite schema and CRUD
- `app/ingest.py` - document chunking and embedding
- `app/llm.py` - NVIDIA chat/embed client wrappers

## API areas

- Auth/session: `/api/auth/*`
- Chat: `/api/chat`, `/api/chat/stream`
- Tickets: `/api/tickets*`
- Admin docs/users/reindex: `/api/admin/*`
- Knowledge gaps: `/api/admin/knowledge-gaps*`
- Training examples (fine-tuning pipeline): `/api/admin/training-examples*`

## Quality testing

Use `test_rag.py` with `atrio_test_cases.json`.
Runbook: `test_runbook.md`.

## Publish safety and second computer setup

See `docs/github_publish_checklist.md` for:
- security/privacy pre-push checklist,
- what is needed to keep running on this computer,
- what is required to run on a second computer.

Focus on both:
- all-case pass rate
- `api_ok_only` pass rate
