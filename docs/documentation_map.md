# Documentation map

**Canonical index** for this repository. Other READMEs link here instead of maintaining parallel lists (so additions or renames happen in one place).

## By role

| Audience | English | Dutch |
| --- | --- | --- |
| End users | [`README_users.md`](README_users.md) | [`README_users.nl.md`](README_users.nl.md) |
| Managers / admins | [`README_managers.md`](README_managers.md) | [`README_managers.nl.md`](README_managers.nl.md) |
| Developers | [`README_developers.md`](README_developers.md) | [`README_developers.nl.md`](README_developers.nl.md) |

## Architecture and data

- [`architecture.md`](architecture.md) — system context and chat request flow (Mermaid)
- [`prompt_injection_and_guardrails.md`](prompt_injection_and_guardrails.md) — untrusted RAG context, prompt injection, deterministic guardrails
- [`schema.md`](schema.md) — SQLite tables, relationships, Chroma note
- [`admin_guide.md`](admin_guide.md) — short admin pointer (detail lives in role guides and in-app `/help`)

## Architecture decisions (ADRs)

- [`adr/README.md`](adr/README.md) — index
- [`adr/0001-sqlite-operational-database.md`](adr/0001-sqlite-operational-database.md) — SQLite default and migration threshold
- [`adr/0002-sso-enterprise-auth.md`](adr/0002-sso-enterprise-auth.md) — SSO/OIDC roadmap vs session auth today

## Operations and observability

- [`backup_and_restore.md`](backup_and_restore.md) — SQLite, Chroma, docs, training artifacts; restore outline
- [`observability.md`](observability.md) — logging, request IDs, metrics, and error tracking (target vs current)

## Privacy and compliance (EU-oriented)

- [`gdpr_data_retention.md`](gdpr_data_retention.md) — personal-data categories, retention posture, lawful bases as *deployment decisions*, erasure support vs documented gaps

## Backend and operations

- [`../backend/README.md`](../backend/README.md) — backend setup, ingest, OpenAPI pointers (EN)
- [`../backend/README.nl.md`](../backend/README.nl.md) — same (NL)
- [`../backend/pyproject.toml`](../backend/pyproject.toml) — Python package metadata; **`uv.lock`** for reproducible installs (see [`README_developers.md`](README_developers.md))
- [`../backend/test_runbook.md`](../backend/test_runbook.md) — RAG eval troubleshooting
- Root [`../README.md`](../README.md) — Docker quick start and product areas

## Training data and quality

- [`fine_tuning_data.md`](fine_tuning_data.md) — lifecycle and export shape
- [`validation_checklist.md`](validation_checklist.md) — hub: **initial acceptance** vs **every deploy**
- [`ci.md`](ci.md) — GitHub Actions (lint, tests, RAG smoke eval gate)

## Release and publishing

- [`github_publish_checklist.md`](github_publish_checklist.md) — GitHub / open-source readiness

## Repository hygiene (root of repo)

- [`../LICENSE`](../LICENSE)
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md)
- [`../SECURITY.md`](../SECURITY.md)

## Consolidated bundle

The repository’s `documentation/` directory (sibling of `docs/`) holds **copies** of many of these files for offline bundling. Edits belong in the paths above unless you are intentionally refreshing the bundle. When refreshing, include at least **`backend/test_runbook.md` → `documentation/backend/test_runbook.md`** and keep **`documentation/docs/documentation_map.md`** in sync with this file (adjusted paths for `documentation/` layout).
