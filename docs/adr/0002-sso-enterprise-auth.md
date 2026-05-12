# ADR 0002: Enterprise SSO / OIDC (roadmap vs implemented auth)

## Status

Accepted: **username/password + cookie sessions** is what the product implements today; **OIDC / SAML SSO** is **roadmap**, not implemented in this repository.

## Context

- Authentication today: `users` table with password hash, session rows, HTTP-only cookie (`AUTH_SESSION_COOKIE`), TTL `AUTH_SESSION_TTL_HOURS` (see [`backend/app/database.py`](../../backend/app/database.py), [`backend/app/main.py`](../../backend/app/main.py)).
- FM software sold into organizations often expects **SSO** (OpenID Connect with Entra ID/Okta/Google Workspace, or SAML via an IdP).

## Decision

- **Shipped path:** Continue supporting **local accounts** and session cookies for development and deployments that do not use an IdP.
- **Roadmap:** Add **OIDC** (primary integration target) behind configuration; SAML may be delegated to an OIDC bridge or a later phase.

## Integration points (for a future implementation)

1. **FastAPI middleware or router dependency** that runs **before** route handlers, exchanges the OIDC authorization code (or validates bearer tokens), and resolves an identity.
2. **User mapping:** Map IdP `sub` (and optional email) to a row in `users` (JIT provisioning) or to a separate `external_identities` table keyed by `user_id`.
3. **Session compatibility:** Either (a) issue the same **session cookie** shape the app already expects after OIDC login, or (b) introduce a parallel **bearer** path—both require updating `get_session` / `Depends(_require_auth)` / `_require_admin` consistently.
4. **Security:** PKCE for public clients, state/nonce validation, HTTPS-only cookies in production (`AUTH_COOKIE_SECURE`), short-lived access tokens if using API tokens, clear logout (IdP + local session).

No SSO code ships with this ADR; it documents **where** the seam is so future work does not fight the existing session model.

## Related

- [`docs/README_developers.md`](../README_developers.md) — local setup and API overview.
