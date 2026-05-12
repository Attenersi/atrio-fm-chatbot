# Release checklist (every deploy)

Run this for **each** deploy or tagged release. It is a short smoke pass; deep verification lives in [`validation_initial_acceptance.md`](validation_initial_acceptance.md).

## Build and health

- Container or service **builds** successfully (`docker compose build` or CI equivalent).
- Stack **starts** (`docker compose up` or production equivalent).
- `GET http://localhost:8000/health` returns OK (use host/port for your environment).
- Optionally: `GET /health/llm` when you rely on the LLM path for this release.

## Application smoke

- Frontend loads (default: `http://localhost:3000`).
- **Chat**: one informational question and one incident-style question succeed end-to-end.
- If multi-turn behavior shipped in this release: one short follow-up thread.

## Regression spot checks (only if touched this release)

- **RAG / classifier / `main` chat path changed**: run a small RAG eval or targeted automated tests; at minimum one manual chat that would have failed before.
- **Training capture changed**: insert or spot-check **one** new `training_examples` row for required fields.
- **Export or training admin API changed**: export a tiny NDJSON sample and confirm it still parses.
- **Docs changed**: skim the sections listed in [`documentation_map.md`](documentation_map.md) that correspond to your change.

## Done when

No blocking errors in the paths above and no known undocumented behavior change for operators or admins.
