# Security Policy

## Supported versions

Security fixes are applied to the latest state of the default branch.
Older snapshots and forks may not receive patches.

## Reporting a vulnerability

Please do **not** open public issues for suspected vulnerabilities.

Preferred path:

1. Open a private security advisory in GitHub (if enabled), or
2. Contact project maintainers through a private channel.

Include:

- clear description of the issue,
- reproduction steps,
- affected area (`frontend`, `backend`, infra/docs),
- potential impact.

We will acknowledge reports as soon as possible and coordinate disclosure after a fix is ready.

## Responsible disclosure expectations

- Give maintainers reasonable time to investigate and patch.
- Avoid public disclosure before mitigation is available.
- Do not exploit vulnerabilities beyond what is needed to prove impact.

## Secrets and data handling notes

- Never commit real keys/tokens (`.env`, API keys, admin credentials).
- Treat chat/ticket-derived exports as potentially sensitive unless sanitized.
- Privacy, retention, and EU-oriented product notes: [`docs/gdpr_data_retention.md`](docs/gdpr_data_retention.md) (use your organization’s privacy contact for data-subject requests; this repo’s security reporting path above is for **vulnerabilities**, not routine GDPR inquiries).
- Validate publish safety before release:
  - `docs/github_publish_checklist.md`
  - `backend/security_prepush_check.py`
