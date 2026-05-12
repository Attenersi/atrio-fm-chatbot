# Documentation map

**Canonical index** (edit in **`docs/documentation_map.md`** in a full clone): this copy stays aligned for offline bundles under `documentation/`.

## By role

| Audience | English | Dutch |
| --- | --- | --- |
| End users | [`README_users.md`](README_users.md) | [`README_users.nl.md`](README_users.nl.md) |
| Managers / admins | [`README_managers.md`](README_managers.md) | [`README_managers.nl.md`](README_managers.nl.md) |
| Developers | [`README_developers.md`](README_developers.md) | [`README_developers.nl.md`](README_developers.nl.md) |

## Architecture and data

- [`architecture.md`](architecture.md) — system context and chat request flow (Mermaid)
- [`prompt_injection_and_guardrails.md`](prompt_injection_and_guardrails.md) — RAG trust boundaries (pointer to canonical doc)
- [`schema.md`](schema.md) — SQLite tables, relationships, Chroma note
- [`admin_guide.md`](admin_guide.md) — short admin pointer (detail lives in role guides and in-app `/help`) — *if not bundled, see full repo `docs/`*

## Architecture decisions (ADRs)

- [`adr/README.md`](adr/README.md) — canonical: [`../../docs/adr/README.md`](../../docs/adr/README.md)
- [`adr/0001-sqlite-operational-database.md`](adr/0001-sqlite-operational-database.md)
- [`adr/0002-sso-enterprise-auth.md`](adr/0002-sso-enterprise-auth.md)

## Operations and observability

- [`backup_and_restore.md`](backup_and_restore.md) — canonical: [`../../docs/backup_and_restore.md`](../../docs/backup_and_restore.md)
- [`observability.md`](observability.md) — canonical: [`../../docs/observability.md`](../../docs/observability.md)

## Privacy and compliance (EU-oriented)

- [`gdpr_data_retention.md`](gdpr_data_retention.md) — canonical: [`../../docs/gdpr_data_retention.md`](../../docs/gdpr_data_retention.md)

## Backend and operations

- [`../backend/README.md`](../backend/README.md) — backend setup, ingest, OpenAPI pointers (EN)
- [`../backend/README.nl.md`](../backend/README.nl.md) — same (NL)
- [`../backend/pyproject.toml`](../backend/pyproject.toml) — `uv.lock` for reproducible installs; see canonical [`../../docs/README_developers.md`](../../docs/README_developers.md)
- [`../backend/test_runbook.md`](../backend/test_runbook.md) — RAG eval troubleshooting
- Root [`../../README.md`](../../README.md) — Docker quick start and product areas

## Training data and quality

- [`fine_tuning_data.md`](fine_tuning_data.md)
- [`validation_checklist.md`](validation_checklist.md) — hub: **initial acceptance** vs **every deploy**
- [`ci.md`](ci.md) — GitHub Actions (pointer to canonical [`../../docs/ci.md`](../../docs/ci.md))

## Release and publishing

- [`github_publish_checklist.md`](github_publish_checklist.md) — GitHub / open-source readiness

## Repository hygiene (repository root)

In a **full clone**, these live next to `docs/`:

- [`../../LICENSE`](../../LICENSE)
- [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)
- [`../../CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md)
- [`../../SECURITY.md`](../../SECURITY.md)

## Consolidated bundle

The `documentation/` directory holds **copies** for offline reading. Refresh from `docs/`, `backend/`, and root when preparing a zip so links stay accurate.
