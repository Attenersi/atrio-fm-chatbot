from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uvicorn
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from openai import APIStatusError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from .chat_injection_guard import (
    llm_classify_injection,
    regex_hits_injection,
    synthetic_injection_blocked_payload,
)
from .chat_output_guard import apply_output_guardrails
from .classifier import fallback_response, parse_llm_json
from .config import (
    ALLOW_INLINE_LLM_KEYS,
    ANALYZER_CACHE_TTL_HOURS,
    ANALYZER_DEADLINE_SECONDS,
    ANALYZER_DISCARD_FILTER_DB_LIMIT,
    ANALYZER_DISCARD_PROMPT_LIMIT,
    ANALYZER_LLM_TIMEOUT_SECONDS,
    ANALYZER_MAX_LLM_ATTEMPTS,
    ANALYZER_REPAIR_BUDGET_SECONDS,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    AUTH_SESSION_COOKIE,
    AUTH_SESSION_TTL_HOURS,
    CACHE_SWEEP_INTERVAL_SECONDS,
    CHROMA_DIR,
    CHAT_INJECTION_LLM_FILTER,
    CORS_ALLOW_ORIGIN_REGEX,
    DOCS_DIR,
    DOCS_SANITIZE_INSTRUCTION_LIKE,
    EMBED_MODEL,
    EVAL_BASELINE_MAX_AGE_HOURS,
    EVENT_LOG_KEEP_PER_KIND,
    INGEST_CHUNK_OVERLAP,
    INGEST_CHUNK_SIZE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_EMBED_API_KEY,
    LLM_HEALTH_TIMEOUT_SECONDS,
    LLM_MODEL,
    MAX_ACTIVE_OVERRIDES,
    OVERRIDE_MIN_CONFIDENCE,
    RATE_LIMIT_CHAT,
    RATE_LIMIT_EMBED,
    REPLAY_MAX_LLM_CALLS,
    MULTI_TICKET_PER_MESSAGE_ENABLED,
    TRAINING_DATA_AUTO_REFRESH,
    TRAINING_DATA_AUTO_REFRESH_SECONDS,
    TRAINING_DATA_DIR,
)
from .doc_extract import UPLOAD_ALLOWED_EXTENSIONS, extract_text_from_upload
from .doc_sanitize import sanitize_document_text
from . import mail as mail_notify
from .database import (
    apply_classification_override,
    authenticate_user,
    create_resolution_note,
    create_user_account,
    create_session,
    create_knowledge_gap,
    create_training_example,
    create_ticket,
    delete_session,
    get_knowledge_gap,
    get_knowledge_gaps,
    get_session,
    get_resolution_notes,
    get_ticket,
    get_tickets,
    get_classification_overrides,
    get_training_example,
    get_training_examples,
    get_user_by_id,
    init_db,
    list_active_chat_messages,
    list_users,
    cleanup_training_examples_and_candidates,
    compute_pending_cache_key,
    compute_review_signals_cache_key,
    covered_example_ids_from_active_overrides,
    consolidate_active_prompt_overrides,
    count_active_prompt_overrides,
    create_llm_model_profile,
    delete_meta,
    delete_llm_model_profile,
    get_llm_model_profile,
    get_llm_task_default_profile_id,
    list_llm_model_profiles,
    list_llm_task_defaults,
    list_question_bank_rows,
    question_bank_dedup_cache_tag,
    record_suggestion_affected_from_analysis_payload,
    set_llm_task_default,
    update_llm_model_profile,
    get_eval_run,
    get_prompt_analysis_cache,
    get_prompt_override,
    get_rag_system_prompt_head_override,
    list_eval_runs,
    list_pending_grouped,
    list_prompt_overrides,
    list_recent_suggestion_decisions,
    list_review_signals_for_analysis,
    mass_mark_all_edited_if_any_custom_reasoning,
    get_active_prompt_overrides,
    apply_prompt_override as db_apply_prompt_override,
    rollback_prompt_override as db_rollback_prompt_override,
    list_prompt_override_audit,
    record_prompt_override_audit,
    record_prompt_suggestion_decision,
    set_prompt_override_replay_summary,
    prune_training_examples_for_review_policy,
    put_prompt_analysis_cache,
    suppress_review_signals,
    vacuum_training_quality_caches,
    append_chat_exchange,
    start_new_chat_thread,
    ticket_stats,
    update_knowledge_gap,
    update_ticket_status,
    update_training_example_review,
    update_user_admin_fields,
    erase_user_chat_and_training_data,
    ALLOWED_CORRECTION_TYPES,
    TRAINING_EXPORT_MAX_IDS,
    export_training_examples_jsonl,
    backfill_training_examples_from_tickets,
    backfill_training_examples_from_test_results,
    bulk_update_training_examples_review,
    build_v1_dataset_view,
    export_v1_jsonl,
    export_v1_review_csv,
    rebuild_json_store_from_db,
    set_meta,
    set_rag_system_prompt_head_override,
    write_v1_dataset_files,
)
from .ingest import run_ingest
from .llm import achat, chat_with_health_timeout, embed
from .llm_profiles import resolve_llm_profile_for_task
from .rag import (
    RAG_TOP_K_META_KEY,
    agenerate,
    agenerate_stream,
    effective_rag_top_k,
    get_effective_system_prompt_head,
    rag_top_k_admin_detail,
    retrieve_with_sources,
)
from .prompt_rule_similarity import (
    filter_discarded_suggestions,
    filter_duplicate_suggestions,
    find_duplicate_rule,
)
from .training_quality_analysis_enrich import (
    enrich_analysis_payload_with_supporting_examples,
    enrich_prompt_override_rows,
)
from .request_context import (
    REQUEST_ID_HEADER,
    add_request_id_filters,
    normalize_request_id,
    request_id_var,
)
from . import rag_eval


_obs_log = logging.getLogger("fm.observability")
_tq_log = logging.getLogger("fm.training_quality")
add_request_id_filters("fm.observability", "fm.training_quality")


def _prompt_rule_fingerprint(system_prompt: str, active_overrides: list[dict]) -> str:
    import hashlib

    override_blob = "\n".join(
        str(o.get("approved_change", "") or "").strip() for o in active_overrides
    )
    blob = f"{system_prompt}\n---ACTIVE_OVERRIDES---\n{override_blob}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _base_system_prompt_template_fingerprint(template: str) -> str:
    """Hash of the system prompt template before ``.format`` (no user context)."""
    import hashlib

    return hashlib.sha256((template or "").encode("utf-8")).hexdigest()[:16]


def _normalize_hidden_entry(
    raw: dict[str, Any], reason: str, kind: str = "group"
) -> dict[str, Any]:
    """Lift one filter result into the unified ``hidden_suggestions`` shape."""
    return {
        "kind": str(raw.get("kind") or kind),
        "type": str(raw.get("type") or ""),
        "reason": reason,
        "suggested_change": str(raw.get("suggested_change") or "")[:600],
        "matched_text": str(
            raw.get("discarded_suggestion")
            or raw.get("matched_text")
            or raw.get("description")
            or ""
        )[:600],
        "match_type": str(raw.get("match_type") or ""),
        "score": raw.get("score"),
        "source": raw.get("source"),
        "affected_ids": [
            int(x) for x in (raw.get("affected_ids") or []) if isinstance(x, int)
        ],
        "decision_id": raw.get("decision_id"),
    }


def _finalize_analysis_response(
    payload: dict[str, Any],
    system_prompt: str,
    active_overrides: list[dict],
    discard_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply all hidden-suggestion filters and collapse them into one list.

    The legacy ``duplicate_matches`` / ``discarded_matches`` /
    ``question_claim_matches`` arrays are gone; the frontend reads a single
    ``hidden_suggestions`` array with ``reason`` / ``kind`` markers. The
    integer counters (``duplicate_suggestions_hidden`` etc.) stay so the
    dashboard headline still works.
    """
    from .database import get_question_bank_claimed_example_ids
    from .question_bank import filter_payload_by_claimed_examples

    hidden_suggestions: list[dict[str, Any]] = []

    claimed = get_question_bank_claimed_example_ids(active_overrides)
    after_qb = filter_payload_by_claimed_examples(payload, claimed)
    for raw in after_qb.get("question_claim_matches") or []:
        hidden_suggestions.append(
            _normalize_hidden_entry(
                raw,
                reason="question_bank_claimed",
                kind=str(raw.get("kind") or "group"),
            )
        )

    groups_after_qb = after_qb.get("groups") if isinstance(after_qb, dict) else []
    if not isinstance(groups_after_qb, list):
        groups_after_qb = []
    visible_groups, dup_hidden = filter_duplicate_suggestions(
        groups_after_qb, system_prompt, active_overrides
    )
    for raw in dup_hidden:
        hidden_suggestions.append(
            _normalize_hidden_entry(raw, reason="duplicate_rule")
        )

    visible_groups, discarded_hidden = filter_discarded_suggestions(
        visible_groups, discard_decisions
    )
    for raw in discarded_hidden:
        hidden_suggestions.append(
            _normalize_hidden_entry(raw, reason="reviewer_discarded")
        )

    return {
        **payload,
        "groups": visible_groups,
        "rag_suggestions": after_qb.get("rag_suggestions") or [],
        "duplicate_suggestions_hidden": len(dup_hidden),
        "discarded_suggestions_hidden": len(discarded_hidden),
        "question_claim_hidden": int(after_qb.get("question_claim_hidden") or 0),
        "hidden_suggestions": hidden_suggestions,
    }


def _rate_limit_key(request: Request) -> str:
    """Per-user limit when authenticated, per-IP otherwise. Avoids penalising
    everyone behind a shared NAT once a single user is signed in."""
    session_id = request.cookies.get(AUTH_SESSION_COOKIE)
    if session_id:
        try:
            session = get_session(session_id)
            if session and session.get("user_id"):
                return f"user:{int(session['user_id'])}"
        except Exception:
            _obs_log.exception("rate limit key lookup failed; falling back to IP")
    return get_remote_address(request)


_DATASET_REFRESH_THREAD_STARTED = False
_TQ_CACHE_SWEEP_TASK: asyncio.Task | None = None


def _should_enable_training_auto_refresh() -> bool:
    return str(TRAINING_DATA_AUTO_REFRESH).strip().lower() in {"1", "true", "yes", "on"}


def _start_training_dataset_scheduler() -> None:
    global _DATASET_REFRESH_THREAD_STARTED
    if _DATASET_REFRESH_THREAD_STARTED:
        return
    if not _should_enable_training_auto_refresh():
        return
    interval = max(15, int(TRAINING_DATA_AUTO_REFRESH_SECONDS or 60))

    def _runner() -> None:
        while True:
            try:
                write_v1_dataset_files(TRAINING_DATA_DIR)
            except Exception:
                _obs_log.exception("write_v1_dataset_files failed in background runner")
            time.sleep(interval)

    th = threading.Thread(target=_runner, name="training-dataset-refresh", daemon=True)
    th.start()
    _DATASET_REFRESH_THREAD_STARTED = True


def _start_training_quality_cache_sweep() -> None:
    """Periodically prune analyzer cache + event log so SQLite does not bloat.

    Runs on the FastAPI event loop. Best-effort: any failure is logged and the
    next tick still fires.
    """
    global _TQ_CACHE_SWEEP_TASK
    if _TQ_CACHE_SWEEP_TASK is not None and not _TQ_CACHE_SWEEP_TASK.done():
        return

    async def _loop() -> None:
        while True:
            try:
                stats = await asyncio.to_thread(
                    vacuum_training_quality_caches,
                    ttl_hours=ANALYZER_CACHE_TTL_HOURS,
                    keep_per_kind=EVENT_LOG_KEEP_PER_KIND,
                )
                if stats.get("deleted_cache_rows") or stats.get("deleted_event_rows"):
                    _tq_log.info(
                        "training-quality cache sweep deleted_cache=%d deleted_events=%d",
                        stats.get("deleted_cache_rows", 0),
                        stats.get("deleted_event_rows", 0),
                    )
            except Exception:
                _obs_log.exception("training-quality cache sweep failed")
            await asyncio.sleep(max(60, int(CACHE_SWEEP_INTERVAL_SECONDS)))

    try:
        loop = asyncio.get_running_loop()
        _TQ_CACHE_SWEEP_TASK = loop.create_task(_loop())
    except RuntimeError:
        # No running loop (should not happen during ASGI lifespan startup).
        _TQ_CACHE_SWEEP_TASK = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    _start_training_dataset_scheduler()
    _start_training_quality_cache_sweep()
    yield
    global _TQ_CACHE_SWEEP_TASK
    task = _TQ_CACHE_SWEEP_TASK
    _TQ_CACHE_SWEEP_TASK = None
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            _obs_log.exception("training-quality cache sweep task shutdown")


limiter = Limiter(key_func=_rate_limit_key)

app = FastAPI(title="FM Chatbot Backend", lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    incoming = request.headers.get(REQUEST_ID_HEADER)
    rid = normalize_request_id(incoming)
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
    finally:
        request_id_var.reset(token)


class ChatRequest(BaseModel):
    message: str
    # Server reads chat history from the DB via _history_from_active_chat;
    # this field is kept for backward compatibility (tests, old clients) and
    # is only consulted when the DB has no active thread for this user yet.
    history: list[dict[str, str]] = Field(default_factory=list)
    run_id: str = ""
    source_type: str = ""
    source_id: str = ""
    source_ref: str = ""


async def chat_request_with_merged_history(
    req: ChatRequest, user: dict, *, isolate_history: bool
) -> ChatRequest:
    """Return a copy of `req` with `history` filled. When isolate_history is True,
    history is always empty so batch eval matches CLI test runs (no DB thread)."""
    if isolate_history:
        return req.model_copy(update={"history": []})
    merged = await asyncio.to_thread(_history_from_active_chat, user, req.history)
    return req.model_copy(update={"history": merged})


async def run_chat_core(
    req: ChatRequest, user: dict, *, isolate_history: bool = False
) -> dict:
    """Shared non-streaming chat pipeline (RAG + LLM + finalize). Used by /api/chat
    and by admin RAG eval with isolate_history=True."""
    chat_req = await chat_request_with_merged_history(
        req, user, isolate_history=isolate_history
    )
    resolved = resolve_llm_profile_for_task("chat")
    context: list[str] = []
    sources: list[str] = []
    payload: dict

    if regex_hits_injection(chat_req.message):
        payload = synthetic_injection_blocked_payload("regex")
    elif CHAT_INJECTION_LLM_FILTER:
        inj = await llm_classify_injection(chat_req.message, resolved=resolved)
        if inj == "INJECTION":
            payload = synthetic_injection_blocked_payload("llm")
        else:
            context, sources = await asyncio.to_thread(
                retrieve_with_sources, chat_req.message, effective_rag_top_k()
            )
            raw_response = await agenerate(
                chat_req.message, context, chat_req.history, resolved=resolved
            )
            try:
                payload = parse_llm_json(raw_response)
            except Exception:
                payload = fallback_response(raw_response)
            payload = apply_output_guardrails(payload, chat_req.message)
            payload = _apply_fm_safety_net(payload, chat_req.message)
    else:
        context, sources = await asyncio.to_thread(
            retrieve_with_sources, chat_req.message, effective_rag_top_k()
        )
        raw_response = await agenerate(
            chat_req.message, context, chat_req.history, resolved=resolved
        )
        try:
            payload = parse_llm_json(raw_response)
        except Exception:
            payload = fallback_response(raw_response)
        payload = apply_output_guardrails(payload, chat_req.message)
        payload = _apply_fm_safety_net(payload, chat_req.message)

    return await asyncio.to_thread(
        _finalize_chat_payload, chat_req, payload, context, sources, user
    )


class EmbedRequest(BaseModel):
    texts: list[str]
    input_type: str = "passage"


class TicketStatusRequest(BaseModel):
    status: str


class ManualTicketCreateRequest(BaseModel):
    message: str
    issue_summary: str = "Manual ticket from chat"
    category: str = "General"
    priority: str = "NORMAL"
    department: str = "Facility Management"
    response: str = ""


class AdminDocCreateRequest(BaseModel):
    name: str
    content: str


class AdminDocUpdateRequest(BaseModel):
    content: str


class AdminRagSettingsPatchRequest(BaseModel):
    """``rag_top_k`` writes a SQLite meta override; ``clear_rag_top_k_override`` removes it."""

    rag_top_k: int | None = None
    clear_rag_top_k_override: bool = False


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AdminUserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    email: str | None = None


class AdminUserEraseChatTrainingRequest(BaseModel):
    """Body must repeat the target user's exact ``username`` to confirm erasure."""

    confirm_username: str


class KnowledgeGapUpdateRequest(BaseModel):
    status: str
    notes: str | None = None


class KnowledgeGapResolveRequest(BaseModel):
    doc_name: str
    category: str = "General"
    content: str
    mode: str = "append"  # append | overwrite
    auto_reindex: bool = True
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class AdminTrainingExampleUpdateRequest(BaseModel):
    correction_type: str
    ideal_output: dict | None = None
    human_notes: str | None = None
    context_used: list[str] | None = None
    reasoning: str | None = None


class AdminTrainingBulkReviewRequest(BaseModel):
    ids: list[int]
    human_notes: str | None = None
    reasoning: str | None = None
    correction_type: str | None = None


class AdminTrainingExamplesExportRequest(BaseModel):
    """Body for POST /api/admin/training-examples/export (filtered NDJSON)."""

    correction_types: list[str] = Field(
        default_factory=lambda: ["pending", "approved", "edited", "rejected"]
    )
    ids: list[int] | None = None
    id_min: int | None = None
    id_max: int | None = None
    created_after: str | None = None
    created_before: str | None = None
    include_actual_output: bool = False


class AdminV1BuildRequest(BaseModel):
    test_results_path: str = "test_results_full.json"
    output_dir: str = "data"


class AdminSystemPromptHeadPayload(BaseModel):
    """Body for PUT ``/api/admin/training-quality/system-prompt-head``.

    Empty or whitespace-only ``override_text`` removes the DB override and
    restores the built-in template from code.
    """

    override_text: str = ""


class ResolutionNoteCreateRequest(BaseModel):
    note: str
    added_by: str = ""
    parts_used: str = ""
    cost: float | None = None
    time_spent_minutes: int | None = None


class ClassificationOverrideCreateRequest(BaseModel):
    field_changed: str  # category | priority | department
    manager_value: str
    changed_by: str = ""


DOC_ALLOWED_EXTENSIONS = {".md", ".txt"}
FM_KEYWORDS = {
    "fm",
    "facility",
    "facilities",
    "building",
    "boiler",
    "hvac",
    "chiller",
    "cooling",
    "heating",
    "electrical",
    "breaker",
    "plumbing",
    "water",
    "drain",
    "safety",
    "fire",
    "evacuation",
    "access",
    "card",
    "parking",
    "maintenance",
    "generator",
    "pump",
    "valve",
}
AUTO_TICKET_QUERY_TYPES = {"SERVICE_REQUEST", "INCIDENT"}
ACTION_HINTS = {
    "fix",
    "repair",
    "check",
    "replace",
    "service",
}
INCIDENT_HINTS = {
    "leak",
    "alarm",
    "smell",
    "smells",
    "stench",
    "sewage",
    "odor",
    "odour",
    "problem",
    "issue",
    "broken",
    "smoke",
    "outage",
    "emergency",
}
STRUCTURAL_HINTS = {
    "sag",
    "sagging",
    "bulge",
    "bulging",
    "crack",
    "cracks",
    "tilt",
    "tilted",
    "bouncy",
    "bounce",
    "lean",
    "leaning",
}
STRUCTURAL_TARGETS = {"ceiling", "floor", "wall", "walls"}
HIDDEN_ISSUE_HINTS = {
    "normal",
    "supposed",
    "always",
    "reason",
    "why",
}
SAFETY_URGENT_HINTS = {
    "gas",
    "smoke",
    "sparking",
    "spark",
    "fire",
    "exit",
    "aed",
    "glass",
    "pouring",
    "burn",
    "burnt",
    "burning",
    "shock",
}
SAFETY_HIGH_HINTS = {
    "alarm",
    "detector",
    "broken",
    "crack",
    "unauthorized",
    "tailgating",
    "handrail",
}
NOT_MAINTENANCE_HINTS = {
    "paper",
    "towels",
    "chairs",
    "desk",
    "order",
    "move",
    "restock",
    "supplies",
    "book",
    "catering",
    "vending",
    "refund",
}
ACK_HINTS = {
    "thanks",
    "thank",
    "thx",
    "ok",
    "okay",
    "great",
    "super",
    "perfect",
    "fixed",
    "resolved",
    "works",
}


def _docs_root() -> Path:
    docs_path = Path(DOCS_DIR).resolve()
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path


def _validate_doc_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Document name is required")
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise HTTPException(status_code=400, detail="Invalid document name")
    if Path(cleaned).suffix.lower() not in DOC_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .md and .txt are allowed")
    return cleaned


def _doc_path(name: str) -> Path:
    safe_name = _validate_doc_name(name)
    root = _docs_root()
    target = (root / safe_name).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="Invalid document path")
    return target


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _auth_cookie_max_age_seconds() -> int:
    return max(1, AUTH_SESSION_TTL_HOURS) * 60 * 60


