"""Multi-step LLM profile checks for admin diagnostics (chat, JSON, stream, embed)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from .config import EMBED_MODEL, LLM_TIMEOUT_SECONDS
from .database import get_llm_model_profile
from .llm import achat, achat_stream, aembed_resolved
from .llm_profiles import ResolvedLlmProfile, resolve_llm_profile_for_task


def _step(
    step_id: str,
    ok: bool,
    ms: float,
    detail: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": step_id,
        "ok": ok,
        "ms": round(ms, 1),
        "detail": detail[:500],
    }
    if extra:
        out["extra"] = extra
    return out


async def run_profile_diagnostic(profile_id: int) -> dict[str, Any]:
    """Run several checks against one resolved profile; return a structured report."""
    pid = int(profile_id)
    if not get_llm_model_profile(pid):
        return {"ok": False, "error": "Profile not found", "steps": []}

    resolved: ResolvedLlmProfile = resolve_llm_profile_for_task(
        "chat", profile_id=pid
    )
    per_call_timeout = min(45.0, float(LLM_TIMEOUT_SECONDS))

    steps: list[dict[str, Any]] = []
    snippet = ""

    # 1) Simple completion — some models (e.g. Kimi) need a larger max_tokens budget
    # before any visible text appears; max_tokens=8 can yield an empty string.
    try:
        t0 = time.perf_counter()
        reply = await asyncio.wait_for(
            achat(
                [{"role": "user", "content": "Reply with exactly: ok"}],
                max_tokens=256,
                timeout=per_call_timeout,
                max_retries=0,
                resolved=resolved,
            ),
            timeout=per_call_timeout + 5.0,
        )
        ms = (time.perf_counter() - t0) * 1000.0
        text = (reply or "").strip()
        if not text:
            reply2 = await asyncio.wait_for(
                achat(
                    [{"role": "user", "content": "Answer with one word only: ok"}],
                    max_tokens=256,
                    timeout=per_call_timeout,
                    max_retries=0,
                    resolved=resolved,
                ),
                timeout=per_call_timeout + 5.0,
            )
            ms = (time.perf_counter() - t0) * 1000.0
            text = (reply2 or "").strip()
            reply = reply2
        snippet = text[:80]
        ok_simple = bool(text) and ("ok" in text.lower())
        steps.append(
            _step(
                "chat_simple",
                ok_simple,
                ms,
                f"reply: {snippet!r}" if text else "reply: (empty after retry)",
            )
        )
    except Exception as exc:
        ms = 0.0
        steps.append(
            _step("chat_simple", False, ms, f"error: {exc}", extra={"error": str(exc)})
        )

    # 2) Structured JSON (classifier-style)
    try:
        t0 = time.perf_counter()
        raw = await asyncio.wait_for(
            achat(
                [
                    {
                        "role": "user",
                        "content": (
                            "Output ONLY a single JSON object, no markdown, no other text. "
                            'Schema: {"probe": true, "n": 1}'
                        ),
                    }
                ],
                max_tokens=512,
                timeout=per_call_timeout,
                max_retries=0,
                resolved=resolved,
            ),
            timeout=per_call_timeout + 5.0,
        )
        ms = (time.perf_counter() - t0) * 1000.0
        text = (raw or "").strip()
        # strip optional ```json fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if len(lines) > 2 else lines).strip()
        parsed = json.loads(text)
        ok = isinstance(parsed, dict) and parsed.get("probe") is True
        steps.append(
            _step(
                "chat_json",
                ok,
                ms,
                "parsed JSON with probe=true" if ok else f"unexpected JSON: {text[:120]!r}",
            )
        )
    except Exception as exc:
        ms = 0.0
        steps.append(
            _step("chat_json", False, ms, f"error: {exc}", extra={"error": str(exc)})
        )

    # 3) Streaming sample — some hosts stream few/no text deltas; fall back to one sync call.
    try:
        t0 = time.perf_counter()
        buf: list[str] = []

        async def _collect() -> None:
            async for chunk in achat_stream(
                [{"role": "user", "content": "Say hello in one short phrase."}],
                max_tokens=256,
                resolved=resolved,
            ):
                buf.append(chunk)
                if sum(len(x) for x in buf) >= 12:
                    break

        await asyncio.wait_for(_collect(), timeout=per_call_timeout + 5.0)
        ms = (time.perf_counter() - t0) * 1000.0
        joined = "".join(buf).strip()
        if not joined:
            fb = await asyncio.wait_for(
                achat(
                    [{"role": "user", "content": "Say hello in one short phrase."}],
                    max_tokens=128,
                    timeout=per_call_timeout,
                    max_retries=0,
                    resolved=resolved,
                ),
                timeout=per_call_timeout + 5.0,
            )
            ms = (time.perf_counter() - t0) * 1000.0
            joined = (fb or "").strip()
            steps.append(
                _step(
                    "chat_stream",
                    len(joined) > 0,
                    ms,
                    (
                        f"stream had 0 text chunks; non-stream ok ({len(joined)} chars): "
                        f"{joined[:60]!r}{'…' if len(joined) > 60 else ''}"
                    ),
                )
            )
        else:
            steps.append(
                _step(
                    "chat_stream",
                    True,
                    ms,
                    f"received {len(joined)} chars: {joined[:60]!r}{'…' if len(joined) > 60 else ''}",
                )
            )
    except Exception as exc:
        ms = 0.0
        steps.append(
            _step("chat_stream", False, ms, f"error: {exc}", extra={"error": str(exc)})
        )

    # 4) Embeddings (RAG-style; same host/key as profile). Moonshot chat keys often
    # cannot call NVIDIA embed models — skip instead of a misleading 403.
    if "moonshot" in (resolved.base_url or "").lower():
        steps.append(
            _step(
                "embeddings",
                True,
                0.0,
                "skipped — Moonshot does not use your RAG EMBED_MODEL here; document "
                "indexing still uses the embed host/model from backend .env (LLM_EMBED_API_KEY / EMBED_MODEL).",
                extra={"skipped": True},
            )
        )
    else:
        try:
            t0 = time.perf_counter()
            vecs = await asyncio.wait_for(
                aembed_resolved(["fm profile diagnostic"], resolved=resolved),
                timeout=per_call_timeout + 5.0,
            )
            ms = (time.perf_counter() - t0) * 1000.0
            dim = len(vecs[0]) if vecs and vecs[0] else 0
            steps.append(
                _step(
                    "embeddings",
                    dim > 0,
                    ms,
                    f"model={EMBED_MODEL!r}, vector_dim={dim}",
                    extra={"embed_model": EMBED_MODEL},
                )
            )
        except Exception as exc:
            ms = 0.0
            steps.append(
                _step(
                    "embeddings",
                    False,
                    ms,
                    f"error: {exc}",
                    extra={"error": str(exc), "embed_model": EMBED_MODEL},
                )
            )

    passed = sum(1 for s in steps if s.get("ok"))
    total_ms = sum(float(s.get("ms") or 0) for s in steps)
    summary = f"{passed}/{len(steps)} checks passed in {total_ms:.0f} ms total"

    return {
        "ok": passed == len(steps) and len(steps) > 0,
        "mode": "full",
        "profile_id": pid,
        "base_url": resolved.base_url,
        "model": resolved.default_model,
        "steps": steps,
        "summary": summary,
        "snippet": snippet,
        "embed_model": EMBED_MODEL,
    }
