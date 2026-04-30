from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import AsyncIterator, Iterator

from openai import AsyncOpenAI, OpenAI

from .config import (
    EMBED_MODEL,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBED_API_KEY,
    NVIDIA_RPM_BUDGET,
)


_log = logging.getLogger("fm.llm")

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
def _chat_client(timeout: float | None = None, max_retries: int | None = None) -> OpenAI:
    kwargs: dict = {
        "api_key": NVIDIA_API_KEY,
        "base_url": NVIDIA_BASE_URL,
        "timeout": timeout if timeout is not None else float(LLM_TIMEOUT_SECONDS),
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return OpenAI(**kwargs)


def _chat_client_async(timeout: float | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        timeout=timeout if timeout is not None else float(LLM_TIMEOUT_SECONDS),
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
    temperature: float = 0.2,
    timeout: float | None = None,
    max_retries: int | None = None,
    *,
    model: str | None = None,
) -> str:
    _acquire_rpm_slot()
    client = _chat_client(timeout=timeout, max_retries=max_retries)
    completion = client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    return completion.choices[0].message.content or ""


def chat_with_health_timeout(messages: list[dict], temperature: float = 0.0) -> str:
    """Sync helper used by /health/llm probe; uses LLM_HEALTH_TIMEOUT_SECONDS and
    disables retries so monitors don't hang past the configured budget."""
    return chat(
        messages,
        temperature=temperature,
        timeout=float(LLM_HEALTH_TIMEOUT_SECONDS),
        max_retries=0,
    )


def chat_stream(messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
    _acquire_rpm_slot()
    client = _chat_client()
    stream = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
        stream=True,
    )
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
    temperature: float = 0.2,
    *,
    model: str | None = None,
) -> str:
    await _acquire_rpm_slot_async()
    client = _chat_client_async()
    completion = await client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    return completion.choices[0].message.content or ""


async def achat_stream(messages: list[dict], temperature: float = 0.2) -> AsyncIterator[str]:
    await _acquire_rpm_slot_async()
    client = _chat_client_async()
    stream = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    _acquire_rpm_slot()
    client = _embed_client()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
        extra_body={"input_type": input_type},
    )
    return [item.embedding for item in response.data]
