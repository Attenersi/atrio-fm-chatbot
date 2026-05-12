# Admin Guide

Language: **English** | See in-app `/help` for role-based guidance.

This file intentionally contains only English content.
If you need a full handbook, use:

- `/help` in the app UI,
- role-specific docs in `docs/README_users.md`, `docs/README_managers.md`, `docs/README_developers.md`,
- centralized copy in `documentation/`.

## Admin quick operations

1. Monitor tickets in `/dashboard`.
2. Manage docs, users, and knowledge gaps in `/admin`.
3. Reindex after every document update.
4. Review training examples in `/admin/training`.
5. Run quality loop in `/admin/training-quality` (eval -> analyze -> apply/rollback).

## Troubleshooting shortcuts

- Bot still uses old knowledge: run **Reindex**.
- Missing answer: resolve a **Knowledge Gap** and reindex.
- Misclassified ticket: use **Classification Override**.
- Regression after prompt changes: rollback override and rerun eval.