def _require_auth(
    auth_session: str | None = Cookie(default=None, alias=AUTH_SESSION_COOKIE),
) -> dict:
    if not auth_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = get_session(auth_session)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = get_user_by_id(session["user_id"])
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Invalid user")
    return user


def _require_admin(user: dict = Depends(_require_auth)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _resolved_ingest_chunk_params(
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> tuple[int, int]:
    """Merge optional overrides with config defaults; validate bounds."""
    cs = INGEST_CHUNK_SIZE if chunk_size is None else int(chunk_size)
    co = INGEST_CHUNK_OVERLAP if chunk_overlap is None else int(chunk_overlap)
    if cs < 200 or cs > 8000:
        raise HTTPException(
            status_code=422, detail="chunk_size must be between 200 and 8000"
        )
    if co < 0 or co >= cs:
        raise HTTPException(
            status_code=422,
            detail="chunk_overlap must be >= 0 and less than chunk_size",
        )
    return cs, co


def _first_env_var_with_value(*names: str) -> str | None:
    """First name in ``names`` whose value is non-empty (never returns the secret)."""
    for name in names:
        raw = os.getenv(name)
        if raw is not None and str(raw).strip():
            return name
    return None


def _env_var_nonempty(name: str) -> bool:
    raw = os.getenv(name)
    return raw is not None and bool(str(raw).strip())


def _fm_llm_diag_extra_env_key_names() -> list[str]:
    """Optional comma-separated names to include in ``env_api_key_diag`` (presence only)."""
    raw = os.getenv("FM_LLM_DIAG_EXTRA_ENV_KEYS", "")
    if not raw.strip():
        return []
    out: list[str] = []
    for part in raw.split(","):
        n = part.strip()
        if n and n not in out:
            out.append(n)
    return out


def _effective_sync_embed_env_key_name() -> str | None:
    """Mirror ``LLM_EMBED_API_KEY`` resolution: embed-specific vars, then chat key vars."""
    k = _first_env_var_with_value("LLM_EMBED_API_KEY", "NVIDIA_EMBED_API_KEY")
    if k:
        return k
    return _first_env_var_with_value("LLM_API_KEY", "NVIDIA_API_KEY")


def _env_api_key_diag() -> dict[str, Any]:
    """Which env vars are non-empty vs which names the app actually reads (no secret values)."""
    standard = (
        "LLM_API_KEY",
        "NVIDIA_API_KEY",
        "LLM_EMBED_API_KEY",
        "NVIDIA_EMBED_API_KEY",
    )
    extras = _fm_llm_diag_extra_env_key_names()
    seen: set[str] = set()
    ordered: list[str] = []
    for n in (*standard, *extras):
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    chat_win = _first_env_var_with_value("LLM_API_KEY", "NVIDIA_API_KEY")
    embed_sync_win = _effective_sync_embed_env_key_name()
    return {
        "chat_process_env_resolution_order": ["LLM_API_KEY", "NVIDIA_API_KEY"],
        "chat_process_env_winning_name": chat_win,
        "ingest_embed_sync_resolution_order": [
            "LLM_EMBED_API_KEY",
            "NVIDIA_EMBED_API_KEY",
            "LLM_API_KEY",
            "NVIDIA_API_KEY",
        ],
        "ingest_embed_sync_winning_name": embed_sync_win,
        "candidates": [{"name": n, "non_empty": _env_var_nonempty(n)} for n in ordered],
        "extra_names_from_FM_LLM_DIAG_EXTRA_ENV_KEYS": extras,
        "note": (
            "The app reads only the variables in each resolution_order (first non-empty wins). "
            "NVIDIA_* are legacy aliases; config maps them to the same values as LLM_*. "
            "Arbitrary names like MY_OTHER_LLM_API_KEY are never read unless you add them to "
            "FM_LLM_DIAG_EXTRA_ENV_KEYS for this report, set them as an LLM profile Env alias, "
            "or copy the key into LLM_API_KEY / LLM_EMBED_API_KEY in .env."
        ),
    }


def _profile_api_key_mode(
    prof: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """(mode, env_var_name). ``env_var_name`` is set only for env_alias mode."""
    if not prof:
        return ("none", None)
    alias = str(prof.get("env_alias") or "").strip()
    if alias:
        return ("env_alias", alias)
    if prof.get("has_api_key"):
        return ("stored", None)
    return ("none", None)


def _admin_ingest_pre_chunk_options() -> dict[str, Any]:
    """Read-only ingest pipeline settings applied before / while splitting into chunks."""
    return {
        "docs_dir": DOCS_DIR,
        "chroma_dir": CHROMA_DIR,
        "sanitize_instruction_like": DOCS_SANITIZE_INSTRUCTION_LIKE,
        "text_splitter_separators": ["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
        "chunk_metadata_keyword_limit": 12,
        "chroma_collection": "fm_docs",
        "embed_input_type_for_passages": "passage",
    }


def _admin_rag_settings_response() -> dict[str, Any]:
    return {
        "rag_top_k": rag_top_k_admin_detail(),
        "ingest_pre_chunk": _admin_ingest_pre_chunk_options(),
        "ingest_chunk_defaults": {
            "chunk_size": INGEST_CHUNK_SIZE,
            "chunk_overlap": INGEST_CHUNK_OVERLAP,
        },
    }


def _admin_reindex_defaults_payload() -> dict[str, Any]:
    rag = rag_top_k_admin_detail()
    return {
        "ingest_chunk_size": INGEST_CHUNK_SIZE,
        "ingest_chunk_overlap": INGEST_CHUNK_OVERLAP,
        "rag_top_k": rag["effective"],
        "rag_top_k_env_startup_default": rag["env_startup_default"],
        "rag_top_k_meta_override_active": rag["meta_override_active"],
        "rag_top_k_limits": rag["limits"],
        "limits": {
            "chunk_size_min": 200,
            "chunk_size_max": 8000,
            "chunk_overlap_min": 0,
        },
        "ingest_pre_chunk": _admin_ingest_pre_chunk_options(),
    }


def _public_llm_runtime_snapshot() -> dict[str, Any]:
    """Non-secret view of resolved LLM targets (chat/embed) + ingest embed + RAG defaults."""
    chat_pid = get_llm_task_default_profile_id("chat")
    chat_prof = get_llm_model_profile(chat_pid) if chat_pid else None
    resolved_chat = resolve_llm_profile_for_task("chat")
    embed_pid = get_llm_task_default_profile_id("embed")
    embed_prof = get_llm_model_profile(embed_pid) if embed_pid else None
    resolved_embed = resolve_llm_profile_for_task("embed")
    chat_src_profile = bool(chat_pid and chat_prof)
    embed_src_profile = bool(embed_pid and embed_prof)
    chat_mode, chat_key_name = _profile_api_key_mode(chat_prof)
    if not chat_src_profile:
        chat_mode = "process_env"
        chat_key_name = _first_env_var_with_value("LLM_API_KEY", "NVIDIA_API_KEY")
    embed_mode, embed_key_name = _profile_api_key_mode(embed_prof)
    if not embed_src_profile:
        embed_mode = "process_env"
        embed_key_name = _effective_sync_embed_env_key_name()
    sync_embed_key = _effective_sync_embed_env_key_name()
    _rag_k = rag_top_k_admin_detail()
    return {
        "rag_top_k": _rag_k["effective"],
        "rag_top_k_settings": _rag_k,
        "env_api_key_diag": _env_api_key_diag(),
        "routing": {
            "chat_completions": (
                "User-visible answers use the chat task profile (or env fallback)—e.g. Moonshot kimi."
            ),
            "rag_query_embeddings": (
                "RAG retrieves context by embedding the question. Moonshot has no suitable "
                "embedding API for EMBED_MODEL here; when the resolved embed host is Moonshot, "
                "query vectors use sync embed() from .env (LLM_EMBED_API_KEY / LLM_BASE_URL / EMBED_MODEL, "
                "typically NVIDIA). Chroma ingest uses the same env sync embed path."
            ),
        },
        "ingest_defaults": {
            "chunk_size": INGEST_CHUNK_SIZE,
            "chunk_overlap": INGEST_CHUNK_OVERLAP,
        },
        "chat": {
            "source": "profile" if chat_src_profile else "env",
            "profile_id": chat_pid,
            "profile_name": (chat_prof or {}).get("name") if chat_prof else None,
            "base_url": str(resolved_chat.base_url or "").strip(),
            "chat_model": str(resolved_chat.default_model or "").strip(),
            "api_key_configured": bool(resolved_chat.api_key),
            "api_key_mode": chat_mode,
            "api_key_env_name": chat_key_name,
            "process_env_winning_key_name": chat_key_name
            if chat_mode == "process_env"
            else None,
        },
        "embed_task": {
            "source": "profile" if embed_src_profile else "env",
            "profile_id": embed_pid,
            "profile_name": (embed_prof or {}).get("name") if embed_prof else None,
            "base_url": str(resolved_embed.base_url or "").strip(),
            "embed_model": str(resolved_embed.default_model or "").strip(),
            "api_key_configured": bool(resolved_embed.api_key),
            "api_key_mode": embed_mode,
            "api_key_env_name": embed_key_name,
            "process_env_winning_key_name": embed_key_name
            if embed_mode == "process_env"
            else None,
        },
        "ingest_embed_sync": {
            "note": (
                "Chroma ingest uses sync embed() with LLM_BASE_URL and LLM_EMBED_API_KEY "
                "(not necessarily the async embed-task profile)."
            ),
            "base_url": str(LLM_BASE_URL or "").strip(),
            "embed_model": EMBED_MODEL,
            "api_key_configured": bool(LLM_EMBED_API_KEY),
            "api_key_mode": "process_env",
            "api_key_env_name": sync_embed_key,
        },
    }


_rag_eval_jobs: dict[str, dict[str, Any]] = {}
_rag_eval_job_lock = asyncio.Lock()


async def _rag_eval_job_runner(
    job_id: str,
    user: dict,
    cases: list[rag_eval.TestCase],
    *,
    run_id: str,
    source_ref: str,
    sleep_between_seconds: float,
    max_retries: int,
    retry_wait_seconds: int,
    per_request_timeout: float | None,
    min_api_ok_pass_rate: float | None,
    min_api_ok_count: int,
    compare_prev: list[dict[str, Any]] | None,
) -> None:
    async with _rag_eval_job_lock:
        job = _rag_eval_jobs.get(job_id)
        if job:
            job["status"] = "running"
            job["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        async def on_progress(partial: list[dict[str, Any]]) -> None:
            async with _rag_eval_job_lock:
                j = _rag_eval_jobs.get(job_id)
                if j:
                    j["results"] = partial
                    j["progress"] = {"done": len(partial), "total": len(cases)}

        results, summary = await rag_eval.run_suite_internal(
            cases,
            user,
            run_id=run_id,
            source_ref=source_ref,
            sleep_between_seconds=sleep_between_seconds,
            max_retries=max_retries,
            retry_wait_seconds=retry_wait_seconds,
            per_request_timeout=per_request_timeout,
            on_progress=on_progress,
        )
        report = rag_eval.merge_report(
            results=results,
            summary=summary,
            user=user,
            compare_prev_results=compare_prev,
        )
        report["llm_runtime"] = _public_llm_runtime_snapshot()
        ok_gate, gate_msg = rag_eval.check_api_ok_gates(
            summary,
            min_api_ok_pass_rate=min_api_ok_pass_rate,
            min_api_ok_count=min_api_ok_count,
        )
        async with _rag_eval_job_lock:
            j = _rag_eval_jobs.get(job_id)
            if j:
                j["status"] = "completed"
                j["finished_at"] = datetime.now(timezone.utc).isoformat()
                j["report"] = report
                j["results"] = report["results"]
                j["summary"] = report["summary"]
                j["progress"] = {"done": len(results), "total": len(cases)}
                j["gate_ok"] = ok_gate
                j["gate_message"] = gate_msg
    except Exception as exc:
        async with _rag_eval_job_lock:
            j = _rag_eval_jobs.get(job_id)
            if j:
                j["status"] = "failed"
                j["finished_at"] = datetime.now(timezone.utc).isoformat()
                j["error"] = str(exc)


def _history_from_active_chat(user: dict, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        return list(fallback)
    try:
        payload = list_active_chat_messages(user_id, limit=60)
    except Exception:
        _obs_log.exception(
            "list_active_chat_messages failed; using frontend history fallback"
        )
        return list(fallback)
    rows = payload.get("messages", [])
    if not rows:
        return list(fallback)
    resolved: list[dict[str, str]] = []
    for row in rows:
        role_raw = str(row.get("role", "")).strip().lower()
        role = "assistant" if role_raw == "assistant" else "user"
        content = str(row.get("content", "") or "")
        if content:
            resolved.append({"role": role, "content": content})
    return resolved


def _safe_stem(name: str) -> str:
    stem = Path(name).stem.strip().lower()
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-")
    return stem or "uploaded_doc"


def _looks_like_fm_query(message: str) -> bool:
    tokens = set(re.findall(r"[a-zA-Z0-9]+", message.lower()))
    return any(token in FM_KEYWORDS for token in tokens)


def _tokens(message: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", message.lower()))


def _infer_query_type(message: str, llm_type: str) -> str:
    normalized = (llm_type or "").upper()
    if normalized in {"INFORMATIONAL", "SERVICE_REQUEST", "INCIDENT", "OUT_OF_SCOPE"}:
        return normalized
    words = _tokens(message)
    if words & INCIDENT_HINTS:
        return "INCIDENT"
    if words & ACTION_HINTS:
        return "SERVICE_REQUEST"
    return "INFORMATIONAL"


def _should_auto_create_ticket(message: str, query_type: str, in_scope: str) -> bool:
    if in_scope != "YES":
        return False
    if query_type in AUTO_TICKET_QUERY_TYPES:
        return True
    words = _tokens(message)
    score = 0
    if words & ACTION_HINTS:
        score += 2
    if words & INCIDENT_HINTS:
        score += 2
    if re.search(r"\b(b\d|floor|room|boiler|hvac|pump|valve)\b", message.lower()):
        score += 1
    if re.search(r"\b(urgent|pilne|asap|natychmiast)\b", message.lower()):
        score += 1
    return score >= 3


def _is_hidden_issue_question(message: str) -> bool:
    msg = message.lower()
    words = _tokens(msg)
    electrical_obs = bool(words & {"buzzing", "humming", "power", "strip", "outlet", "electrical", "shock"})
    question_like = "?" in message or electrical_obs or any(
        phrase in msg
        for phrase in (
            "is it normal",
            "should",
            "has it always",
            "is there a reason",
            "why does",
            "should i be able to",
            "is it me or",
            "am i imagining",
            "is it supposed to",
            "daylight through",
            "gap in",
            "draft from",
        )
    )
    structural_obs = bool(
        words
        & (
            STRUCTURAL_HINTS
            | STRUCTURAL_TARGETS
            | {
                "wet",
                "dark",
                "patch",
                "discoloration",
                "discoloured",
                "discolored",
                "daylight",
                "window",
                "frame",
                "gap",
                "draft",
            }
        )
    )
    return question_like and bool(words & (INCIDENT_HINTS | HIDDEN_ISSUE_HINTS) or structural_obs or electrical_obs)


def _looks_like_non_maintenance_request(message: str) -> bool:
    words = _tokens(message)
    m = message.lower()
    # Phrase-level: vending refunds / tenant decoration intent (not "paint peeling" faults).
    if re.search(r"\bvending\s+machine\b", m) or ("vending" in m and "money" in m):
        if not (words & (SAFETY_URGENT_HINTS | SAFETY_HIGH_HINTS | {"fire", "smoke", "spark"})):
            return True
    if re.search(r"\b(i\s+want|can\s+i)\s+to\s+paint\b", m) or re.search(
        r"\bpaint\s+my\s+(.{0,24})walls?\b", m
    ):
        if not (words & (SAFETY_URGENT_HINTS | {"leak", "mold", "flood", "asbestos"})):
            return True
    if (
        ("badge" in m or "key card" in m or "access card" in m)
        and ("new employee" in m or "request" in m or "get" in m or "need" in m or "replace" in m)
    ):
        return True
    if (
        "lost my badge" in m
        or "lost my key" in m
        or "lost key card" in m
        or "lost my card" in m
        or "lost my access" in m
        or "lost my access badge" in m
    ):
        return True
    supply_patterns = (
        "refill",
        "restock",
        "running low",
        "empty dispenser",
        "out of soap",
        "coffee beans",
        "paper towels",
    )
    if any(p in m for p in supply_patterns):
        return True
    if re.search(r"\b(cleaning|cleaner|cleaners).*(more often|increase|frequency)\b", m):
        return True
    if "come more often" in m and ("cleaning" in m or "team" in m):
        return True
    if ("nothing works" in m or "everything is broken" in m) and not (
        words & {"hvac", "heating", "cooling", "plumbing", "electrical", "elevator", "light", "lights", "water", "door", "outlet"}
    ):
        return True
    if not (words & NOT_MAINTENANCE_HINTS):
        return False
    # If this also carries strong incident markers, treat it as real maintenance.
    if words & (SAFETY_URGENT_HINTS | SAFETY_HIGH_HINTS | INCIDENT_HINTS):
        return False
    return True


def _is_directory_or_rules_information_question(message: str) -> bool:
    """
    Pure directory / policy lookups must not create tickets (e.g. emergency phone number,
    reception number, contact FM, building rules).
    """
    m = message.lower()
    if "?" not in message:
        return False
    if re.search(r"\bwhat'?s?\s+the\s+emergency\s+(number|line|hotline)\b", m):
        return True
    if re.search(r"\bwhat\s+is\s+the\s+emergency\s+(number|line|hotline)\b", m):
        return True
    if re.search(r"\bwhat'?s?\s+the\s+phone\s+number\b", m):
        return True
    if re.search(r"\bwhat'?s?\s+the\s+.*\bnumber\s+for\s+reception\b", m):
        return True
    if "how do i contact" in m or "how to contact" in m or "how can i contact" in m:
        return True
    if re.search(r"\bwhere\s+(do|can)\s+i\s+find\s+.*\b(number|contact)\b", m):
        return True
    if any(x in m for x in ("badge", "key card", "access card")) and any(
        x in m for x in ("new employee", "how", "where", "request", "procedure")
    ):
        return True
    if (
        "lost my badge" in m
        or "lost my key" in m
        or "lost key card" in m
        or "lost my card" in m
        or "lost my access" in m
        or "lost my access badge" in m
    ):
        return True
    if any(
        x in m
        for x in ("refill", "restock", "running low", "empty dispenser", "out of soap", "coffee beans", "paper towels")
    ):
        return True
    if re.search(r"\b(cleaning|cleaner|cleaners).*(more often|increase|frequency)\b", m):
        return True
    if "come more often" in m and ("cleaning" in m or "team" in m):
        return True
    return False


def _is_vague_complaint_without_actionable_detail(message: str) -> bool:
    m = message.lower()
    words = _tokens(message)
    vague_terms = {"everything", "nothing", "always", "never", "properly"}
    has_vague = bool(words & vague_terms) or ("nothing works properly" in m)
    system_markers = bool(words & {"hvac", "ac", "heating", "plumbing", "electrical", "elevator", "light", "lights", "water", "door", "outlet"})
    # Still vague even with location if no concrete system/symptom is provided.
    return has_vague and (not system_markers)


def _has_water_on_electronics_risk(message: str) -> bool:
    m = message.lower()
    liquid = any(x in m for x in ("water", "liquid", "leak", "leaking", "flood", "dripping", "pouring"))
    electronics = any(x in m for x in ("laptop", "computer", "server", "equipment", "electronics"))
    return liquid and electronics


def _has_concrete_problem_signal(message: str) -> bool:
    m = message.lower()
    words = _tokens(message)
    if words & (INCIDENT_HINTS | ACTION_HINTS):
        return True
    if _has_water_on_electronics_risk(message):
        return True
    return bool(
        re.search(
            r"\b(broken|not working|leak|leaking|smell|smoke|sparking|outage|dark|crack|sag|tilt|bouncy)\b",
            m,
        )
    )


def _is_escalation_signal(message: str) -> bool:
    m = message.lower()
    return any(
        x in m
        for x in (
            "getting worse",
            "louder every day",
            "spreading",
            "again",
            "third time",
            "keeps happening",
        )
    )


def _bump_priority_one_level(priority: str) -> str:
    p = (priority or "NORMAL").upper()
    if p == "LOW":
        return "NORMAL"
    if p == "NORMAL":
        return "HIGH"
    if p == "HIGH":
        return "URGENT"
    return "URGENT"


def _looks_like_existing_ticket_status_question(message: str) -> bool:
    """User is asking for status on an existing issue, not reporting a new one."""
    m = message.lower()
    if re.search(r"\bany\s+update\b", m):
        return True
    if re.search(r"\b(update|status)\s+on\s+(my|the)\b", m):
        return True
    if re.search(r"\bstatus\s+of\s+(my|the)\b", m):
        return True
    if re.search(r"\bhow\s+is\s+my\s+(ticket|issue|request)\b", m):
        return True
    if "ticket" in m and "status" in m:
        return True
    if "has anyone looked" in m:
        return True
    if re.search(r"\bis\s+the\s+.*\s+(back|back on|fixed|working)\b", m):
        return True
    if "is it fixed" in m or "is it back" in m:
        return True
    if "just checking" in m and ("back" in m or "fixed" in m or "working" in m):
        return True
    if "hot water back" in m:
        return True
    return False


def _apply_safety_and_category_rules(payload: dict, message: str) -> dict:
    log = logging.getLogger("fm.chat")
    words = _tokens(message)
    orig_category = str(payload.get("category", "General") or "General")
    orig_priority = str(payload.get("priority", "NORMAL") or "NORMAL").upper()
    category = orig_category
    priority = orig_priority
    if priority not in {"LOW", "NORMAL", "HIGH", "URGENT"}:
        priority = "NORMAL"

    if words & (SAFETY_URGENT_HINTS | SAFETY_HIGH_HINTS):
        if category in {"General", "Electrical", "Plumbing", "HVAC"}:
            # Safety overrides generic / subsystem labels for explicit risk events.
            if words & (SAFETY_URGENT_HINTS | {"unauthorized", "tailgating", "aed", "exit", "alarm", "detector"}):
                category = "Safety"
        if words & (SAFETY_URGENT_HINTS | {"alarm", "exit", "aed", "glass"}):
            priority = "URGENT"
        elif priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Water + electricity is always urgent safety risk.
    if ("water" in words or "leak" in words) and (
        "electrical" in words or "electricity" in words or "sparking" in words or "outlet" in words
    ):
        category = "Safety"
        priority = "URGENT"

    # Recurring smells, sewage odors, and ceiling discoloration imply real defects — at least HIGH.
    msg_lower = message.lower()
    sewage = "sewage" in msg_lower or "sewer" in msg_lower
    weird_smell = ("weird smell" in msg_lower) or (
        "smell" in msg_lower and ("anyone reported" in msg_lower or "reported the" in msg_lower)
    )
    ceiling_stain = "ceiling" in msg_lower and any(
        x in msg_lower for x in ("yellow", "brown", "discolor", "discolour", "stain", "colour", "color")
    )
    recurring = bool(re.search(r"\b(always|every\s+time|keeps|recurring|keeps happening)\b", msg_lower))
    if sewage or ceiling_stain or weird_smell or (recurring and ("smell" in msg_lower or "odor" in msg_lower)):
        if sewage:
            category = "Plumbing"
        elif weird_smell or ("smell" in msg_lower and "floor" in msg_lower):
            category = "Safety"
        elif ceiling_stain:
            category = "Plumbing"
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Standing water from appliances (e.g. coffee machine) is a slip / damage risk.
    if ("leak" in msg_lower or "leaking" in msg_lower) and "water" in msg_lower:
        if "coffee" in msg_lower or "everywhere" in msg_lower or "floor" in msg_lower:
            category = "Plumbing"
            if priority in {"LOW", "NORMAL"}:
                priority = "URGENT"

    # Keep minor facility annoyances low/normal.
    if {"soap", "dispenser", "empty"} <= words and priority not in {"LOW"}:
        priority = "LOW"
    if {"blinds", "broken"} <= words and priority not in {"LOW"}:
        priority = "LOW"

    # Structural damage heuristics.
    has_structural_shape = bool(words & STRUCTURAL_HINTS) and bool(words & STRUCTURAL_TARGETS)
    if has_structural_shape:
        category = "Safety"
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"
        if ("sag" in words or "sagging" in words) and ("ceiling" in words):
            priority = "URGENT"

    # Discolored water likely contamination risk.
    if ("water" in words) and bool(words & {"yellow", "brown", "discolored", "discoloured", "discoloration"}):
        category = "Plumbing"
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Dark patch on wall usually indicates hidden moisture.
    if ("dark" in words or "patch" in words or "stain" in words) and ("wall" in words or "walls" in words):
        category = "Plumbing"
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Burnt marks / electric shocks are immediate safety concerns.
    if ("burnt" in msg_lower or "burning mark" in msg_lower or "burn mark" in msg_lower) and (
        "outlet" in words or "electrical" in words or "power" in words
    ):
        category = "Safety"
        priority = "URGENT"
    if ("electric shock" in msg_lower or "got a shock" in msg_lower or "shocked" in words):
        category = "Safety"
        priority = "URGENT"

    # Buzzing/humming electrical devices = at least high safety risk.
    if ("buzzing" in words or "humming" in words) and (
        "power" in words or "strip" in words or "outlet" in words or "electrical" in words
    ):
        category = "Safety"
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Any burning/smoke/gas smell in mixed messages should be treated as urgent.
    msg_lower = message.lower()
    if (
        ("smell" in msg_lower or "odor" in msg_lower or "odour" in msg_lower)
        and any(x in msg_lower for x in ("burning", "smoke", "gas", "rotten egg", "sewage"))
    ):
        category = "Safety" if ("burning" in msg_lower or "smoke" in msg_lower or "gas" in msg_lower) else category
        priority = "URGENT"

    # Emergency lighting failures.
    if ("emergency light" in msg_lower or "emergency lights" in msg_lower) and any(
        x in msg_lower for x in ("not working", "didn't come on", "failed", "off")
    ):
        category = "Safety"
        priority = "URGENT"

    # Entire floor without power/light.
    if (
        bool(re.search(r"\ball(\s+the)?\s+lights\b", msg_lower))
        and bool(re.search(r"\bfloor\s+\d+\b", msg_lower))
        and any(x in msg_lower for x in ("out", "dark", "no power", "went out"))
    ) or (
        any(x in msg_lower for x in ("entire floor", "whole floor"))
        and any(x in msg_lower for x in ("out", "dark", "no power"))
    ):
        if category == "General":
            category = "Electrical"
        priority = "URGENT"

    # Multi-issue report should not stay NORMAL.
    if any(x in msg_lower for x in ("three problems", "multiple issues", "also", "and")) and (
        bool(re.search(r"\b(ac|hvac|light|lights|window|door|lock|water|elevator|heating|cooling)\b", msg_lower))
    ):
        if priority in {"LOW", "NORMAL"}:
            priority = "HIGH"

    # Escalation bump.
    if _is_escalation_signal(message):
        priority = _bump_priority_one_level(priority)

    # Never accept LOW when the user message clearly signals incident / safety / leak paths
    # (mitigates doc-injected "downgrade priority" if the user still describes the hazard).
    if priority == "LOW":
        if words & SAFETY_URGENT_HINTS:
            priority = "HIGH"
        elif words & {"leak", "leaking", "flood", "flooding"} or (
            "spark" in msg_lower or "sparking" in msg_lower
        ):
            priority = "HIGH"
        elif "stuck" in msg_lower and "elevator" in msg_lower:
            priority = "HIGH"
        elif (words & INCIDENT_HINTS) and (words & SAFETY_HIGH_HINTS):
            priority = "HIGH"

    if category != orig_category or priority != orig_priority:
        log.info(
            "post_rules_adjustment category=%s->%s priority=%s->%s",
            orig_category,
            category,
            orig_priority,
            priority,
        )

    payload["category"] = category
    payload["priority"] = priority
    return payload


def _condense_history(history: list[dict[str, str]], limit: int = 6) -> str:
    turns = history[-limit:]
    chunks: list[str] = []
    for turn in turns:
        role = turn.get("role", "")
        content = turn.get("content", "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        label = "User" if role == "user" else "Assistant"
        chunks.append(f"{label}: {content}")
    return "\n".join(chunks)


def _fallback_issue_summary(message: str) -> str:
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return "No issue summary provided."
    if len(cleaned) <= 140:
        return cleaned
    return f"{cleaned[:137]}..."


def _has_operational_signal(message: str) -> bool:
    words = _tokens(message)
    return bool((words & ACTION_HINTS) or (words & INCIDENT_HINTS))


def _is_acknowledgement(message: str) -> bool:
    words = _tokens(message)
    if not words:
        # Empty token set (e.g. emojis, "!!!", "🚨") is not an acknowledgement.
        return False
    if words.issubset(ACK_HINTS):
        return True
    # Short "confirmation only" messages should never create knowledge gaps.
    normalized = " ".join(message.strip().split())
    return len(normalized) <= 28 and bool(words & ACK_HINTS)


def _apply_fm_safety_net(payload: dict, message: str) -> dict:
    """If LLM says out-of-scope but the message looks FM-related, mark in-scope but ungrounded
    so the answer goes to knowledge gaps."""
    if payload.get("in_scope") == "NO" and _looks_like_fm_query(message):
        payload["in_scope"] = "YES"
        payload["grounded"] = "NO"
        payload["response"] = (
            "I can help only with Facility Management topics. "
            "This FM question is not covered well enough in the current documentation yet."
        )
    return payload


def _is_building_info_candidate(message: str, history_text: str) -> bool:
    # We only want true FM/building information requests in gaps.
    # Must have FM signal in current message or recent chat context.
    return _looks_like_fm_query(message) or _looks_like_fm_query(history_text)


def _extract_partial_response_text(raw: str) -> str:
    marker = '"response"'
    idx = raw.find(marker)
    if idx == -1:
        return ""
    colon = raw.find(":", idx + len(marker))
    if colon == -1:
        return ""
    quote_start = raw.find('"', colon + 1)
    if quote_start == -1:
        return ""
    i = quote_start + 1
    out: list[str] = []
    escaped = False
    while i < len(raw):
        ch = raw[i]
        if escaped:
            if ch == "n":
                out.append("\n")
            elif ch == "t":
                out.append("\t")
            elif ch == "r":
                out.append("\r")
            elif ch in {'"', "\\", "/"}:
                out.append(ch)
            elif ch == "u" and i + 4 < len(raw):
                hex_digits = raw[i + 1 : i + 5]
                try:
                    out.append(chr(int(hex_digits, 16)))
                    i += 4
                except ValueError:
                    out.append(ch)
            else:
                # Keep unknown escape content best-effort.
                out.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _chat_ticket_create_rows(
    payload: dict[str, Any],
    *,
    should_create_ticket: bool,
    req: ChatRequest,
    message_issue_summary: str,
    water_on_electronics: bool,
    escalation_signal: bool,
) -> list[dict[str, Any]]:
    """Build per-ticket field rows for ``create_ticket`` (one user message, N tickets)."""
    if not should_create_ticket:
        return []
    issues = payload.get("issues") or []
    multi = (
        MULTI_TICKET_PER_MESSAGE_ENABLED
        and isinstance(issues, list)
        and len(issues) > 0
    )

    def _apply_safety_to_row(row: dict[str, Any]) -> dict[str, Any]:
        r = dict(row)
        if water_on_electronics:
            r["category"] = "Safety"
            r["priority"] = "URGENT"
        elif escalation_signal:
            r["priority"] = _bump_priority_one_level(str(r.get("priority") or "NORMAL"))
        return r

    if multi:
        rows: list[dict[str, Any]] = []
        for it in issues:
            if not isinstance(it, dict):
                continue
            if str(it.get("create_ticket", "NO")).upper() != "YES":
                continue
            summ = str(it.get("issue_summary") or "").strip()
            if not summ:
                continue
            rows.append(
                _apply_safety_to_row(
                    {
                        "issue_summary": summ,
                        "category": str(it.get("category") or "General"),
                        "priority": str(it.get("priority") or "NORMAL"),
                        "department": str(
                            it.get("department") or "Facility Management"
                        ),
                    }
                )
            )
        if not rows:
            rows = [
                _apply_safety_to_row(
                    {
                        "issue_summary": message_issue_summary,
                        "category": str(payload.get("category") or "General"),
                        "priority": str(payload.get("priority") or "NORMAL"),
                        "department": str(
                            payload.get("department") or "Facility Management"
                        ),
                    }
                )
            ]
        return rows

    return [
        _apply_safety_to_row(
            {
                "issue_summary": message_issue_summary,
                "category": str(payload.get("category") or "General"),
                "priority": str(payload.get("priority") or "NORMAL"),
                "department": str(
                    payload.get("department") or "Facility Management"
                ),
            }
        )
    ]


def _finalize_injection_blocked_chat(
    req: ChatRequest,
    payload: dict,
    context: list[str],
    sources: list[str],
    user: dict,
) -> dict:
    """Finalize path when regex/LLM input guard blocked the main model (no tickets, no gaps)."""
    ib = str(payload.get("_injection_block") or "unknown")
    p = dict(payload)
    query_type = str(p.get("query_type") or "INFORMATIONAL")
    issue_summary = str(p.get("issue_summary") or "").strip() or (
        "Message blocked by input safety filter."
    )
    ticket_ids: list[int] = []
    ticket_created = False
    ticket_id: int | None = None
    response_text = str(p.get("response") or "")
    uid = int(user.get("id") or 0)

    p["context_count"] = len(context)
    p["used_sources"] = sources
    p["query_type"] = query_type
    p["ticket_created"] = ticket_created
    p["ticket_id"] = ticket_id
    p["ticket_ids"] = ticket_ids
    p["issue_summary"] = issue_summary

    actual_output = {
        "category": p.get("category", "General"),
        "priority": p.get("priority", "NORMAL"),
        "create_ticket": False,
        "response": p.get("response", ""),
        "issue_summary": issue_summary,
        "ticket_ids": list(ticket_ids),
    }
    try:
        retrieval_meta = {
            "num_chunks": len(sources),
            "any_chunk": bool(sources),
            "context_count": len(context),
            "ticket_ids": list(ticket_ids),
            "injection_block": ib,
        }
        create_training_example(
            input_text=req.message,
            actual_output=actual_output,
            user_id=user.get("id"),
            user_role=str(user.get("role", "")),
            query_type=str(query_type),
            in_scope=str(p.get("in_scope", "")),
            grounded=str(p.get("grounded", "")),
            context_used=list(sources),
            used_sources=list(sources),
            context_count=len(context),
            ticket_created=False,
            ticket_id=ticket_id,
            model=LLM_MODEL,
            run_id=req.run_id.strip(),
            source_type=req.source_type.strip() or "chat_log",
            source_id=req.source_id.strip(),
            source_ref=req.source_ref.strip(),
            knowledge_gap_logged=False,
            knowledge_gap_reason="",
            retrieval_meta=retrieval_meta,
        )
    except Exception:
        _obs_log.exception("create_training_example failed in injection-blocked chat finalize")
    try:
        append_chat_exchange(
            int(user.get("id") or 0),
            req.message,
            response_text,
        )
    except Exception:
        _obs_log.exception("append_chat_exchange failed in injection-blocked chat finalize")
    p.pop("_injection_block", None)
    return p


def _finalize_chat_payload(
    req: ChatRequest,
    payload: dict,
    context: list[str],
    sources: list[str],
    user: dict,
) -> dict:
    if payload.get("_injection_block"):
        return _finalize_injection_blocked_chat(req, payload, context, sources, user)
    payload = _apply_safety_and_category_rules(payload, req.message)
    query_type = _infer_query_type(req.message, payload.get("query_type", ""))
    if payload.get("in_scope") == "NO":
        query_type = "OUT_OF_SCOPE"
    conversation_text = _condense_history(req.history)
    decision_source = payload.get("create_ticket", "NO")
    non_maintenance = _looks_like_non_maintenance_request(req.message)
    info_lookup = _is_directory_or_rules_information_question(req.message)
    concrete_problem = _has_concrete_problem_signal(req.message)
    mixed_info_and_problem = info_lookup and concrete_problem
    followup_status = _looks_like_existing_ticket_status_question(req.message)
    hidden_issue = _is_hidden_issue_question(req.message) and not info_lookup and not followup_status
    vague_complaint = _is_vague_complaint_without_actionable_detail(req.message)
    escalation_signal = _is_escalation_signal(req.message)
    water_on_electronics = _has_water_on_electronics_risk(req.message)
    if payload.get("in_scope") != "YES":
        should_create_ticket = False
    elif vague_complaint:
        should_create_ticket = False
    elif non_maintenance:
        should_create_ticket = False
    elif (info_lookup and not mixed_info_and_problem) or (followup_status and not escalation_signal):
        should_create_ticket = False
    elif decision_source == "YES":
        should_create_ticket = True
    elif decision_source == "NO":
        # Trust the LLM's NO unless a strong override fires below (water_on_electronics,
        # escalation_signal, hidden_issue). Eliminates expected=NO actual=YES drift.
        should_create_ticket = False
    else:
        heuristic_input = f"{conversation_text}\nUser: {req.message}".strip()
        should_create_ticket = _should_auto_create_ticket(
            heuristic_input, query_type, payload.get("in_scope", "YES")
        )
    if hidden_issue and payload.get("in_scope") == "YES":
        should_create_ticket = True
        if query_type == "INFORMATIONAL":
            query_type = "INCIDENT"
    elif (info_lookup or followup_status) and not should_create_ticket:
        query_type = "INFORMATIONAL"

    if water_on_electronics and payload.get("in_scope") == "YES":
        should_create_ticket = True
        payload["category"] = "Safety"
        payload["priority"] = "URGENT"
        query_type = "INCIDENT"

    if escalation_signal and payload.get("in_scope") == "YES":
        should_create_ticket = True
        payload["priority"] = _bump_priority_one_level(str(payload.get("priority", "NORMAL")))
        if query_type == "INFORMATIONAL":
            query_type = "INCIDENT"

    if should_create_ticket and query_type not in AUTO_TICKET_QUERY_TYPES:
        # Keep query_type aligned with the actual ticket decision.
        query_type = "INCIDENT"
    issue_summary = _fallback_issue_summary(payload.get("issue_summary", ""))
    if issue_summary == "No issue summary provided.":
        issue_summary = _fallback_issue_summary(req.message)

    ticket_rows = _chat_ticket_create_rows(
        payload,
        should_create_ticket=should_create_ticket,
        req=req,
        message_issue_summary=issue_summary,
        water_on_electronics=water_on_electronics,
        escalation_signal=escalation_signal,
    )
    ticket_ids: list[int] = []
    tickets_out: list[dict[str, Any]] = []
    response_text = str(payload.get("response") or "")
    uid = int(user.get("id") or 0)
    for row in ticket_rows:
        ticket = create_ticket(
            message=req.message,
            issue_summary=row["issue_summary"],
            category=row["category"],
            priority=row["priority"],
            department=row["department"],
            response=response_text,
            created_by_user_id=uid,
        )
        ticket_ids.append(int(ticket["id"]))
        tickets_out.append(ticket)
    if tickets_out:
        try:
            mail_notify.notify_tickets_created_batch(tickets_out, user.get("username"))
        except Exception:
            _obs_log.exception("mail notify ticket(s) failed (chat finalize)")
    ticket_id: int | None = ticket_ids[0] if ticket_ids else None
    ticket_created = bool(ticket_ids)

    payload["context_count"] = len(context)
    payload["used_sources"] = sources
    payload["query_type"] = query_type
    payload["ticket_created"] = ticket_created
    payload["ticket_id"] = ticket_id
    payload["ticket_ids"] = ticket_ids
    payload["issue_summary"] = issue_summary
    heuristic_input = f"{conversation_text}\nUser: {req.message}".strip()
    should_log_knowledge_gap = (
        payload.get("in_scope") == "YES"
        and payload.get("grounded") == "NO"
        and query_type == "INFORMATIONAL"
        and not ticket_created
        and not _has_operational_signal(heuristic_input)
        and not _is_acknowledgement(req.message)
        and _is_building_info_candidate(req.message, conversation_text)
    )
    gap_reason = ""
    if should_log_knowledge_gap:
        gap_reason = (
            "grounded=NO informational FM question; "
            "no operational signal; no ticket created"
        )
        create_knowledge_gap(
            question=req.message,
            ticket_id=ticket_id,
            category=payload.get("category", "General"),
            response=payload["response"],
            notes=gap_reason,
        )
    actual_output = {
        "category": payload.get("category", "General"),
        "priority": payload.get("priority", "NORMAL"),
        "create_ticket": bool(ticket_created),
        "response": payload.get("response", ""),
        "issue_summary": issue_summary,
        "ticket_ids": list(ticket_ids),
    }
    try:
        retrieval_meta = {
            "num_chunks": len(sources),
            "any_chunk": bool(sources),
            "context_count": len(context),
            "ticket_ids": list(ticket_ids),
        }
        create_training_example(
            input_text=req.message,
            actual_output=actual_output,
            user_id=user.get("id"),
            user_role=str(user.get("role", "")),
            query_type=str(query_type),
            in_scope=str(payload.get("in_scope", "")),
            grounded=str(payload.get("grounded", "")),
            context_used=list(sources),
            used_sources=list(sources),
            context_count=len(context),
            ticket_created=bool(ticket_created),
            ticket_id=ticket_id,
            model=LLM_MODEL,
            run_id=req.run_id.strip(),
            source_type=req.source_type.strip() or "chat_log",
            source_id=req.source_id.strip(),
            source_ref=req.source_ref.strip(),
            knowledge_gap_logged=bool(should_log_knowledge_gap),
            knowledge_gap_reason=gap_reason,
            retrieval_meta=retrieval_meta,
        )
    except Exception:
        # Training log must not break chat flow, but it must leave a trail.
        _obs_log.exception("create_training_example failed in chat finalize")
    try:
        append_chat_exchange(
            int(user.get("id") or 0),
            req.message,
            str(payload.get("response", "") or ""),
        )
    except Exception:
        _obs_log.exception("append_chat_exchange failed in chat finalize")
    payload.pop("_injection_block", None)
    payload.pop("_output_guard_issues", None)
    return payload


def _run_llm_probe() -> dict[str, str]:
    """Single source of truth for the optional LLM sanity check used by /health and /health/llm.
    Uses LLM_HEALTH_TIMEOUT_SECONDS so monitors don't hang for the full chat timeout."""
    if not LLM_API_KEY:
        return {
            "status": "warning",
            "message": "Missing LLM_API_KEY (or legacy NVIDIA_API_KEY)",
        }
    try:
        reply = chat_with_health_timeout(
            [{"role": "user", "content": "Reply with: ok"}],
        )
        return {
            "status": "ok",
            "provider": "openai_compatible",
            "base_url": LLM_BASE_URL,
            "probe": reply.strip(),
        }
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "message": str(exc)}


@app.get("/health")
def health(probe: int = Query(default=0, ge=0, le=1)) -> dict[str, str]:
    # Default: cheap liveness check (no external calls), so monitors don't hang
    # if the LLM provider is slow or offline. Pass `?probe=1` for full sanity.
    if probe != 1:
        if not LLM_API_KEY:
            return {
                "status": "warning",
                "message": "Missing LLM_API_KEY (or legacy NVIDIA_API_KEY)",
            }
        return {"status": "ok", "provider": "openai_compatible", "base_url": LLM_BASE_URL}
    return _run_llm_probe()


@app.get("/health/llm")
def health_llm() -> dict[str, str]:
    return _run_llm_probe()


@app.post("/api/chat")
@limiter.limit(RATE_LIMIT_CHAT)
async def api_chat(
    request: Request, req: ChatRequest, user: dict = Depends(_require_auth)
) -> dict:
    try:
        return await run_chat_core(req, user, isolate_history=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/stream")
@limiter.limit(RATE_LIMIT_CHAT)
async def api_chat_stream(
    request: Request, req: ChatRequest, user: dict = Depends(_require_auth)
) -> StreamingResponse:
    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    async def generate_events():
        try:
            chat_req = await chat_request_with_merged_history(
                req, user, isolate_history=False
            )
            resolved = resolve_llm_profile_for_task("chat")
            context: list[str] = []
            sources: list[str] = []
            raw = ""
            streamed_len = 0

            if regex_hits_injection(chat_req.message):
                payload = synthetic_injection_blocked_payload("regex")
            elif CHAT_INJECTION_LLM_FILTER:
                inj = await llm_classify_injection(
                    chat_req.message, resolved=resolved
                )
                if inj == "INJECTION":
                    payload = synthetic_injection_blocked_payload("llm")
                else:
                    context, sources = await asyncio.to_thread(
                        retrieve_with_sources, chat_req.message, effective_rag_top_k()
                    )
                    async for chunk in agenerate_stream(
                        chat_req.message,
                        context,
                        chat_req.history,
                        resolved=resolved,
                    ):
                        raw += chunk
                        partial_response = _extract_partial_response_text(raw)
                        if len(partial_response) > streamed_len:
                            delta = partial_response[streamed_len:]
                            streamed_len = len(partial_response)
                            if delta:
                                yield event({"type": "chunk", "delta": delta})
                    try:
                        payload = parse_llm_json(raw)
                    except Exception:
                        payload = fallback_response(raw)
                    payload = apply_output_guardrails(payload, chat_req.message)
                    payload = _apply_fm_safety_net(payload, chat_req.message)
            else:
                context, sources = await asyncio.to_thread(
                    retrieve_with_sources, chat_req.message, effective_rag_top_k()
                )
                async for chunk in agenerate_stream(
                    chat_req.message,
                    context,
                    chat_req.history,
                    resolved=resolved,
                ):
                    raw += chunk
                    partial_response = _extract_partial_response_text(raw)
                    if len(partial_response) > streamed_len:
                        delta = partial_response[streamed_len:]
                        streamed_len = len(partial_response)
                        if delta:
                            yield event({"type": "chunk", "delta": delta})
                try:
                    payload = parse_llm_json(raw)
                except Exception:
                    payload = fallback_response(raw)
                payload = apply_output_guardrails(payload, chat_req.message)
                payload = _apply_fm_safety_net(payload, chat_req.message)

            final_payload = await asyncio.to_thread(
                _finalize_chat_payload, chat_req, payload, context, sources, user
            )
            final_response = final_payload.get("response", "")
            if isinstance(final_response, str) and len(final_response) > streamed_len:
                yield event(
                    {"type": "chunk", "delta": final_response[streamed_len:]}
                )
            yield event({"type": "final", "payload": final_payload})
        except Exception as exc:
            # Keep any partial chunks already streamed and just append a marker.
            yield event(
                {
                    "type": "chunk",
                    "delta": "\n\n[stream interrupted; see server logs for details]",
                }
            )
            yield event({"type": "error", "message": str(exc), "partial": True})

    return StreamingResponse(generate_events(), media_type="text/event-stream")


@app.get("/api/chat/history")
def api_chat_history(
    limit: int = Query(default=200, ge=1, le=2000),
    user: dict = Depends(_require_auth),
) -> dict:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Missing user id")
    return list_active_chat_messages(user_id, limit=limit)


@app.post("/api/chat/new")
def api_chat_new(user: dict = Depends(_require_auth)) -> dict:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Missing user id")
    thread = start_new_chat_thread(user_id)
    return {"thread": thread}


@app.post("/api/embed")
@limiter.limit(RATE_LIMIT_EMBED)
def api_embed(request: Request, req: EmbedRequest) -> dict:
    try:
        vectors = embed(req.texts, input_type=req.input_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"embeddings": vectors}


@app.post("/api/ingest")
def api_ingest() -> dict:
    try:
        count = run_ingest()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"chunks_indexed": count}


@app.post("/api/auth/login")
def api_auth_login(req: AuthLoginRequest, response: Response) -> dict:
    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session = create_session(user["id"])
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session["id"],
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
        secure=AUTH_COOKIE_SECURE,
        max_age=_auth_cookie_max_age_seconds(),
    )
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
        },
    }


@app.post("/api/auth/register")
def api_auth_register(req: AuthRegisterRequest) -> dict:
    try:
        user = create_user_account(req.username, req.password, role="user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "created": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
        },
    }


@app.post("/api/auth/logout")
def api_auth_logout(
    response: Response,
    auth_session: str | None = Cookie(default=None, alias=AUTH_SESSION_COOKIE),
) -> dict:
    if auth_session:
        delete_session(auth_session)
    response.delete_cookie(key=AUTH_SESSION_COOKIE)
    return {"authenticated": False}


@app.get("/api/auth/session")
def api_auth_session(user: dict = Depends(_require_auth)) -> dict:
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
        },
    }


@app.get("/api/tickets")
def api_tickets(
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: dict = Depends(_require_auth),
) -> dict:
    created_by_user_id = None if user.get("role") == "admin" else user["id"]
    return {
        "tickets": get_tickets(
            category=category,
            priority=priority,
            status=status,
            created_by_user_id=created_by_user_id,
        )
    }


@app.post("/api/tickets/manual")
def api_tickets_manual(req: ManualTicketCreateRequest, user: dict = Depends(_require_auth)) -> dict:
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    issue_summary = req.issue_summary.strip() or "Manual ticket from chat"
    ticket = create_ticket(
        message=message,
        issue_summary=issue_summary,
        category=req.category,
        priority=req.priority,
        department=req.department,
        response=req.response,
        created_by_user_id=user["id"],
    )
    try:
        mail_notify.notify_ticket_created(ticket, user.get("username"))
    except Exception:
        _obs_log.exception("mail notify_ticket_created failed (manual ticket)")
    return {"ticket": ticket}


@app.get("/api/tickets/stats")
def api_tickets_stats(user: dict = Depends(_require_auth)) -> dict:
    created_by_user_id = None if user.get("role") == "admin" else user["id"]
    return ticket_stats(created_by_user_id=created_by_user_id)


@app.patch("/api/tickets/{ticket_id}")
def api_ticket_update(
    ticket_id: int,
    req: TicketStatusRequest,
    user: dict = Depends(_require_auth),
) -> dict:
    existing = get_ticket(ticket_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.get("role") != "admin" and existing.get("created_by_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied for this ticket")
    old_status = str(existing.get("status", ""))
    try:
        ticket = update_ticket_status(ticket_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    creator_email = None
    cid = ticket.get("created_by_user_id")
    if cid is not None:
        creator = get_user_by_id(int(cid))
        if creator:
            creator_email = creator.get("email")
    try:
        mail_notify.notify_ticket_status_changed(
            existing, ticket, old_status, creator_email
        )
    except Exception:
        _obs_log.exception("mail notify_ticket_status_changed failed")
    return {"ticket": ticket}


@app.get("/api/tickets/{ticket_id}")
def api_ticket_by_id(ticket_id: int, user: dict = Depends(_require_auth)) -> dict:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.get("role") != "admin" and ticket.get("created_by_user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied for this ticket")
    return {"ticket": ticket}


@app.get("/api/admin/tickets/{ticket_id}/resolution-notes")
def api_admin_ticket_resolution_notes(
    ticket_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"notes": get_resolution_notes(ticket_id)}


@app.post("/api/admin/tickets/{ticket_id}/resolution-notes")
def api_admin_ticket_resolution_note_create(
    ticket_id: int,
    req: ResolutionNoteCreateRequest,
    admin: dict = Depends(_require_admin),
) -> dict:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        note = create_resolution_note(
            ticket_id=ticket_id,
            note=req.note,
            added_by=req.added_by.strip() or str(admin.get("username", "")),
            parts_used=req.parts_used,
            cost=req.cost,
            time_spent_minutes=req.time_spent_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"note": note}


@app.get("/api/admin/tickets/{ticket_id}/classification-overrides")
def api_admin_ticket_classification_overrides(
    ticket_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"overrides": get_classification_overrides(ticket_id)}


@app.post("/api/admin/tickets/{ticket_id}/classification-overrides")
def api_admin_ticket_classification_override_create(
    ticket_id: int,
    req: ClassificationOverrideCreateRequest,
    admin: dict = Depends(_require_admin),
) -> dict:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        result = apply_classification_override(
            ticket_id=ticket_id,
            field_changed=req.field_changed,
            manager_value=req.manager_value,
            changed_by=req.changed_by.strip() or str(admin.get("username", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/api/admin/users")
def api_admin_users(_: dict = Depends(_require_admin)) -> dict:
    return {"users": list_users()}


@app.patch("/api/admin/users/{user_id}")
def api_admin_user_patch(
    user_id: int,
    req: AdminUserUpdateRequest,
    admin: dict = Depends(_require_admin),
) -> dict:
    if req.role is None and req.is_active is None and req.email is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    if user_id == admin.get("id") and req.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    active: int | None = None
    if req.is_active is not None:
        active = 1 if req.is_active else 0
    try:
        updated = update_user_admin_fields(
            user_id,
            role=req.role,
            is_active=active,
            email=req.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": updated}


@app.post("/api/admin/users/{user_id}/erase-chat-training-data")
def api_admin_user_erase_chat_training_data(
    user_id: int,
    req: AdminUserEraseChatTrainingRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if (req.confirm_username or "").strip() != str(target.get("username") or ""):
        raise HTTPException(
            status_code=400,
            detail="confirm_username must exactly match the target user's username",
        )
    counts = erase_user_chat_and_training_data(user_id)
    return {"ok": True, "user_id": user_id, "deleted": counts}


@app.get("/api/admin/docs")
def api_admin_docs(_: dict = Depends(_require_admin)) -> dict:
    root = _docs_root()
    docs = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in DOC_ALLOWED_EXTENSIONS:
            continue
        docs.append({"name": path.name, "size_bytes": path.stat().st_size})
    return {"docs": docs}


@app.get("/api/admin/docs/{name}")
def api_admin_doc_get(name: str, _: dict = Depends(_require_admin)) -> dict:
    path = _doc_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return {"name": path.name, "content": path.read_text(encoding="utf-8")}


@app.post("/api/admin/docs")
def api_admin_doc_create(
    req: AdminDocCreateRequest, _: dict = Depends(_require_admin)
) -> dict:
    path = _doc_path(req.name)
    if path.exists():
        raise HTTPException(status_code=409, detail="Document already exists")
    path.write_text(req.content, encoding="utf-8")
    return {"created": True, "name": path.name}


@app.put("/api/admin/docs/{name}")
def api_admin_doc_update(
    name: str, req: AdminDocUpdateRequest, _: dict = Depends(_require_admin)
) -> dict:
    path = _doc_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    path.write_text(req.content, encoding="utf-8")
    return {"updated": True, "name": path.name}


@app.delete("/api/admin/docs/{name}")
def api_admin_doc_delete(name: str, _: dict = Depends(_require_admin)) -> dict:
    path = _doc_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    path.unlink()
    return {"deleted": True, "name": name}


@app.get("/api/admin/reindex/defaults")
def api_admin_reindex_defaults(_: dict = Depends(_require_admin)) -> dict:
    return _admin_reindex_defaults_payload()


@app.get("/api/admin/rag/settings")
def api_admin_rag_settings_get(_: dict = Depends(_require_admin)) -> dict:
    return _admin_rag_settings_response()


@app.post("/api/admin/rag/settings")
@app.patch("/api/admin/rag/settings")
def api_admin_rag_settings_patch(
    req: AdminRagSettingsPatchRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    if req.clear_rag_top_k_override and req.rag_top_k is not None:
        raise HTTPException(
            status_code=400,
            detail="Use either clear_rag_top_k_override or rag_top_k, not both",
        )
    if req.clear_rag_top_k_override:
        delete_meta(RAG_TOP_K_META_KEY)
    elif req.rag_top_k is not None:
        lim = rag_top_k_admin_detail()["limits"]
        k = int(req.rag_top_k)
        lo, hi = int(lim["min"]), int(lim["max"])
        if k < lo or k > hi:
            raise HTTPException(
                status_code=422,
                detail=f"rag_top_k must be between {lo} and {hi}",
            )
        set_meta(RAG_TOP_K_META_KEY, str(k))
    return _admin_rag_settings_response()


@app.get("/api/admin/llm/chat-target")
def api_admin_llm_chat_target(_: dict = Depends(_require_admin)) -> dict:
    return _public_llm_runtime_snapshot()


@app.post("/api/admin/reindex")
def api_admin_reindex(
    _: dict = Depends(_require_admin),
    chunk_size: int | None = Query(default=None),
    chunk_overlap: int | None = Query(default=None),
) -> dict:
    cs, co = _resolved_ingest_chunk_params(chunk_size, chunk_overlap)
    try:
        count = run_ingest(chunk_size=cs, chunk_overlap=co)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"chunks_indexed": count, "chunk_size": cs, "chunk_overlap": co}


@app.post("/api/admin/upload")
async def api_admin_upload(
    file: UploadFile = File(...),
    overwrite: bool = Form(default=True),
    auto_reindex: bool = Form(default=False),
    chunk_size: int | None = Form(default=None),
    chunk_overlap: int | None = Form(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in UPLOAD_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .txt, .md, .csv, .pdf, or .docx",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        text = extract_text_from_upload(filename, raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in file")

    text = sanitize_document_text(text, enabled=DOCS_SANITIZE_INSTRUCTION_LIKE)

    target_name = f"{_safe_stem(filename)}.md"
    path = _doc_path(target_name)
    if path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="Target document already exists")
    path.write_text(text, encoding="utf-8")
    reindex_count: int | None = None
    reindex_chunk_size: int | None = None
    reindex_chunk_overlap: int | None = None
    if auto_reindex:
        try:
            cs, co = _resolved_ingest_chunk_params(chunk_size, chunk_overlap)
            reindex_count = run_ingest(chunk_size=cs, chunk_overlap=co)
            reindex_chunk_size = cs
            reindex_chunk_overlap = co
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Upload succeeded, but reindex failed: {exc}"
            ) from exc
    return {
        "uploaded": True,
        "source_filename": filename,
        "saved_as": target_name,
        "chars": len(text),
        "auto_reindexed": auto_reindex,
        "chunks_indexed": reindex_count,
        "chunk_size": reindex_chunk_size,
        "chunk_overlap": reindex_chunk_overlap,
    }


@app.post("/api/admin/login")
def api_admin_login(req: AuthLoginRequest, response: Response) -> dict:
    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    session = create_session(user["id"])
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session["id"],
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
        secure=AUTH_COOKIE_SECURE,
        max_age=_auth_cookie_max_age_seconds(),
    )
    return {"authenticated": True, "username": user["username"], "role": user["role"]}


@app.post("/api/admin/logout")
def api_admin_logout(
    response: Response,
    auth_session: str | None = Cookie(default=None, alias=AUTH_SESSION_COOKIE),
) -> dict:
    return api_auth_logout(response, auth_session)


@app.get("/api/admin/session")
def api_admin_session(user: dict = Depends(_require_admin)) -> dict:
    return {
        "authenticated": True,
        "username": user["username"],
        "role": user["role"],
        "user_id": user["id"],
    }


@app.get("/api/admin/knowledge-gaps")
def api_admin_knowledge_gaps(
    status: str | None = Query(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    return {"gaps": get_knowledge_gaps(status=status)}


@app.patch("/api/admin/knowledge-gaps/{gap_id}")
def api_admin_knowledge_gap_update(
    gap_id: int,
    req: KnowledgeGapUpdateRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    try:
        gap = update_knowledge_gap(gap_id, req.status, req.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not gap:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    return {"gap": gap}


@app.get("/api/admin/knowledge-gaps/{gap_id}")
def api_admin_knowledge_gap_by_id(
    gap_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    gap = get_knowledge_gap(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    return {"gap": gap}


@app.post("/api/admin/knowledge-gaps/{gap_id}/resolve")
def api_admin_knowledge_gap_resolve(
    gap_id: int,
    req: KnowledgeGapResolveRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    gap = get_knowledge_gap(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    if req.mode not in {"append", "overwrite"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use append or overwrite")
    path = _doc_path(req.doc_name)
    if req.mode == "append" and path.exists():
        existing = path.read_text(encoding="utf-8")
        separator = "\n\n---\n\n"
        merged = f"{existing}{separator}{req.content.strip()}\n"
        path.write_text(merged, encoding="utf-8")
    else:
        path.write_text(req.content, encoding="utf-8")

    chunks_indexed: int | None = None
    if req.auto_reindex:
        try:
            cs, co = _resolved_ingest_chunk_params(req.chunk_size, req.chunk_overlap)
            chunks_indexed = run_ingest(chunk_size=cs, chunk_overlap=co)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resolve saved, reindex failed: {exc}") from exc

    notes = f"resolved_in={path.name}; mode={req.mode}"
    resolved_gap = update_knowledge_gap(
        gap_id,
        "resolved",
        notes,
        req.category,
    )
    return {"gap": resolved_gap, "saved_doc": path.name, "chunks_indexed": chunks_indexed}


@app.get("/api/admin/training-examples")
def api_admin_training_examples(
    correction_type: str | None = Query(default=None),
    user_role: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(_require_admin),
) -> dict:
    rows = get_training_examples(
        correction_type=correction_type,
        user_role=user_role,
        limit=limit,
        offset=offset,
    )
    return {"examples": rows}


@app.get("/api/admin/training-quality/groups")
def api_admin_training_quality_groups(
    limit_per_group: int = Query(default=5, ge=1, le=50),
    _: dict = Depends(_require_admin),
) -> dict:
    """Faza B: aggregate pending training_examples by mismatch_fields. No LLM."""
    return list_pending_grouped(limit_per_group=limit_per_group)


@app.post("/api/admin/training-quality/eval/run")
async def api_admin_training_quality_eval_run(
    _: dict = Depends(_require_admin),
) -> dict:
    """REMOVED. The full eval_golden flow was retired in favor of per-override
    replay (`POST /api/admin/training-quality/overrides/{id}/replay`).

    Returns 410 Gone so callers fail loudly. The columns and helpers stick
    around until Phase 4 migration removes them.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "eval_golden flow is removed. Use "
            "POST /api/admin/training-quality/overrides/{id}/replay for an "
            "on-demand mini-replay."
        ),
    )


@app.get("/api/admin/training-quality/eval/runs")
def api_admin_training_quality_eval_runs(
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(_require_admin),
) -> dict:
    return {"runs": list_eval_runs(limit=limit)}


@app.get("/api/admin/training-quality/eval/runs/{run_id}")
def api_admin_training_quality_eval_run_by_id(
    run_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    item = get_eval_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return {"run": item}


@app.post("/api/admin/rag-eval/jobs")
async def api_admin_rag_eval_start_job(
    suite: str = Form(...),
    case_ids: str = Form(""),
    run_id: str = Form(""),
    source_ref: str = Form(""),
    sleep_between_seconds: float = Form(15.0),
    max_retries: int = Form(3),
    retry_wait_seconds: int = Form(10),
    min_api_ok_pass_rate: str = Form(""),
    min_api_ok_count: int = Form(0),
    per_request_timeout_seconds: float = Form(240.0),
    suite_file: UploadFile | None = File(None),
    compare_file: UploadFile | None = File(None),
    user: dict = Depends(_require_admin),
) -> dict:
    """Start a background RAG/chat eval job (isolated history per case)."""
    kind = suite.strip().lower()
    ref_default: str
    if kind == "builtin":
        cases = rag_eval.build_builtin_cases()
        ref_default = "builtin_cases"
    elif kind == "json":
        if not suite_file or not suite_file.filename:
            raise HTTPException(
                status_code=422, detail="suite_file is required for json suite"
            )
        raw = await suite_file.read()
        cases = rag_eval.build_test_cases_from_json_bytes(raw)
        ref_default = suite_file.filename or "uploaded.json"
    elif kind == "csv":
        if not suite_file or not suite_file.filename:
            raise HTTPException(
                status_code=422, detail="suite_file is required for csv suite"
            )
        raw = await suite_file.read()
        cases = rag_eval.build_test_cases_from_csv_bytes(raw)
        ref_default = suite_file.filename or "uploaded.csv"
    else:
        raise HTTPException(
            status_code=422,
            detail="suite must be one of: builtin, json, csv",
        )

    if not cases:
        raise HTTPException(status_code=422, detail="suite contains no test cases")

    if case_ids.strip():
        wanted = rag_eval.parse_case_ids_blob(case_ids)
        cases = [c for c in cases if c.id in wanted]
        if not cases:
            raise HTTPException(
                status_code=422, detail="no cases left after case_ids filter"
            )

    compare_prev: list[dict[str, Any]] | None = None
    if compare_file and compare_file.filename:
        craw = await compare_file.read()
        if len(craw) > rag_eval.MAX_SUITE_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="compare_file too large")
        try:
            data = json.loads(craw.decode("utf-8-sig"))
            compare_prev = list(data.get("results", []))
        except (json.JSONDecodeError, TypeError) as exc:
            raise HTTPException(
                status_code=422, detail=f"compare_file must be JSON with results[]: {exc}"
            ) from exc

    min_rate: float | None = None
    mpr = (min_api_ok_pass_rate or "").strip()
    if mpr:
        try:
            min_rate = float(mpr)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="min_api_ok_pass_rate must be a number"
            ) from exc
        if not (0.0 <= min_rate <= 100.0):
            raise HTTPException(
                status_code=422, detail="min_api_ok_pass_rate must be between 0 and 100"
            )

    job_id = str(uuid.uuid4())
    rid = run_id.strip() or datetime.now(timezone.utc).strftime("testrun-%Y%m%dT%H%M%SZ")
    sref = source_ref.strip() or ref_default
    timeout = per_request_timeout_seconds if per_request_timeout_seconds > 0 else None

    async with _rag_eval_job_lock:
        _rag_eval_jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
            "progress": {"done": 0, "total": len(cases)},
            "results": [],
            "report": None,
            "summary": None,
            "error": None,
            "gate_ok": None,
            "gate_message": None,
        }

    asyncio.create_task(
        _rag_eval_job_runner(
            job_id,
            user,
            cases,
            run_id=rid,
            source_ref=sref,
            sleep_between_seconds=sleep_between_seconds,
            max_retries=max_retries,
            retry_wait_seconds=retry_wait_seconds,
            per_request_timeout=timeout,
            min_api_ok_pass_rate=min_rate,
            min_api_ok_count=min_api_ok_count,
            compare_prev=compare_prev,
        )
    )
    return {"job_id": job_id}


@app.get("/api/admin/rag-eval/jobs/{job_id}")
async def api_admin_rag_eval_job_status(
    job_id: str,
    _: dict = Depends(_require_admin),
) -> dict:
    async with _rag_eval_job_lock:
        job = _rag_eval_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


class PromptOverrideApplyRequest(BaseModel):
    error_type: str
    suggested_change: str = ""
    approved_change: str
    rationale: str = ""
    affected_example_ids: list[int] = []
    confidence: float = 1.0
    manually_edited: bool = False
    force: bool = False


@app.post("/api/admin/training-quality/overrides/apply")
async def api_admin_overrides_apply(
    req: PromptOverrideApplyRequest,
    user: dict = Depends(_require_admin),
) -> dict:
    """Apply a (possibly manager-edited) prompt override.

    Guards:
      - 422 max_active_overrides if MAX_ACTIVE_OVERRIDES already active
      - 422 low_confidence if analyzer confidence < OVERRIDE_MIN_CONFIDENCE
        and the manager did not explicitly mark the change as manually_edited

    Note: testing the override now happens through a separate
    POST /overrides/{id}/replay request (mini-replay on affected examples plus
    paraphrases). The legacy `eval_baseline_id` flow is no longer required.
    """
    approved = (req.approved_change or "").strip()
    if not approved:
        raise HTTPException(status_code=422, detail="approved_change is required")

    if count_active_prompt_overrides() >= MAX_ACTIVE_OVERRIDES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"max_active_overrides reached ({MAX_ACTIVE_OVERRIDES}); rollback or "
                "consolidate existing overrides before applying a new one"
            ),
        )

    if req.confidence < OVERRIDE_MIN_CONFIDENCE and not req.manually_edited:
        raise HTTPException(
            status_code=422,
            detail=(
                f"low_confidence ({req.confidence:.2f}) below floor "
                f"{OVERRIDE_MIN_CONFIDENCE}; edit the rule manually before applying"
            ),
        )

    base_head = get_effective_system_prompt_head()

    active_overrides = list_prompt_overrides(status="active", limit=200)
    duplicate = find_duplicate_rule(approved, base_head, active_overrides)
    _tq_log.debug(
        "apply override duplicate-check approved_len=%d active=%d force=%s is_dup=%s score=%s",
        len(approved),
        len(active_overrides),
        bool(req.force),
        bool(duplicate.get("is_duplicate")),
        duplicate.get("score"),
    )
    if duplicate.get("is_duplicate") and not req.force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "duplicate_prompt_rule",
                "duplicate": duplicate,
            },
        )

    record = db_apply_prompt_override(
        error_type=req.error_type,
        suggested_change=req.suggested_change,
        approved_change=approved,
        rationale=req.rationale.strip(),
        affected_example_ids=req.affected_example_ids,
        created_by_user_id=user.get("id"),
        eval_baseline_id=None,
    )
    record_prompt_override_audit(
        override_id=int(record.get("id") or 0),
        action="apply",
        actor_user_id=user.get("id"),
        payload={
            "error_type": req.error_type,
            "affected_count": len(req.affected_example_ids or []),
            "force": bool(req.force),
        },
    )

    return {"override": record}


class PromptOverrideConsolidateRequest(BaseModel):
    force: bool = False
    llm_profile_id: int | None = None


@app.post("/api/admin/training-quality/overrides/consolidate")
@limiter.limit("2/5minute")
async def api_admin_overrides_consolidate(
    request: Request,
    req: PromptOverrideConsolidateRequest,
    user: dict = Depends(_require_admin),
) -> dict:
    """Merge all active prompt overrides into one via LLM, atomically in SQLite.

    Allowed only when active count equals ``MAX_ACTIVE_OVERRIDES``. If the merged
    text duplicates the base system prompt, returns 409 unless ``force`` is true.
    """
    from .prompt_consolidator import merge_active_overrides_async

    n = count_active_prompt_overrides()
    if n != MAX_ACTIVE_OVERRIDES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"consolidate_requires_full_cap: have {n} active, need exactly "
                f"{MAX_ACTIVE_OVERRIDES}"
            ),
        )
    active_rows = get_active_prompt_overrides(force_refresh=True)
    expected_ids = [int(r["id"]) for r in active_rows]
    if len(expected_ids) != MAX_ACTIVE_OVERRIDES:
        raise HTTPException(
            status_code=422,
            detail="active_override_count_mismatch_refresh_and_retry",
        )

    from .llm_profiles import resolve_llm_profile_for_task

    try:
        merge_result = await merge_active_overrides_async(
            active_rows,
            llm_profile=resolve_llm_profile_for_task(
                "consolidator", profile_id=req.llm_profile_id
            ),
        )
    except APIStatusError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "NVIDIA API rate limit (429). Wait about one minute, then retry. "
                    "Avoid running Analyze reviews and consolidate immediately after heavy chat use."
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Consolidator failed: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Consolidator failed: {exc}",
        ) from exc

    duplicate = find_duplicate_rule(
        merge_result.merged_rule,
        get_effective_system_prompt_head(),
        [],
    )
    if duplicate.get("is_duplicate") and not req.force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "duplicate_prompt_rule",
                "duplicate": duplicate,
            },
        )

    id_part = ", ".join(str(i) for i in expected_ids)
    full_rationale = (
        f"{merge_result.rationale.strip()}\n\n"
        f"Superseded override ids: {id_part}"
    ).strip()

    try:
        record, superseded = consolidate_active_prompt_overrides(
            error_type="consolidated",
            suggested_change=f"Merged {len(expected_ids)} active rules",
            approved_change=merge_result.merged_rule.strip(),
            rationale=full_rationale,
            created_by_user_id=user.get("id"),
            expected_superseded_ids=expected_ids,
        )
    except ValueError as exc:
        if str(exc) == "active_override_set_changed":
            raise HTTPException(
                status_code=409,
                detail="active_override_set_changed_retry",
            ) from exc
        raise

    new_id = int(record.get("id") or 0)
    record_prompt_override_audit(
        override_id=new_id,
        action="consolidate",
        actor_user_id=user.get("id"),
        payload={
            "superseded_ids": superseded,
            "model": merge_result.model,
            "force": bool(req.force),
        },
    )
    for sid in superseded or []:
        record_prompt_override_audit(
            override_id=int(sid),
            action="superseded",
            actor_user_id=user.get("id"),
            payload={"by_override_id": new_id},
        )

    return {
        "override": record,
        "superseded_ids": superseded,
        "model": merge_result.model,
    }


@app.post("/api/admin/training-quality/overrides/{override_id}/rollback")
async def api_admin_overrides_rollback(
    override_id: int,
    user: dict = Depends(_require_admin),
) -> dict:
    record = db_rollback_prompt_override(override_id)
    if not record:
        raise HTTPException(status_code=404, detail="Override not active or not found")
    record_prompt_override_audit(
        override_id=int(record.get("id") or override_id),
        action="rollback",
        actor_user_id=user.get("id"),
        payload={"prev_status": "active"},
    )
    return {"override": record}


@app.get("/api/admin/training-quality/overrides/{override_id}/audit")
def api_admin_override_audit(
    override_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(_require_admin),
) -> dict:
    """Lifecycle log for one prompt override (apply/rollback/consolidate)."""
    return {"audit": list_prompt_override_audit(override_id, limit=limit)}


@app.get("/api/admin/training-quality/dedup/audit")
def api_admin_training_quality_dedup_audit(
    window: int = Query(default=20, ge=1, le=100),
    cosine_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    _: dict = Depends(_require_admin),
) -> dict:
    """Dedup tuning aid: replay recent analyzer suggestions through both
    the cheap and the embedding-second-stage filter and return what
    *would* be hidden under the current thresholds versus the requested
    ``cosine_threshold`` override.

    Useful when calibrating ``EMBEDDING_DEDUP_COSINE_THRESHOLD`` after a
    model swap. Reads only — never writes anything to the dedup tables.
    """
    from .config import (
        EMBEDDING_DEDUP_COSINE_THRESHOLD as default_cosine,
        EMBEDDING_DEDUP_LOWER_BOUND,
        EMBEDDING_DEDUP_UPPER_BOUND,
    )
    from .database import (
        get_active_prompt_overrides,
        list_recent_suggestion_decisions,
    )
    from .prompt_rule_embeddings import cache_size, cosine_search
    from .prompt_rule_similarity import (
        SEQUENCE_DUPLICATE_THRESHOLD,
        TOKEN_DUPLICATE_THRESHOLD,
        _sequence_ratio,
        _token_jaccard,
        build_existing_rule_candidates,
    )
    decisions = list_recent_suggestion_decisions(limit=window)
    active = get_active_prompt_overrides()
    candidates = build_existing_rule_candidates(get_effective_system_prompt_head(), active)

    effective_cosine = float(
        cosine_threshold if cosine_threshold is not None else default_cosine
    )

    rows: list[dict[str, Any]] = []
    for d in decisions:
        suggestion = str(d.get("suggested_change") or "").strip()
        if not suggestion:
            continue
        best_seq = 0.0
        best_jac = 0.0
        for cand in candidates:
            text = cand.get("text") or ""
            best_seq = max(best_seq, _sequence_ratio(suggestion, text))
            best_jac = max(best_jac, _token_jaccard(suggestion, text))
        cheap_score = max(best_seq, best_jac)
        cheap_hit = (
            best_seq >= SEQUENCE_DUPLICATE_THRESHOLD
            or best_jac >= TOKEN_DUPLICATE_THRESHOLD
        )
        in_band = (
            EMBEDDING_DEDUP_LOWER_BOUND <= cheap_score < EMBEDDING_DEDUP_UPPER_BOUND
        )
        cosine_score: float | None = None
        embed_match: str | None = None
        if in_band and not cheap_hit:
            score, candidate = cosine_search(suggestion, candidates)
            if candidate is not None:
                cosine_score = round(float(score), 4)
                embed_match = str(candidate.get("text") or "")
        embed_hit = bool(
            cosine_score is not None and cosine_score >= effective_cosine
        )
        rows.append(
            {
                "decision_id": d.get("id"),
                "suggested_change": suggestion[:400],
                "cheap_score": round(float(cheap_score), 4),
                "cheap_hit": bool(cheap_hit),
                "in_borderline_band": bool(in_band),
                "cosine_score": cosine_score,
                "embedding_hit": embed_hit,
                "embedding_match_text": (embed_match or "")[:400] if embed_match else None,
            }
        )

    rows_count, blob_bytes = cache_size()
    return {
        "thresholds": {
            "sequence": SEQUENCE_DUPLICATE_THRESHOLD,
            "token_jaccard": TOKEN_DUPLICATE_THRESHOLD,
            "embedding_lower_bound": EMBEDDING_DEDUP_LOWER_BOUND,
            "embedding_upper_bound": EMBEDDING_DEDUP_UPPER_BOUND,
            "embedding_cosine_default": default_cosine,
            "embedding_cosine_effective": effective_cosine,
        },
        "embedding_cache": {"rows": rows_count, "blob_bytes": blob_bytes},
        "items": rows,
    }


@app.get("/api/admin/training-quality/overrides")
def api_admin_overrides_list(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(_require_admin),
) -> dict:
    items = list_prompt_overrides(status=status, limit=limit)
    # Baseline/after eval accuracy is no longer surfaced (replay supersedes that
    # flow). Columns linger pending Phase 4 migration; the response is trimmed.
    enriched = enrich_prompt_override_rows(list(items))
    return {"overrides": enriched}


@app.get("/api/admin/training-quality/summary")
def api_admin_training_quality_summary(
    _: dict = Depends(_require_admin),
) -> dict:
    """Cheap counters for the new Training Quality landing card.

    Returns how many reviewed examples carry useful signal (edited / rejected /
    note-only) so the UI can show "Co reviewerzy zglosili" without making any
    LLM calls.
    """
    base_head = get_effective_system_prompt_head()

    signals = list_review_signals_for_analysis(limit=200, max_examples_per_group=1)
    active_overrides = list_prompt_overrides(status="active", limit=200)
    active_summaries = []
    for o in active_overrides:
        ch = str(o.get("approved_change") or "").strip()
        one_line = ch.split("\n", 1)[0].strip()
        if len(one_line) > 120:
            one_line = one_line[:119] + "…"
        aff = o.get("affected_example_ids") or []
        active_summaries.append(
            {
                "id": int(o["id"]),
                "error_type": str(o.get("error_type") or ""),
                "one_line_preview": one_line or "—",
                "affected_example_count": len(aff) if isinstance(aff, list) else 0,
            }
        )
    return {
        "total_signals": signals.get("total_signals", 0),
        "edited": signals.get("edited", 0),
        "rejected": signals.get("rejected", 0),
        "notes_only": signals.get("notes_only", 0),
        "groups_count": len(signals.get("groups", [])),
        "generated_at": signals.get("generated_at"),
        "active_prompt_overrides": count_active_prompt_overrides(),
        "max_active_prompt_overrides": MAX_ACTIVE_OVERRIDES,
        "production_prompt": {
            "fingerprint": _prompt_rule_fingerprint(base_head, active_overrides),
            "base_prompt_template_hash": _base_system_prompt_template_fingerprint(
                base_head
            ),
            "active_overrides": active_summaries,
            "active_override_ids": [int(o["id"]) for o in active_overrides],
        },
    }


@app.get("/api/admin/training-quality/system-prompt-head")
def api_admin_training_quality_system_prompt_head(
    _: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Return built-in default, optional DB override flag, and effective base prompt."""
    from .rag import SYSTEM_PROMPT_HEAD

    ov = get_rag_system_prompt_head_override()
    eff = get_effective_system_prompt_head()
    return {
        "builtin_default": SYSTEM_PROMPT_HEAD,
        "override_active": bool(ov and str(ov).strip()),
        "effective": eff,
        "char_count": len(eff or ""),
    }


@app.put("/api/admin/training-quality/system-prompt-head")
def api_admin_training_quality_system_prompt_head_put(
    body: AdminSystemPromptHeadPayload,
    _: dict = Depends(_require_admin),
) -> dict[str, Any]:
    """Save or clear the FM base system prompt (first block in chat; not RAG snippets)."""
    try:
        return set_rag_system_prompt_head_override(body.override_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_analysis_context(llm_profile_id: int | None) -> dict[str, Any]:
    """Common preamble shared by GET (cache-only) and POST (LLM run) analysis."""
    base_head = get_effective_system_prompt_head()

    active_overrides = list_prompt_overrides(status="active", limit=200)
    discarded_for_filter = list_recent_suggestion_decisions(
        decision="rejected", limit=ANALYZER_DISCARD_FILTER_DB_LIMIT
    )
    covered = covered_example_ids_from_active_overrides(active_overrides)
    signals_for_examples = suppress_review_signals(
        list_review_signals_for_analysis(limit=60, max_examples_per_group=5),
        covered,
    )
    qb_tag = question_bank_dedup_cache_tag(active_overrides)
    prof_key = f"p{int(llm_profile_id)}" if llm_profile_id is not None else "pdef"
    cache_key = (
        f"{compute_review_signals_cache_key()}:"
        f"{_prompt_rule_fingerprint(base_head, active_overrides)}:"
        f"{qb_tag}:{prof_key}"
    )
    return {
        "system_prompt": base_head,
        "active_overrides": active_overrides,
        "discarded_for_filter": discarded_for_filter,
        "covered": covered,
        "signals_for_examples": signals_for_examples,
        "cache_key": cache_key,
    }


def _analysis_response_from_cache(
    ctx: dict[str, Any], cached: dict[str, Any] | None
) -> dict[str, Any] | None:
    if cached is None:
        return None
    payload = _finalize_analysis_response(
        cached["result"],
        ctx["system_prompt"],
        ctx["active_overrides"],
        ctx["discarded_for_filter"],
    )
    payload = enrich_analysis_payload_with_supporting_examples(
        payload, ctx["signals_for_examples"]
    )
    return {
        "cached": True,
        "cache_key": ctx["cache_key"],
        "generated_at": cached["created_at"],
        "model": cached["model"],
        **payload,
    }


@app.get("/api/admin/training-quality/analysis")
def api_admin_training_quality_analysis(
    llm_profile_id: int | None = Query(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    """Cache-only read of the latest analyzer output for the current state.

    Never calls the LLM. Returns 404 if there is no cache entry yet — the
    frontend should follow up with POST ``/analysis/run``. This split lets
    the LLM-spawning path stay rate-limited without penalizing reviewers
    who just want to view the most recent suggestions.
    """
    ctx = _build_analysis_context(llm_profile_id)
    cached = get_prompt_analysis_cache(ctx["cache_key"], ANALYZER_CACHE_TTL_HOURS)
    response = _analysis_response_from_cache(ctx, cached)
    if response is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "no_cached_analysis",
                "cache_key": ctx["cache_key"],
                "hint": "POST /api/admin/training-quality/analysis/run to populate.",
            },
        )
    return response


@app.post("/api/admin/training-quality/analysis/run")
@limiter.limit("3/5minute")
async def api_admin_training_quality_analysis_run(
    request: Request,
    llm_profile_id: int | None = Query(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    """Trigger a fresh analyzer LLM run (or return the live cache entry)."""
    from .llm_profiles import resolve_llm_profile_for_task
    from .prompt_analyzer import analyze_pending_async  # local import: heavy module

    ctx = _build_analysis_context(llm_profile_id)
    cached = get_prompt_analysis_cache(ctx["cache_key"], ANALYZER_CACHE_TTL_HOURS)
    if cached is not None:
        cached_response = _analysis_response_from_cache(ctx, cached)
        if cached_response is not None:
            return cached_response

    groups = ctx["signals_for_examples"].get("groups", [])
    _tq_log.debug(
        "analysis run signals total=%s groups=%d covered=%d",
        ctx["signals_for_examples"].get("total_signals"),
        len(groups),
        len(ctx["covered"]),
    )
    if not groups:
        return {
            "cached": False,
            "cache_key": ctx["cache_key"],
            "groups": [],
            "rag_suggestions": [],
            "duplicate_suggestions_hidden": 0,
            "discarded_suggestions_hidden": 0,
            "question_claim_hidden": 0,
            "hidden_suggestions": [],
            "model": None,
            "generated_at": ctx["signals_for_examples"].get("generated_at"),
        }
    discarded_for_llm = ctx["discarded_for_filter"][:ANALYZER_DISCARD_PROMPT_LIMIT]
    _analyzer_budget = (
        float(ANALYZER_MAX_LLM_ATTEMPTS) * float(ANALYZER_LLM_TIMEOUT_SECONDS)
        + float(ANALYZER_REPAIR_BUDGET_SECONDS)
        + 60.0
    )
    _analyzer_effective_deadline = max(
        float(ANALYZER_DEADLINE_SECONDS),
        _analyzer_budget,
    )
    try:
        _obs_log.info(
            "analyzer_llm_start groups=%s deadline_s=%s (env=%s min_budget=%s)",
            len(groups),
            _analyzer_effective_deadline,
            ANALYZER_DEADLINE_SECONDS,
            _analyzer_budget,
        )
        resolved = resolve_llm_profile_for_task(
            "analyzer", profile_id=llm_profile_id
        )
        result = await asyncio.wait_for(
            analyze_pending_async(
                groups,
                ctx["system_prompt"],
                discarded=discarded_for_llm,
                llm_profile=resolved,
            ),
            timeout=_analyzer_effective_deadline,
        )
    except asyncio.TimeoutError as exc:
        _obs_log.warning(
            "prompt analyzer exceeded deadline_s=%s",
            _analyzer_effective_deadline,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Analyzer timed out after {_analyzer_effective_deadline:.0f}s "
                f"(allows {ANALYZER_MAX_LLM_ATTEMPTS}x{ANALYZER_LLM_TIMEOUT_SECONDS}s LLM budget). "
                "Retry shortly; raise ANALYZER_LLM_TIMEOUT_SECONDS or ANALYZER_DEADLINE_SECONDS only "
                "if NVIDIA responses are consistently slow."
            ),
        ) from exc
    except Exception as exc:
        _obs_log.exception("prompt analyzer failed")
        raise HTTPException(status_code=502, detail=f"Analyzer failed: {exc}") from exc
    payload = result.to_dict()
    put_prompt_analysis_cache(ctx["cache_key"], payload, result.model)
    try:
        record_suggestion_affected_from_analysis_payload(payload, ctx["cache_key"])
    except Exception:
        _obs_log.exception("record suggestion_affected events failed")
    fresh = get_prompt_analysis_cache(ctx["cache_key"], ANALYZER_CACHE_TTL_HOURS)
    filtered_payload = _finalize_analysis_response(
        payload, ctx["system_prompt"], ctx["active_overrides"], ctx["discarded_for_filter"]
    )
    filtered_payload = enrich_analysis_payload_with_supporting_examples(
        filtered_payload, ctx["signals_for_examples"]
    )
    return {
        "cached": False,
        "cache_key": ctx["cache_key"],
        "generated_at": fresh["created_at"] if fresh else None,
        "model": result.model,
        **filtered_payload,
    }


class PromptSuggestionDiscardRequest(BaseModel):
    error_type: str = ""
    suggested_change: str
    reason: str = ""
    affected_example_ids: list[int] = []


def _llm_profile_422_detail(exc: ValueError) -> str:
    """Map internal ValueError codes to a short, actionable HTTP message."""
    code = str(exc)
    friendly: dict[str, str] = {
        "inline_llm_keys_disabled": (
            "inline_llm_keys_disabled — Pasted keys are disabled. Set LLM_PROFILES_SECRET in the "
            "backend .env and restart, or set ALLOW_INLINE_LLM_KEYS=true; or leave the API key "
            "empty and use Env alias (e.g. LLM_API_KEY). If you set ALLOW_INLINE_LLM_KEYS=false, "
            "only env alias works."
        ),
        "missing_credentials": (
            "missing_credentials — Set Env alias (e.g. LLM_API_KEY) or paste a key when "
            "LLM_PROFILES_SECRET (or ALLOW_INLINE_LLM_KEYS=true) allows inline storage."
        ),
        "invalid_env_alias": (
            "invalid_env_alias — Use a name like LLM_API_KEY (letters, digits, underscores)."
        ),
    }
    return friendly.get(code, code)


class LlmProfileCreateRequest(BaseModel):
    name: str
    base_url: str
    default_model: str
    provider: str = "openai_compatible"
    api_key: str | None = None
    env_alias: str | None = None


class LlmProfilePatchRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    disabled: bool | None = None
    api_key: str | None = None
    env_alias: str | None = None
    clear_env_alias: bool = False


class LlmTaskDefaultsRequest(BaseModel):
    """Map task name -> profile id (null clears)."""

    defaults: dict[str, int | None]


@app.get("/api/admin/llm/capabilities")
def api_admin_llm_capabilities(_: dict = Depends(_require_admin)) -> dict:
    """Whether the server accepts pasted API keys on profile create/patch."""
    return {"allow_inline_api_keys": bool(ALLOW_INLINE_LLM_KEYS)}


@app.get("/api/admin/llm/profiles")
def api_admin_llm_profiles_list(
    include_disabled: int = Query(default=0, ge=0, le=1),
    _: dict = Depends(_require_admin),
) -> dict:
    rows = list_llm_model_profiles(include_disabled=bool(include_disabled))
    return {"profiles": rows}


@app.post("/api/admin/llm/profiles")
def api_admin_llm_profiles_create(
    req: LlmProfileCreateRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    try:
        row = create_llm_model_profile(
            name=req.name,
            base_url=req.base_url,
            default_model=req.default_model,
            provider=req.provider,
            api_key_plain=req.api_key,
            env_alias=req.env_alias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_llm_profile_422_detail(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": row}


@app.patch("/api/admin/llm/profiles/{profile_id}")
def api_admin_llm_profiles_patch(
    profile_id: int,
    req: LlmProfilePatchRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    try:
        row = update_llm_model_profile(
            profile_id,
            name=req.name,
            base_url=req.base_url,
            default_model=req.default_model,
            disabled=req.disabled,
            api_key_plain=req.api_key,
            env_alias=req.env_alias,
            clear_env_alias=req.clear_env_alias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_llm_profile_422_detail(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"profile": row}


@app.delete("/api/admin/llm/profiles/{profile_id}")
def api_admin_llm_profiles_delete(
    profile_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    ok = delete_llm_model_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"ok": True}


@app.get("/api/admin/llm/task-defaults")
def api_admin_llm_task_defaults_get(_: dict = Depends(_require_admin)) -> dict:
    return {"defaults": list_llm_task_defaults()}


@app.put("/api/admin/llm/task-defaults")
def api_admin_llm_task_defaults_put(
    req: LlmTaskDefaultsRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    for task, pid in req.defaults.items():
        set_llm_task_default(task, pid)
    return {"defaults": list_llm_task_defaults()}


@app.post("/api/admin/llm/profiles/{profile_id}/probe")
async def api_admin_llm_profile_probe(
    profile_id: int,
    request: Request,
    mode_query: str | None = Query(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    from .llm_profile_diag import run_profile_diagnostic
    from .llm_profiles import resolve_llm_profile_for_task

    if not get_llm_model_profile(int(profile_id)):
        raise HTTPException(status_code=404, detail="Profile not found")

    m = "quick"
    try:
        raw_bytes = await request.body()
        if raw_bytes.strip():
            payload = json.loads(raw_bytes.decode("utf-8"))
            if isinstance(payload, dict):
                raw = str(payload.get("mode", "")).strip().lower()
                if raw in {"quick", "full"}:
                    m = raw
    except Exception:
        pass
    if m == "quick" and mode_query is not None and str(mode_query).strip():
        mq = str(mode_query).strip().lower()
        if mq in {"quick", "full"}:
            m = mq
    if m not in {"quick", "full"}:
        raise HTTPException(
            status_code=422,
            detail="mode must be 'quick' or 'full'",
        )

    if m == "full":
        try:
            return await run_profile_diagnostic(int(profile_id))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        resolved = resolve_llm_profile_for_task("chat", profile_id=int(profile_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        reply = await achat(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            max_tokens=256,
            timeout=float(LLM_HEALTH_TIMEOUT_SECONDS),
            max_retries=0,
            resolved=resolved,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "mode": "quick",
        "snippet": (reply or "").strip()[:80],
        "base_url": resolved.base_url,
        "model": resolved.default_model,
    }


@app.get("/api/admin/training-quality/question-bank")
def api_admin_training_quality_question_bank(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    only_covered: bool = Query(default=False),
    only_with_override: bool = Query(default=False),
    only_recent_hours: int | None = Query(default=None),
    _: dict = Depends(_require_admin),
) -> dict:
    rows, total = list_question_bank_rows(
        limit=limit,
        offset=offset,
        q=q,
        only_covered=only_covered,
        only_with_override=only_with_override,
        only_recent_hours=only_recent_hours,
    )
    return {"rows": rows, "total": total, "offset": offset, "limit": limit}


@app.post("/api/admin/training-quality/suggestions/discard")
def api_admin_training_quality_suggestion_discard(
    req: PromptSuggestionDiscardRequest,
    user: dict = Depends(_require_admin),
) -> dict:
    """Record an analyzer suggestion the reviewer chose to discard.

    The next analyzer run reads recent rejections and includes them in the
    prompt so the LLM avoids re-suggesting equivalent rules.
    """
    if not req.suggested_change.strip():
        raise HTTPException(status_code=400, detail="suggested_change is required")
    record = record_prompt_suggestion_decision(
        error_type=req.error_type,
        suggested_change=req.suggested_change,
        decision="rejected",
        reason=req.reason,
        affected_example_ids=req.affected_example_ids,
        created_by_user_id=user.get("id"),
    )
    return {"decision": record}


class PromptOverrideReplayRequest(BaseModel):
    max_inputs: int = 6
    paraphrases_per_input: int = 3
    llm_profile_id: int | None = None


def _replay_preflight(
    override_id: int, req: PromptOverrideReplayRequest
) -> tuple[dict, int, int, int]:
    """Shared pre-flight checks for both POST and SSE replay handlers.

    Returns ``(override_record, max_inputs, paraphrases, predicted_calls)``.
    Raises ``HTTPException`` on 404 / 429.
    """
    from .llm import rpm_status
    from .prompt_replay import predicted_replay_call_count

    record = get_prompt_override(int(override_id))
    if not record:
        raise HTTPException(status_code=404, detail="Override not found")
    max_inputs = max(1, min(20, int(req.max_inputs or 0) or 6))
    paraphrases = max(0, min(5, int(req.paraphrases_per_input or 0)))

    affected = list(record.get("affected_example_ids") or [])
    effective_inputs = min(max_inputs, len(affected)) if affected else 0
    predicted_calls = predicted_replay_call_count(effective_inputs, paraphrases)
    status = rpm_status()
    remaining = max(0, int(status.get("budget", 0)) - int(status.get("used_last_60s", 0)))
    if predicted_calls > 0 and remaining < predicted_calls:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Replay would issue ~{predicted_calls} LLM calls but only "
                f"{remaining} slots remain in the current 60s window. "
                "Wait a moment and retry."
            ),
        )
    return record, max_inputs, paraphrases, predicted_calls


@app.post("/api/admin/training-quality/overrides/{override_id}/replay")
@limiter.limit("1/5minute")
async def api_admin_training_quality_override_replay(
    request: Request,
    override_id: int,
    req: PromptOverrideReplayRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    """Run a mini-replay of an active override on its affected examples plus
    paraphrases of each. Each replay item is also persisted into
    `training_examples` (source_type='prompt_replay') so it shows up in the
    review queue and the reviewer can spot regressions.

    Pre-flight: rejects with 429 if the predicted LLM call count would
    exceed the remaining NVIDIA RPM budget. The handler itself is also
    rate-limited per user to one run every 5 minutes.
    """
    from .llm_profiles import resolve_llm_profile_for_task
    from .prompt_replay import replay_for_override  # local import: heavy module

    _record, max_inputs, paraphrases, _predicted = _replay_preflight(override_id, req)
    try:
        summary = await replay_for_override(
            int(override_id),
            max_inputs=max_inputs,
            paraphrases_per_input=paraphrases,
            llm_profile=resolve_llm_profile_for_task(
                "replay", profile_id=req.llm_profile_id
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _obs_log.exception("replay_for_override failed")
        raise HTTPException(status_code=502, detail=f"Replay failed: {exc}") from exc

    set_prompt_override_replay_summary(
        int(override_id),
        {
            "total_original": summary.total_original,
            "passed_original": summary.passed_original,
            "total_paraphrases": summary.total_paraphrases,
            "passed_paraphrases": summary.passed_paraphrases,
            "examples_logged": summary.examples_logged,
            "ran_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"summary": summary.to_dict()}


@app.post("/api/admin/training-quality/overrides/{override_id}/replay/stream")
@limiter.limit("1/5minute")
async def api_admin_training_quality_override_replay_stream(
    request: Request,
    override_id: int,
    req: PromptOverrideReplayRequest,
    _: dict = Depends(_require_admin),
) -> StreamingResponse:
    """SSE variant of the replay endpoint.

    Emits one ``data: {...json...}\\n\\n`` event per progress update from
    :func:`prompt_replay.stream_replay_for_override` so the admin UI can
    show per-question progress instead of waiting on a single blocking
    POST. Final ``summary`` event is also persisted on the override row
    so subsequent ``/overrides`` list calls show the same numbers.
    """
    from .llm_profiles import resolve_llm_profile_for_task
    from .prompt_replay import stream_replay_for_override  # heavy module

    _record, max_inputs, paraphrases, _predicted = _replay_preflight(override_id, req)
    profile = resolve_llm_profile_for_task("replay", profile_id=req.llm_profile_id)

    async def _event_source():
        try:
            async for event in stream_replay_for_override(
                int(override_id),
                max_inputs=max_inputs,
                paraphrases_per_input=paraphrases,
                llm_profile=profile,
            ):
                if event.get("type") == "summary":
                    summary = event.get("summary") or {}
                    try:
                        set_prompt_override_replay_summary(
                            int(override_id),
                            {
                                "total_original": int(summary.get("total_original") or 0),
                                "passed_original": int(summary.get("passed_original") or 0),
                                "total_paraphrases": int(summary.get("total_paraphrases") or 0),
                                "passed_paraphrases": int(summary.get("passed_paraphrases") or 0),
                                "examples_logged": int(summary.get("examples_logged") or 0),
                                "ran_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    except Exception:
                        _obs_log.exception(
                            "set_prompt_override_replay_summary failed (override=%s)",
                            override_id,
                        )
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception as exc:
            _obs_log.exception("stream_replay_for_override failed")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/admin/training-examples/{example_id}")
def api_admin_training_example_by_id(
    example_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    item = get_training_example(example_id)
    if not item:
        raise HTTPException(status_code=404, detail="Training example not found")
    return {"example": item}


@app.patch("/api/admin/training-examples/{example_id}")
def api_admin_training_example_update(
    example_id: int,
    req: AdminTrainingExampleUpdateRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    try:
        item = update_training_example_review(
            example_id,
            correction_type=req.correction_type,
            ideal_output=req.ideal_output,
            human_notes=req.human_notes,
            context_used=req.context_used,
            reasoning=req.reasoning,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Training example not found")
    return {"example": item}


@app.post("/api/admin/training-examples/bulk-review")
def api_admin_training_bulk_review(
    req: AdminTrainingBulkReviewRequest,
    confirm: bool = Query(default=False),
    dry_run: bool = Query(default=False),
    _: dict = Depends(_require_admin),
) -> dict:
    if not dry_run and not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Bulk update affects many rows. Pass ?confirm=true to apply, or ?dry_run=true to preview only."
            ),
        )
    payload = req.model_dump(exclude_unset=True)
    ids = payload.get("ids", [])
    updates: dict[str, Any] = {}
    if "human_notes" in payload:
        v = payload["human_notes"]
        updates["human_notes"] = "" if v is None else str(v)
    if "reasoning" in payload:
        v = payload["reasoning"]
        updates["reasoning"] = "" if v is None else str(v)
    if "correction_type" in payload:
        ct = str(payload["correction_type"] or "").strip()
        updates["correction_type"] = ct
    try:
        result = bulk_update_training_examples_review(ids, updates, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


def _normalize_export_correction_types(raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        ct = str(item).strip().lower()
        if ct == "corrected":
            ct = "edited"
        if not ct or ct in seen:
            continue
        if ct not in ALLOWED_CORRECTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid correction_type {ct!r}. Allowed: {', '.join(sorted(ALLOWED_CORRECTION_TYPES))}",
            )
        seen.add(ct)
        out.append(ct)
    if not out:
        raise HTTPException(status_code=400, detail="At least one correction_type is required.")
    return out


@app.get("/api/admin/training-examples/export")
def api_admin_training_examples_export(
    correction_types: str = Query(default="approved,edited"),
    _: dict = Depends(_require_admin),
) -> Response:
    include = [x.strip().lower() for x in correction_types.split(",") if x.strip()]
    if not include:
        include = ["approved", "edited"]
    try:
        include = _normalize_export_correction_types(include)
    except HTTPException:
        raise
    data = export_training_examples_jsonl(include_correction_types=include)
    return Response(content=data, media_type="application/x-ndjson")


@app.post("/api/admin/training-examples/export")
def api_admin_training_examples_export_post(
    body: AdminTrainingExamplesExportRequest,
    _: dict = Depends(_require_admin),
) -> Response:
    try:
        cts = _normalize_export_correction_types(body.correction_types)
    except HTTPException:
        raise
    id_list = body.ids
    if id_list is not None:
        clean_ids: list[int] = []
        seen_i: set[int] = set()
        for raw in id_list:
            try:
                i = int(raw)
            except (TypeError, ValueError):
                continue
            if i <= 0 or i in seen_i:
                continue
            seen_i.add(i)
            clean_ids.append(i)
        if len(clean_ids) > TRAINING_EXPORT_MAX_IDS:
            raise HTTPException(
                status_code=400,
                detail=f"Too many ids (max {TRAINING_EXPORT_MAX_IDS}).",
            )
        id_list = clean_ids or None
    if body.id_min is not None and body.id_max is not None and body.id_min > body.id_max:
        raise HTTPException(status_code=400, detail="id_min must be <= id_max.")
    ca = (body.created_after or "").strip() or None
    cb = (body.created_before or "").strip() or None
    try:
        data = export_training_examples_jsonl(
            include_correction_types=cts,
            example_ids=id_list,
            id_min=body.id_min,
            id_max=body.id_max,
            created_after=ca,
            created_before=cb,
            include_actual_output=bool(body.include_actual_output),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=data, media_type="application/x-ndjson")


@app.post("/api/admin/training-examples/backfill/tickets")
def api_admin_training_examples_backfill_tickets(
    limit: int = Query(default=5000, ge=1, le=200000),
    _: dict = Depends(_require_admin),
) -> dict:
    result = backfill_training_examples_from_tickets(limit=limit)
    return {"ok": True, "result": result}


@app.post("/api/admin/training-examples/backfill/tests")
def api_admin_training_examples_backfill_tests(
    test_results_path: str = Query(default="test_results_full.json"),
    _: dict = Depends(_require_admin),
) -> dict:
    candidate = Path(test_results_path)
    if not candidate.is_absolute():
        candidate = (_backend_root() / candidate).resolve()
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Test results file not found: {candidate}")
    result = backfill_training_examples_from_test_results(str(candidate))
    return {"ok": True, "result": result, "path": str(candidate)}


@app.get("/api/admin/training-examples/v1/manifest")
def api_admin_training_examples_v1_manifest(
    _: dict = Depends(_require_admin),
) -> dict:
    view = build_v1_dataset_view()
    return {"manifest": view["manifest"]}


@app.get("/api/admin/training-examples/v1/exports")
def api_admin_training_examples_v1_exports(
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(_require_admin),
) -> dict:
    base = Path(TRAINING_DATA_DIR)
    if not base.is_absolute():
        base = (_backend_root() / base).resolve()
    items: list[dict[str, Any]] = []
    if base.exists():
        for p in base.iterdir():
            if not p.is_file():
                continue
            name = p.name
            if not (
                name.startswith("fine_tuning_v1_")
                or name.startswith("fine_tuning_v1.")
                or name.endswith(".jsonl")
                or name.endswith(".csv")
            ):
                continue
            st = p.stat()
            items.append(
                {
                    "name": name,
                    "path": str(p),
                    "size_bytes": int(st.st_size),
                    "updated_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                }
            )
    items.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
    return {"exports": items[:limit], "dir": str(base)}


@app.get("/api/admin/training-examples/v1/export-jsonl")
def api_admin_training_examples_v1_export_jsonl(
    mode: str = Query(default="train"),  # train | candidates
    _: dict = Depends(_require_admin),
) -> Response:
    view = build_v1_dataset_view()
    if mode == "candidates":
        rows = list(view["all_rows"])
    else:
        rows = list(view["train_rows"])
    data = export_v1_jsonl(rows)
    return Response(content=data, media_type="application/x-ndjson")


@app.get("/api/admin/training-examples/v1/export-csv")
def api_admin_training_examples_v1_export_csv(
    _: dict = Depends(_require_admin),
) -> Response:
    view = build_v1_dataset_view()
    data = export_v1_review_csv(list(view["review_rows"]))
    return Response(content=data, media_type="text/csv")


@app.post("/api/admin/training-examples/v1/build-files")
def api_admin_training_examples_v1_build_files(
    req: AdminV1BuildRequest,
    _: dict = Depends(_require_admin),
) -> dict:
    test_path = Path(req.test_results_path)
    if not test_path.is_absolute():
        test_path = (_backend_root() / test_path).resolve()
    # DB-first mode: build-files only regenerates export artifacts from SQLite.
    out_dir = Path(req.output_dir)
    if not out_dir.is_absolute():
        out_dir = (_backend_root() / out_dir).resolve()
    result = write_v1_dataset_files(str(out_dir))
    result["test_results_path"] = str(test_path)
    return result


@app.post("/api/admin/training-examples/v1/mark-all-edited")
def api_admin_training_examples_mark_all_edited(
    confirm: bool = Query(default=False),
    _: dict = Depends(_require_admin),
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Destructive bulk action. Pass ?confirm=true to acknowledge that this will "
                "rewrite correction_type for many rows."
            ),
        )
    result = mass_mark_all_edited_if_any_custom_reasoning()
    return {"ok": True, **result}


@app.get("/api/admin/training-examples/v1/sync-check")
def api_admin_training_examples_sync_check(
    _: dict = Depends(_require_admin),
) -> dict:
    db_rows = get_training_examples(limit=200000, offset=0)
    db_ids = {int(r.get("id", 0) or 0) for r in db_rows if int(r.get("id", 0) or 0) > 0}
    view = build_v1_dataset_view()
    json_ids = {int(r.get("id", 0) or 0) for r in list(view.get("all_rows", [])) if int(r.get("id", 0) or 0) > 0}
    missing_in_json = sorted(list(db_ids - json_ids))
    missing_in_db = sorted(list(json_ids - db_ids))
    return {
        "ok": True,
        "db_count": len(db_ids),
        "json_count": len(json_ids),
        "missing_in_json_count": len(missing_in_json),
        "missing_in_db_count": len(missing_in_db),
        "missing_in_json_sample": missing_in_json[:50],
        "missing_in_db_sample": missing_in_db[:50],
    }


@app.post("/api/admin/training-examples/v1/rebuild-json-store")
def api_admin_training_examples_rebuild_json_store(
    _: dict = Depends(_require_admin),
) -> dict:
    result = rebuild_json_store_from_db()
    return {"ok": True, **result}


@app.post("/api/admin/training-examples/v1/prune-to-review-policy")
def api_admin_training_examples_prune_to_review_policy(
    _: dict = Depends(_require_admin),
) -> dict:
    result = prune_training_examples_for_review_policy()
    return {"ok": True, **result}


@app.post("/api/admin/training-examples/v1/cleanup-now")
def api_admin_training_examples_cleanup_now(
    _: dict = Depends(_require_admin),
) -> dict:
    result = cleanup_training_examples_and_candidates()
    return {"ok": True, **result}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
