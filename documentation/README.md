# Central documentation folder

This directory holds **copies** of documentation for bundling or offline reading. **Edits belong in the originals** under the repo root (`docs/`, `backend/`, etc.).

**Canonical documentation index** (maintain links there, not here): [`../docs/documentation_map.md`](../docs/documentation_map.md)

## Refreshing this bundle (e.g. before zipping)

Copy or reconcile from the repo so internal links stay valid:

| Canonical source | Bundle target |
| --- | --- |
| `docs/*.md` (role guides, architecture, schema, validation, publish checklist, …) | `documentation/docs/` |
| `backend/README.md`, `backend/README.nl.md` | `documentation/backend/` |
| **`backend/test_runbook.md`** | **`documentation/backend/test_runbook.md`** |

The file **`documentation/docs/documentation_map.md`** is a bundle-oriented sibling of `docs/documentation_map.md` (paths adjusted for `documentation/`). Prefer editing **`docs/documentation_map.md`**, then update the bundle copy.

Root-only files (`LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) are not duplicated here; they live at the repository root and are linked from the map.
