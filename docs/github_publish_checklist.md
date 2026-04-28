# GitHub Publish Checklist (Security + Privacy)

Use this checklist before publishing the repository.

## 1) Secret Safety

- Keep real secrets only in local `backend/.env` (never commit this file).
- Rotate any previously exposed keys/tokens:
  - `NVIDIA_API_KEY`
  - `NVIDIA_EMBED_API_KEY`
  - `ADMIN_TOKEN`
  - any real admin/user passwords
- Use `backend/.env.example` as the public template.

## 2) Privacy Safety

- Do not publish raw local data:
  - `backend/tickets.db`
  - `backend/chroma_db/`
  - `backend/tests/results/`
  - `backend/data/fine_tuning_v1_candidates.jsonl`
  - `backend/data/fine_tuning_v1_train.jsonl`
  - `backend/data/fine_tuning_v1_review.csv`
- Treat any chat/ticket-derived JSONL as potentially sensitive unless anonymized.

## 3) Pre-push Check

- Run:
  - `python backend/security_prepush_check.py`
- If this script reports issues, fix them before commit/push.

## 4) What You Need On This Computer

- Local `backend/.env` with valid secrets.
- Installed dependencies (`backend/venv`, `frontend/node_modules`).
- Optional local state (`backend/tickets.db`, `backend/chroma_db`).

## 5) What You Need On Another Computer

- Clone repository code.
- Install backend/frontend dependencies.
- Create `backend/.env` from `backend/.env.example` and fill real values.
- Run ingest/init to build local data, or transfer `tickets.db` and `chroma_db` privately.

## 6) GO/NO-GO Decision

- GO only if:
  - no real secrets in tracked files,
  - no sensitive local datasets staged,
  - pre-push check passes.
- Otherwise: NO-GO.
