"""Optional Fernet encryption for LLM profile API keys stored in SQLite.

Phase 2 hardening:
- The Fernet key is derived from ``LLM_PROFILES_SECRET`` *and* a per-database
  salt stored in ``meta.db_salt`` via PBKDF2-HMAC-SHA256 (200_000 rounds).
  This prevents two deployments using the same secret from sharing keys, and
  raises the cost of brute-forcing the secret if a SQLite snapshot leaks.
- Inline encrypted API keys: set ``LLM_PROFILES_SECRET`` (then allowed by default), or
  ``ALLOW_INLINE_LLM_KEYS=true``. Use ``ALLOW_INLINE_LLM_KEYS=false`` to force
  ``env_alias``-only even when a secret is configured.

The salt is only read once per process (``_resolve_salt_once``); the derived
Fernet instance is cached. If migrations have not yet seeded ``meta.db_salt``
the encryption layer degrades gracefully and acts as if no secret were set.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from .config import LLM_PROFILES_SECRET

_PBKDF2_ITERATIONS = 200_000
_fernet = None
_resolved_salt: Optional[bytes] = None


def _resolve_salt_once() -> Optional[bytes]:
    """Read ``meta.db_salt`` exactly once per process.

    Imported lazily to avoid a circular ``llm_crypto`` <-> ``database`` import.
    """
    global _resolved_salt
    if _resolved_salt is not None:
        return _resolved_salt
    try:
        from .database import get_meta

        raw = (get_meta("db_salt") or "").strip()
    except Exception:
        raw = ""
    if not raw:
        return None
    _resolved_salt = raw.encode("utf-8")
    return _resolved_salt


def _fernet_instance():
    """Build (and cache) a Fernet instance keyed by PBKDF2(secret, db_salt).

    Returns ``None`` if either the secret or the per-DB salt is missing, or if
    the ``cryptography`` package is not installed.
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    secret = LLM_PROFILES_SECRET.strip()
    if not secret:
        return None
    salt = _resolve_salt_once()
    if not salt:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:  # pragma: no cover
        return None
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )
    key = base64.urlsafe_b64encode(derived)
    _fernet = Fernet(key)
    return _fernet


def reset_for_tests() -> None:
    """Drop cached Fernet + salt so a unit test can swap the secret/salt."""
    global _fernet, _resolved_salt
    _fernet = None
    _resolved_salt = None


def encrypt_secret_optional(plain: str) -> str | None:
    f = _fernet_instance()
    if not f:
        raise RuntimeError(
            "LLM_PROFILES_SECRET (or db_salt) not set; cannot store encrypted API key"
        )
    return f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret_optional(blob: str | None) -> str | None:
    if not blob:
        return None
    f = _fernet_instance()
    if not f:
        return None
    try:
        return f.decrypt(blob.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def resolve_profile_api_key(
    *,
    api_key_encrypted: str | None,
    env_alias: str | None,
) -> str | None:
    if env_alias:
        return os.getenv(env_alias.strip(), "") or None
    return decrypt_secret_optional(api_key_encrypted)
