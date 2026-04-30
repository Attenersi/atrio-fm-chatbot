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

- **Production / real tenant data:** do not publish operational SQLite, Chroma, or exports that contain real people, suites, or incidents.
- **Test fixtures:** this repo may intentionally track a **sanitized** [`backend/tickets.db`](backend/tickets.db) so clones share the same dev dataset; only commit DB snapshots you are willing to share. Regenerate `fine_tuning_v1_candidates.jsonl` after pull with `POST /api/admin/training-examples/v1/rebuild-json-store` if needed.
- Still treat as local-only by default:
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
- If `tickets.db` is not in the repo, run ingest/init to build local data or copy it privately; copy `chroma_db` privately if you need the same vector index without re-ingesting.

## 6) GO/NO-GO Decision

- GO only if:
  - no real secrets in tracked files,
  - no sensitive local datasets staged,
  - pre-push check passes.
- Otherwise: NO-GO.

## 7) Production hardening

When you actually deploy the backend to a public URL, set these env vars in
`backend/.env` (do not commit them):

- `AUTH_COOKIE_SECURE=true` — required behind HTTPS so the session cookie is
  not sent over plain HTTP.
- `AUTH_COOKIE_SAMESITE=lax` — recommended default. Use `strict` only if you
  do not rely on cross-site redirects (e.g. SSO links from email/Slack will
  drop the cookie when set to `strict`).
- `CORS_ALLOW_ORIGIN_REGEX` — must match your production frontend origin
  (default allows only `localhost`/`127.0.0.1`). Example:
  `^https://app\\.example\\.com$`.
- `AUTH_BOOTSTRAP_USER_PASSWORD` — leave **empty** in production to skip the
  default `user` account, or set a strong unique value if you intentionally
  want a seed account.
- `ADMIN_PASSWORD` — never deploy with the placeholder/default value.
- Rotate `NVIDIA_API_KEY` and `NVIDIA_EMBED_API_KEY` if they ever appeared in
  a shared env file or screenshot.

Cross-device dev (testing the frontend from a phone over the LAN):

- Set `CORS_ALLOW_ORIGIN_REGEX` explicitly, e.g.
  `^https?://(localhost|127\\.0\\.0\\.1|192\\.168\\.\\d{1,3}\\.\\d{1,3}|[a-zA-Z0-9.-]+\\.local)(:\\d+)?$`,
  otherwise the browser will block requests from `192.168.x.x` to the backend.
