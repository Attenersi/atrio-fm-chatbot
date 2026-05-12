# Contributing

Thanks for your interest in improving FM Chatbot.

## Development model

- Open an issue first for substantial changes.
- Use focused pull requests (one topic per PR).
- Keep commits small and descriptive.

## Local workflow (Docker-only)

1. Copy and configure `backend/.env` from `backend/.env.example`.
2. Start stack:
   - `docker compose up --build`
3. Run ingest when docs change:
   - `docker compose exec backend python -m app.ingest`
4. Run frontend typecheck before submitting:
   - `docker compose exec frontend npm run build`

## Pull request checklist

- [ ] Change is scoped and documented.
- [ ] User-facing behavior is tested manually.
- [ ] No secrets or private datasets are included.
- [ ] Docs updated (`README` and/or `docs/*`) if behavior changed.

## Code style expectations

- Prefer clear, explicit code over clever shortcuts.
- Preserve existing conventions in each module.
- Add tests when fixing bugs or changing core logic.

## Security and sensitive data

- Do not commit real credentials (`.env`, API keys, tokens).
- Do not commit sensitive chat/ticket exports unless explicitly sanitized.
- For vulnerabilities, follow `SECURITY.md` instead of filing a public issue.
