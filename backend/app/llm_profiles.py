"""Resolve OpenAI-compatible LLM endpoints from admin profiles or env defaults."""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    EMBED_MODEL,
    LLM_ANALYZER_MODEL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBED_API_KEY,
)
from .database import (
    fetch_llm_profile_row_for_resolve,
    get_llm_task_default_profile_id,
)
from .llm_crypto import resolve_profile_api_key


@dataclass(frozen=True)
class ResolvedLlmProfile:
    api_key: str
    base_url: str
    default_model: str
    timeout_seconds: float | None = None


def _fallback_for_task(task: str) -> ResolvedLlmProfile:
    t = (task or "chat").strip().lower()
    if t == "embed":
        key = NVIDIA_EMBED_API_KEY or NVIDIA_API_KEY
        return ResolvedLlmProfile(
            api_key=key,
            base_url=NVIDIA_BASE_URL,
            default_model=EMBED_MODEL,
            timeout_seconds=float(LLM_TIMEOUT_SECONDS),
        )
    if t in {"analyzer", "analyzer_repair", "consolidator", "replay"}:
        return ResolvedLlmProfile(
            api_key=NVIDIA_API_KEY,
            base_url=NVIDIA_BASE_URL,
            default_model=LLM_ANALYZER_MODEL,
            timeout_seconds=float(LLM_TIMEOUT_SECONDS),
        )
    return ResolvedLlmProfile(
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        default_model=LLM_MODEL,
        timeout_seconds=float(LLM_TIMEOUT_SECONDS),
    )


def resolve_llm_profile_for_task(
    task: str,
    *,
    profile_id: int | None = None,
) -> ResolvedLlmProfile:
    """Pick credentials: explicit profile_id, else task default row, else process env."""
    pid = profile_id
    if pid is None:
        tid = get_llm_task_default_profile_id(task)
        if tid is not None:
            pid = tid
    if pid is None:
        return _fallback_for_task(task)

    row = fetch_llm_profile_row_for_resolve(int(pid))
    if not row:
        return _fallback_for_task(task)

    key = resolve_profile_api_key(
        api_key_encrypted=row["api_key_encrypted"],
        env_alias=row["env_alias"],
    )
    if not key:
        return _fallback_for_task(task)

    return ResolvedLlmProfile(
        api_key=key,
        base_url=str(row["base_url"] or "").strip() or NVIDIA_BASE_URL,
        default_model=str(row["default_model"] or "").strip() or LLM_MODEL,
        timeout_seconds=float(LLM_TIMEOUT_SECONDS),
    )
