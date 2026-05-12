from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, AsyncIterator, Iterator

from openai import APIStatusError, AsyncOpenAI, OpenAI

from .llm_profiles import ResolvedLlmProfile
from .config import (
    EMBED_MODEL,
    LLM_BASE_URL,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    NVIDIA_429_RETRY_ATTEMPTS,
    NVIDIA_429_RETRY_BASE_SECONDS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBED_API_KEY,
    NVIDIA_RPM_BUDGET,
)


_log = logging.getLogger("fm.llm")


def _moonshot_k2_model_prefixes() -> tuple[str, ...]:
    return ("kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking")


def _is_moonshot_k2_sampling_model(resolved: ResolvedLlmProfile | None, model: str) -> bool:
    """Kimi K2.5/K2.6 (+ thinking SKU): Moonshot pairs mode with a fixed temperature."""
    if resolved:
        base = str(resolved.base_url or "").strip()
    else:
        base = str(NVIDIA_BASE_URL or LLM_BASE_URL or "").strip()
    if "moonshot" not in base.lower():
        return False
    mid = (model or "").strip().lower()
    return any(mid == p or mid.startswith(p + "-") for p in _moonshot_k2_model_prefixes())


def _moonshot_k2_thinking_enabled(extra_body: dict[str, Any] | None) -> bool:
    """True = Thinking mode (temperature 1.0); False = Instant (0.6).

    Hosted ``api.moonshot.ai`` uses OpenAPI field ``thinking: {type: enabled|disabled}``.
    ``chat_template_kwargs`` (vLLM-style) is honored only when mapping into ``thinking``
    in :func:`_final_chat_extra_body` — it is not sent to Moonshot as-is.
    """
    if not extra_body:
        return True
    legacy = extra_body.get("thinking")
    if isinstance(legacy, dict):
        t = legacy.get("type")
        if t == "enabled":
            return True
        if t == "disabled":
            return False
    ctk = extra_body.get("chat_template_kwargs")
    if isinstance(ctk, dict) and "thinking" in ctk:
        return bool(ctk.get("thinking"))
    return True


