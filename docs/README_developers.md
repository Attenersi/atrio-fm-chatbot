# Developer Guide

## What this project is

FM chatbot platform with:
- Next.js frontend (`frontend/`)
- FastAPI backend (`backend/`)
- RAG over FM docs (`backend/docs_fm/`)
- ticketing and admin workflows
- quality test suite (`backend/test_rag.py`)

## Local setup (Windows / PowerShell)

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env` with valid NVIDIA credentials and paths.

### Frontend

```powershell
cd ..\frontend
npm install
```

Set `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Ingest docs and run

```powershell
cd ..\backend
.\venv\Scripts\python.exe -m app.ingest
.\venv\Scripts\python.exe -m app.main
```

In another terminal:

```powershell
cd frontend
npm run dev
```

## Key backend flows

### Chat request path

1. `/api/chat` receives message and history.
2. `retrieve_with_sources()` pulls doc chunks from Chroma.
3. `generate()` returns structured JSON from LLM.
4. `_finalize_chat_payload()` applies deterministic safety/business rules.
5. Optional ticket is created and query is logged to training examples.

### Streaming path

`/api/chat/stream` emits chunks, then final payload using the same finalization logic.

## Where to change behavior

- Prompt/RAG rules: `backend/app/rag.py`
- Parsing fallback/strictness: `backend/app/classifier.py`
- Heuristics for category/priority/ticketing: `backend/app/main.py`
- Data persistence/schema: `backend/app/database.py`

## Testing and evaluation

Run full suite:

```powershell
cd backend
.\venv\Scripts\python.exe -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Recommended interpretation:
- `pass_rate` (all)
- `api_ok_pass_rate` (logic only when API responded)

See `backend/test_runbook.md` for timeout/retry strategy and reruns.

## Adding new FM knowledge

1. Add or edit docs in `backend/docs_fm/`
2. Reindex (`python -m app.ingest` or admin reindex endpoint)
3. Re-run selected tests
4. Review knowledge gaps in admin panel

## Fine-tuning data lifecycle

Every processed query is captured as a training-example candidate.
Spec and review workflow: `docs/fine_tuning_data.md`.
