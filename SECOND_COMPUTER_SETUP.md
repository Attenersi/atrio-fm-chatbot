# Second Computer Setup (Private)

This guide is for your private transfer/setup on another machine **without Docker** (native Node + Python venv). For the supported team path, prefer **[`README.md`](README.md) quick start** (`docker compose` works the same on Windows, macOS, and Linux).

## 1) Clone repository

**PowerShell (Windows)**

```powershell
git clone <your-repo-url>
cd fm-chatbot
```

**bash / zsh (macOS / Linux)**

```bash
git clone <your-repo-url>
cd fm-chatbot
```

## 2) Backend setup

**PowerShell**

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

**bash / zsh**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` with your real private values (API keys, admin credentials, etc.).

## 3) Frontend setup

**PowerShell**

```powershell
cd ..\frontend
npm install
```

**bash / zsh**

```bash
cd ../frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8010
```

## 4) Rebuild RAG index (required if you do not copy `chroma_db`)

**PowerShell**

```powershell
cd ..\backend
.\venv\Scripts\python.exe -m app.ingest
```

**bash / zsh**

```bash
cd ../backend
./venv/bin/python -m app.ingest
```

This rebuilds local vector index from `backend/docs_fm`.

## 5) Optional: copy your local state from main computer

If you want the same history/data immediately, copy privately:

- `backend/tickets.db`
- `backend/chroma_db/`
- `backend/data/fine_tuning_v1_candidates.jsonl`

You can skip this and start clean if preferred.

## 6) Start app

From repo root, `npm run dev` starts both services when configured in root `package.json`.

**PowerShell**

```powershell
npm run dev
```

**bash / zsh**

```bash
npm run dev
```

Expected:

- backend: `http://localhost:8010`
- frontend: `http://localhost:3010`

