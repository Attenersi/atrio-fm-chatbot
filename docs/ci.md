# Continuous integration

GitHub Actions workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Jobs

| Job | Purpose |
| --- | --- |
| **backend** | `uv sync --frozen --group dev`, then `uv run` for `ruff` (tests/scripts/root utilities; `app/` excluded for now — see [`backend/ruff.toml`](../backend/ruff.toml)), incremental `mypy`, `pytest`, `pip-audit` on runtime deps (see [`backend/requirements.txt`](../backend/requirements.txt), exported from [`backend/uv.lock`](../backend/uv.lock)). |
| **frontend** | `npm run lint`, `npm run format:check` (Prettier), `npm run typecheck` (`tsc --noEmit`), `npm audit --audit-level=critical`. |
| **eval** | Docker Compose stack, ingest, [`backend/test_rag.py`](../backend/test_rag.py) against [`backend/tests/suites/ci_eval_smoke.json`](../backend/tests/suites/ci_eval_smoke.json) with `--min-api-ok-pass-rate` and `--min-api-ok-count`. |

## Secrets and variables (eval job)

The **eval** job runs only when:

- Repository secret **`LLM_API_KEY`** or **`NVIDIA_API_KEY`** is non-empty (either works; legacy name kept for existing repos), and
- The event is not a **fork** pull request (`github.event.pull_request.head.repo.fork == false`), or the event is a **push** (same-repo).

Recommended secrets:

| Name | Use |
| --- | --- |
| `LLM_API_KEY` | Preferred: OpenAI-compatible chat + embed key (or set `LLM_EMBED_API_KEY` / legacy `NVIDIA_EMBED_API_KEY` separately). |
| `NVIDIA_API_KEY` | Legacy alias; used if `LLM_API_KEY` is unset. |
| `LLM_EMBED_API_KEY` / `NVIDIA_EMBED_API_KEY` | Optional; defaults to the chat key in app config. |
| `CI_ADMIN_PASSWORD` | Optional; must match `ADMIN_PASSWORD` written into the CI-generated `backend/.env`. Defaults to `ci-admin-password` if unset. |

Repository variable (optional):

| Name | Default | Use |
| --- | --- | --- |
| `EVAL_MIN_API_OK_PASS_RATE` | `70` | Minimum `api_ok_pass_rate` (percent) required for the smoke suite. |

## `test_rag.py` exit codes

Documented in `python test_rag.py --help`. Summary: `0` success, `1` case failures, `2` runtime error, `3` api_ok gate failure.

## Reproducing eval locally

```bash
docker compose up -d --build
docker compose exec backend python -m app.ingest
cd backend
python test_rag.py --base-url http://127.0.0.1:8000 --cases-file tests/suites/ci_eval_smoke.json --min-api-ok-count 1 --min-api-ok-pass-rate 70
```

## Dependency audit notes

- **npm**: `audit-level=critical` avoids failing the build on known **high** issues in current Next.js 14 transitive deps until you upgrade. Tighten to `--audit-level=high` after bumping Next/eslint stack.
- **pip**: `uv run pip-audit` targets runtime [`requirements.txt`](../backend/requirements.txt) only.