def _final_chat_extra_body(
    resolved: ResolvedLlmProfile | None,
    model: str,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge vendor ``extra_body``. For Moonshot Kimi K2.5/K2.6 we default to **Instant**
    via native ``thinking: {type: disabled}`` so the API accepts ``temperature=0.6``;
    ``chat_template_kwargs.thinking`` is translated into that field then dropped
    (Moonshot ignores ``chat_template_kwargs``, which would leave Thinking on and
    force ``temperature=1`` only). Use ``thinking: {type: enabled}`` for Thinking.
    """
    if resolved:
        base = str(resolved.base_url or "").strip()
    else:
        base = str(NVIDIA_BASE_URL or LLM_BASE_URL or "").strip()
    mid = (model or "").strip().lower()
    if "moonshot" not in base.lower():
        return dict(extra_body) if extra_body else None
    if not _is_moonshot_k2_sampling_model(resolved, mid):
        return dict(extra_body) if extra_body else None

    merged = dict(extra_body or {})
    native = merged.get("thinking")
    if isinstance(native, dict) and native.get("type") in ("enabled", "disabled"):
        merged.pop("chat_template_kwargs", None)
        return merged

    ctk_in = merged.get("chat_template_kwargs")
    ctk: dict[str, Any] = dict(ctk_in) if isinstance(ctk_in, dict) else {}
    if "thinking" in ctk:
        merged["thinking"] = {
            "type": "enabled" if bool(ctk.get("thinking")) else "disabled"
        }
    else:
        merged["thinking"] = {"type": "disabled"}
    merged.pop("chat_template_kwargs", None)
    return merged


def _effective_chat_temperature(
    resolved: ResolvedLlmProfile | None,
    requested: float,
    *,
    model: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> float:
    """Non-Moonshot: use ``requested``. Moonshot K2.5/K2.6: Thinking → 1.0, Instant → 0.6."""
    if resolved:
        base = str(resolved.base_url or "").strip()
        mid = (model or resolved.default_model or "").strip().lower()
    else:
        base = str(NVIDIA_BASE_URL or LLM_BASE_URL or "").strip()
        mid = (model or LLM_MODEL or "").strip().lower()
    if "moonshot" not in base.lower():
        return requested
    if not _is_moonshot_k2_sampling_model(resolved, mid):
        return 1.0
    return 1.0 if _moonshot_k2_thinking_enabled(extra_body) else 0.6


# ---------------------------------------------------------------------------
# Global NVIDIA RPM token bucket (shared by chat, embed, analyzer, eval-runner)
# ---------------------------------------------------------------------------
# We track wall-clock timestamps of recent requests inside a single 60s window.
# When the window is full, callers wait for the oldest slot to expire.
_rpm_lock = threading.Lock()
_rpm_window: list[float] = []


def _prune_window(now: float) -> None:
    """Drop timestamps older than 60s. Caller must hold _rpm_lock."""
    cutoff = now - 60.0
    while _rpm_window and _rpm_window[0] < cutoff:
        _rpm_window.pop(0)


def _acquire_rpm_slot(timeout: float = 30.0) -> None:
    """Block (sync) until a slot is available or `timeout` seconds elapsed."""
    deadline = time.monotonic() + timeout
    while True:
        now = time.time()
        with _rpm_lock:
            _prune_window(now)
            if len(_rpm_window) < NVIDIA_RPM_BUDGET:
                _rpm_window.append(now)
                return
            # Wait until the oldest entry leaves the window.
            wait = 60.0 - (now - _rpm_window[0]) + 0.05
        if time.monotonic() + wait > deadline:
            raise RuntimeError(
                f"NVIDIA RPM budget exhausted (>{NVIDIA_RPM_BUDGET}/min); please retry shortly"
            )
        time.sleep(min(wait, 1.0))


async def _acquire_rpm_slot_async(timeout: float = 30.0) -> None:
    """Async variant: same semantics, uses asyncio.sleep so the event loop stays free."""
    deadline = time.monotonic() + timeout
    while True:
        now = time.time()
        with _rpm_lock:
            _prune_window(now)
            if len(_rpm_window) < NVIDIA_RPM_BUDGET:
                _rpm_window.append(now)
                return
            wait = 60.0 - (now - _rpm_window[0]) + 0.05
        if time.monotonic() + wait > deadline:
            raise RuntimeError(
                f"NVIDIA RPM budget exhausted (>{NVIDIA_RPM_BUDGET}/min); please retry shortly"
            )
        await asyncio.sleep(min(wait, 1.0))


def rpm_status() -> dict:
    """Diagnostic helper for /health and tests."""
    with _rpm_lock:
        _prune_window(time.time())
        used = len(_rpm_window)
    return {"budget": NVIDIA_RPM_BUDGET, "used_last_60s": used}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
def _chat_client(
    timeout: float | None = None,
    max_retries: int | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAI:
    kwargs: dict = {
        "api_key": api_key or NVIDIA_API_KEY,
        "base_url": base_url or NVIDIA_BASE_URL,
        "timeout": timeout if timeout is not None else float(LLM_TIMEOUT_SECONDS),
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return OpenAI(**kwargs)


def _chat_client_async(
    timeout: float | None = None,
    *,
    max_retries: int = 2,
    api_key: str | None = None,
    base_url: str | None = None,
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key or NVIDIA_API_KEY,
        base_url=base_url or NVIDIA_BASE_URL,
        timeout=timeout if timeout is not None else float(LLM_TIMEOUT_SECONDS),
        max_retries=max_retries,
    )


def _embed_client() -> OpenAI:
    return OpenAI(
        api_key=NVIDIA_EMBED_API_KEY,
        base_url=NVIDIA_BASE_URL,
        timeout=float(LLM_TIMEOUT_SECONDS),
    )


# ---------------------------------------------------------------------------
# Sync API (chat / embed)
# ---------------------------------------------------------------------------
def chat(
    messages: list[dict],
    temperature: float = LLM_TEMPERATURE,
    timeout: float | None = None,
    max_retries: int | None = None,
    *,
    model: str | None = None,
    resolved: ResolvedLlmProfile | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    _acquire_rpm_slot()
    eff_timeout = (
        float(resolved.timeout_seconds)
        if resolved and resolved.timeout_seconds is not None
        else timeout
    )
    client = _chat_client(
        timeout=eff_timeout,
        max_retries=max_retries,
        api_key=resolved.api_key if resolved else None,
        base_url=resolved.base_url if resolved else None,
    )
    eff_model = model or (resolved.default_model if resolved else None) or LLM_MODEL
    eb = _final_chat_extra_body(resolved, eff_model, extra_body)
    eff_temp = _effective_chat_temperature(
        resolved, temperature, model=eff_model, extra_body=eb
    )
    kwargs: dict[str, Any] = {
        "model": eff_model,
        "messages": messages,
        "temperature": eff_temp,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if eb:
        kwargs["extra_body"] = eb
    if _is_moonshot_k2_sampling_model(resolved, eff_model):
        kwargs.setdefault("top_p", 0.95)
    completion = client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content or ""


def chat_with_health_timeout(messages: list[dict], temperature: float = LLM_TEMPERATURE) -> str:
    """Sync helper used by /health/llm probe; uses LLM_HEALTH_TIMEOUT_SECONDS and
    disables retries so monitors don't hang past the configured budget."""
    return chat(
        messages,
        temperature=temperature,
        timeout=float(LLM_HEALTH_TIMEOUT_SECONDS),
        max_retries=0,
    )


def chat_stream(
    messages: list[dict],
    temperature: float = LLM_TEMPERATURE,
    *,
    resolved: ResolvedLlmProfile | None = None,
    extra_body: dict[str, Any] | None = None,
) -> Iterator[str]:
    _acquire_rpm_slot()
    client = _chat_client(
        api_key=resolved.api_key if resolved else None,
        base_url=resolved.base_url if resolved else None,
    )
    eff_model = (resolved.default_model if resolved else None) or LLM_MODEL
    eb = _final_chat_extra_body(resolved, eff_model, extra_body)
    eff_temp = _effective_chat_temperature(
        resolved, temperature, model=eff_model, extra_body=eb
    )
    kwargs: dict[str, Any] = {
        "model": eff_model,
        "messages": messages,
        "temperature": eff_temp,
        "max_tokens": LLM_MAX_TOKENS,
        "stream": True,
    }
    if eb:
        kwargs["extra_body"] = eb
    if _is_moonshot_k2_sampling_model(resolved, eff_model):
        kwargs.setdefault("top_p", 0.95)
    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


# ---------------------------------------------------------------------------
# Async API (used by api_chat / api_chat_stream / prompt_analyzer)
# ---------------------------------------------------------------------------
async def achat(
    messages: list[dict],
    temperature: float = LLM_TEMPERATURE,
    *,
    model: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    resolved: ResolvedLlmProfile | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """Chat completion. Retries on NVIDIA HTTP 429 with exponential backoff.

    Local RPM slot acquisition runs before each attempt so we stay under our
    client-side budget; NVIDIA can still 429 when quotas differ — then we wait
    and retry up to ``NVIDIA_429_RETRY_ATTEMPTS`` times.
    """
    eff_timeout = (
        float(resolved.timeout_seconds)
        if resolved and resolved.timeout_seconds is not None
        else (float(LLM_TIMEOUT_SECONDS) if timeout is None else float(timeout))
    )
    to = eff_timeout
    mr = 2 if max_retries is None else int(max_retries)
    mt = LLM_MAX_TOKENS if max_tokens is None else max(1, int(max_tokens))
    eff_model = model or (resolved.default_model if resolved else None) or LLM_MODEL
    eb = _final_chat_extra_body(resolved, eff_model, extra_body)
    eff_temp = _effective_chat_temperature(
        resolved, temperature, model=eff_model, extra_body=eb
    )
    kwargs: dict[str, Any] = {
        "model": eff_model,
        "messages": messages,
        "temperature": eff_temp,
        "max_tokens": mt,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if eb:
        kwargs["extra_body"] = eb
    if _is_moonshot_k2_sampling_model(resolved, eff_model):
        kwargs.setdefault("top_p", 0.95)

    last_exc: BaseException | None = None
    max_429 = max(0, int(NVIDIA_429_RETRY_ATTEMPTS))
    base_wait = float(NVIDIA_429_RETRY_BASE_SECONDS)

    for attempt in range(max_429 + 1):
        await _acquire_rpm_slot_async(timeout=120.0)
        client = _chat_client_async(
            timeout=to,
            max_retries=mr,
            api_key=resolved.api_key if resolved else None,
            base_url=resolved.base_url if resolved else None,
        )
        try:
            completion = await client.chat.completions.create(**kwargs)
            return completion.choices[0].message.content or ""
        except APIStatusError as exc:
            last_exc = exc
            if exc.status_code == 429 and attempt < max_429:
                wait = min(90.0, base_wait * (2**attempt))
                _log.warning(
                    "achat: NVIDIA 429 Too Many Requests; sleeping %.1fs (retry %s/%s)",
                    wait,
                    attempt + 1,
                    max_429,
                )
                await asyncio.sleep(wait)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("achat: exhausted retries without response")


async def achat_stream(
    messages: list[dict],
    temperature: float = LLM_TEMPERATURE,
    *,
    max_tokens: int | None = None,
    resolved: ResolvedLlmProfile | None = None,
    extra_body: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    await _acquire_rpm_slot_async()
    client = _chat_client_async(
        api_key=resolved.api_key if resolved else None,
        base_url=resolved.base_url if resolved else None,
    )
    eff_model = (resolved.default_model if resolved else None) or LLM_MODEL
    mt = LLM_MAX_TOKENS if max_tokens is None else max(1, int(max_tokens))
    eb = _final_chat_extra_body(resolved, eff_model, extra_body)
    eff_temp = _effective_chat_temperature(
        resolved, temperature, model=eff_model, extra_body=eb
    )
    skwargs: dict[str, Any] = {
        "model": eff_model,
        "messages": messages,
        "temperature": eff_temp,
        "max_tokens": mt,
        "stream": True,
    }
    if eb:
        skwargs["extra_body"] = eb
    if _is_moonshot_k2_sampling_model(resolved, eff_model):
        skwargs.setdefault("top_p", 0.95)
    stream = await client.chat.completions.create(**skwargs)
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


async def aembed_resolved(
    texts: list[str],
    *,
    resolved: ResolvedLlmProfile,
    model: str | None = None,
    input_type: str = "passage",
) -> list[list[float]]:
    """Embeddings using the same base URL and API key as ``resolved`` (RAG-style check).

    NVIDIA OpenAI-compatible hosts often require ``input_type`` in ``extra_body``;
    other vendors typically omit it.
    """
    m = (model or EMBED_MODEL).strip() or EMBED_MODEL
    to = float(
        resolved.timeout_seconds
        if resolved.timeout_seconds is not None
        else LLM_TIMEOUT_SECONDS
    )
    await _acquire_rpm_slot_async(timeout=120.0)
    client = _chat_client_async(
        timeout=to,
        max_retries=0,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
    )
    base = (resolved.base_url or "").lower()
    use_nv_extra = "nvidia.com" in base or "integrate.api.nvidia" in base
    kwargs: dict[str, Any] = {"model": m, "input": texts}
    if use_nv_extra:
        kwargs["extra_body"] = {"input_type": input_type}
    response = await client.embeddings.create(**kwargs)
    return [item.embedding for item in response.data]


def embed_resolved(
    texts: list[str],
    *,
    resolved: ResolvedLlmProfile,
    model: str | None = None,
    input_type: str = "passage",
) -> list[list[float]]:
    """Sync embeddings using ``resolved`` host/key (parity with :func:`aembed_resolved`)."""
    m = (model or EMBED_MODEL).strip() or EMBED_MODEL
    to = float(
        resolved.timeout_seconds
        if resolved.timeout_seconds is not None
        else LLM_TIMEOUT_SECONDS
    )
    _acquire_rpm_slot()
    client = _chat_client(
        timeout=to,
        max_retries=0,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
    )
    base = (resolved.base_url or "").lower()
    use_nv_extra = "nvidia.com" in base or "integrate.api.nvidia" in base
    kwargs: dict[str, Any] = {"model": m, "input": texts}
    if use_nv_extra:
        kwargs["extra_body"] = {"input_type": input_type}
    response = client.embeddings.create(**kwargs)
    return [item.embedding for item in response.data]


def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    _acquire_rpm_slot()
    client = _embed_client()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
        extra_body={"input_type": input_type},
    )
    return [item.embedding for item in response.data]
