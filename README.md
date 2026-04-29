# FM Chatbot

Facility Management chatbot platform with:
- Next.js frontend
- FastAPI backend
- NVIDIA NIM (OpenAI-compatible API)
- ChromaDB retrieval index (RAG)
- SQLite operational storage (users, sessions, tickets, gaps, training examples)

## Who this documentation is for

- Developers: see `docs/README_developers.md`
- Managers/Admins (current role mapping): see `docs/README_managers.md`
- End users (tenant/staff chat users): see `docs/README_users.md`
- Fine-tuning data lifecycle: see `docs/fine_tuning_data.md`
- Validation checklist: `docs/validation_checklist.md`

## System overview

1. User sends message from frontend chat.
2. Backend retrieves context from FM documents in Chroma.
3. LLM generates structured JSON classification + response.
4. Backend applies safety/business heuristics and optional ticket creation.
5. Backend logs each query as a training example candidate for future fine-tuning.

## Quick start (Windows / PowerShell)

### 1) Backend setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Create/edit `backend/.env` (NVIDIA API key and app settings).

### 2) Frontend setup

```powershell
cd ..\frontend
npm install
```

Create/edit `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3) Ingest FM docs (first run and after doc changes)

```powershell
cd ..\backend
.\venv\Scripts\python.exe -m app.ingest
```

### 4) Start backend

```powershell
.\venv\Scripts\python.exe -m app.main
```

### 5) Start frontend

```powershell
cd ..\frontend
npm run dev
```

Open `http://localhost:3000`.

### One-command dev start (backend + frontend)

From repo root:

```powershell
npm install
npm run dev
```

This starts:
- backend on `http://localhost:8000`
- frontend on `http://localhost:3000`

## Testing quality

RAG test runner lives in `backend/test_rag.py`.

Recommended sequence:

```powershell
cd backend
.\venv\Scripts\python.exe -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Interpret both:
- `pass_rate` (all cases)
- `api_ok_pass_rate` (logic quality without transport failures)

Detailed guidance: `backend/test_runbook.md`.
