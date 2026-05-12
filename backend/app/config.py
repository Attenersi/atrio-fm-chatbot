import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
ALT_ENV_FILE = BASE_DIR / "env"
load_dotenv(dotenv_path=ENV_FILE)
# Backward compatibility: many local setups keep variables in `backend/env`.
if ALT_ENV_FILE.exists():
    load_dotenv(dotenv_path=ALT_ENV_FILE, override=False)


def _env_str(*keys: str, default: str = "") -> str:
    """Return the first non-empty environment value among ``keys`` (order matters)."""
    for key in keys:
        raw = os.getenv(key)
        if raw is not None:
            s = str(raw).strip()
            if s:
                return s
    return default


def _env_int(*keys: str, default: int) -> int:
    for key in keys:
        raw = os.getenv(key)
        if raw is not None and str(raw).strip():
            return int(raw)
    return default


def _env_float(*keys: str, default: float) -> float:
    for key in keys:
        raw = os.getenv(key)
        if raw is not None and str(raw).strip():
            return float(raw)
    return default


_DEFAULT_LLM_BASE_URL = "https://integrate.api.nvidia.com/v1"

# OpenAI-compatible API (any vendor). Prefer LLM_*; NVIDIA_* remains supported.
LLM_API_KEY = _env_str("LLM_API_KEY", "NVIDIA_API_KEY")
LLM_EMBED_API_KEY = _env_str("LLM_EMBED_API_KEY", "NVIDIA_EMBED_API_KEY") or LLM_API_KEY
LLM_BASE_URL = _env_str("LLM_BASE_URL", "NVIDIA_BASE_URL", default=_DEFAULT_LLM_BASE_URL)
LLM_MODEL = os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/llama-nemotron-embed-1b-v2")
# Some OpenAI-compatible vendors only allow a fixed sampling temperature per model
# (handled in app.llm._effective_chat_temperature for Moonshot Kimi).
LLM_TEMPERATURE = max(0.0, min(2.0, _env_float("LLM_TEMPERATURE", default=0.2)))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
# Hard ceiling for LLM HTTP calls; prevents event loop / threads from waiting forever.
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
# Short timeout used only by /health/llm probe so monitors don't hang.
LLM_HEALTH_TIMEOUT_SECONDS = int(os.getenv("LLM_HEALTH_TIMEOUT_SECONDS", "5"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
# Text splitter defaults for Chroma ingest (see ingest.run_ingest).
INGEST_CHUNK_SIZE = _env_int("INGEST_CHUNK_SIZE", default=1200)
INGEST_CHUNK_OVERLAP = _env_int("INGEST_CHUNK_OVERLAP", default=150)
# LRU size for query embeddings in RAG (0 = disable cache).
RAG_QUERY_EMBED_CACHE_SIZE = int(os.getenv("RAG_QUERY_EMBED_CACHE_SIZE", "192"))
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
DOCS_DIR = os.getenv("DOCS_DIR", "docs_fm")
# Strip/redact obvious instruction-like lines in uploaded docs before index (see doc_sanitize.py).
DOCS_SANITIZE_INSTRUCTION_LIKE = os.getenv(
    "DOCS_SANITIZE_INSTRUCTION_LIKE", "true"
).strip().lower() in {"1", "true", "yes", "on"}
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "tickets.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
AUTH_SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "8"))
AUTH_SESSION_COOKIE = os.getenv("AUTH_SESSION_COOKIE", "fm_session")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
_samesite_raw = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower() or "lax"
# Starlette accepts only {"lax", "strict", "none"}; anything else would 500 set_cookie.
AUTH_COOKIE_SAMESITE = _samesite_raw if _samesite_raw in {"lax", "strict", "none"} else "lax"
AUTH_BOOTSTRAP_USER_USERNAME = os.getenv("AUTH_BOOTSTRAP_USER_USERNAME", "user")
# No default password: production must set AUTH_BOOTSTRAP_USER_PASSWORD explicitly,
# otherwise the bootstrap non-admin account is not created.
AUTH_BOOTSTRAP_USER_PASSWORD = os.getenv("AUTH_BOOTSTRAP_USER_PASSWORD", "")
TRAINING_DATA_DIR = os.getenv("TRAINING_DATA_DIR", "data")
TRAINING_DATA_AUTO_REFRESH = os.getenv("TRAINING_DATA_AUTO_REFRESH", "1")
TRAINING_DATA_AUTO_REFRESH_SECONDS = int(os.getenv("TRAINING_DATA_AUTO_REFRESH_SECONDS", "30"))

# Optional SMTP (ticket notifications). Leave SMTP_HOST empty to disable sends.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "").strip()
ADMIN_NOTIFY_EMAIL = os.getenv("ADMIN_NOTIFY_EMAIL", "").strip()
# all | urgent | off — who gets "new ticket" emails (admin list only)
MAIL_NOTIFY_NEW_TICKETS = os.getenv("MAIL_NOTIFY_NEW_TICKETS", "all").strip()

# Browser CORS: by default only localhost / 127.0.0.1 are allowed (with credentials).
# To open up to LAN/`*.local` (e.g. when testing across phones on Wi-Fi), set
# CORS_ALLOW_ORIGIN_REGEX explicitly in the env.
_DEFAULT_CORS_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
_cors_env = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
CORS_ALLOW_ORIGIN_REGEX = _cors_env if _cors_env else _DEFAULT_CORS_REGEX

# Rate limits (slowapi syntax: "<count>/<period>"). Keys are user_id when
# authenticated, IP otherwise.
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "30/minute")
RATE_LIMIT_EMBED = os.getenv("RATE_LIMIT_EMBED", "60/minute")

# Hard cap on outbound LLM RPM (chat + embed + analyzer + eval share this bucket).
# Legacy NVIDIA_* env names still apply when LLM_* unset.
LLM_RPM_BUDGET = _env_int("LLM_RPM_BUDGET", "NVIDIA_RPM_BUDGET", default=35)
# achat() waits and retries when the provider returns HTTP 429.
LLM_429_RETRY_ATTEMPTS = _env_int("LLM_429_RETRY_ATTEMPTS", "NVIDIA_429_RETRY_ATTEMPTS", default=5)
LLM_429_RETRY_BASE_SECONDS = _env_float(
    "LLM_429_RETRY_BASE_SECONDS", "NVIDIA_429_RETRY_BASE_SECONDS", default=10.0
)

# Deprecated aliases — resolved via LLM_* / legacy NVIDIA_* above. Prefer LLM_* in new .env files.
NVIDIA_API_KEY = LLM_API_KEY
NVIDIA_EMBED_API_KEY = LLM_EMBED_API_KEY
NVIDIA_BASE_URL = LLM_BASE_URL
NVIDIA_RPM_BUDGET = LLM_RPM_BUDGET
NVIDIA_429_RETRY_ATTEMPTS = LLM_429_RETRY_ATTEMPTS
NVIDIA_429_RETRY_BASE_SECONDS = LLM_429_RETRY_BASE_SECONDS

# Faza D: prompt analyzer settings.
# Defaults to the same chat model so a fresh deploy works without extra config.
# For better suggestions, set LLM_ANALYZER_MODEL to a stronger NIM model.
LLM_ANALYZER_MODEL = os.getenv("LLM_ANALYZER_MODEL", LLM_MODEL)
# Analyzer returns a JSON object with several rule strings; the chat default
# LLM_MAX_TOKENS (often 512) truncates mid-JSON and causes parse errors.
ANALYZER_MAX_OUTPUT_TOKENS = int(os.getenv("ANALYZER_MAX_OUTPUT_TOKENS", "3072"))
ANALYZER_MAX_GROUPS = int(os.getenv("ANALYZER_MAX_GROUPS", "4"))
ANALYZER_MAX_EXAMPLES_PER_GROUP = int(os.getenv("ANALYZER_MAX_EXAMPLES_PER_GROUP", "5"))
ANALYZER_CACHE_TTL_HOURS = int(os.getenv("ANALYZER_CACHE_TTL_HOURS", "24"))
# Analyzer may retry LLM when JSON parsing fails; deadline must allow all attempts
# (each up to ANALYZER_LLM_TIMEOUT_SECONDS) plus a little slack for RPM wait.
ANALYZER_MAX_LLM_ATTEMPTS = int(os.getenv("ANALYZER_MAX_LLM_ATTEMPTS", "2"))
ANALYZER_LLM_TIMEOUT_SECONDS = int(os.getenv("ANALYZER_LLM_TIMEOUT_SECONDS", "120"))
# Reserved for the optional JSON-repair LLM call after normal attempts fail.
ANALYZER_REPAIR_BUDGET_SECONDS = int(
    os.getenv("ANALYZER_REPAIR_BUDGET_SECONDS", "120")
)
_default_analyzer_deadline = (
    ANALYZER_MAX_LLM_ATTEMPTS * ANALYZER_LLM_TIMEOUT_SECONDS
    + ANALYZER_REPAIR_BUDGET_SECONDS
    + 90
)
ANALYZER_DEADLINE_SECONDS = int(
    os.getenv("ANALYZER_DEADLINE_SECONDS", str(_default_analyzer_deadline))
)

# Faza E: prompt override safeguards.
# Cap on simultaneously active overrides to force consolidation; analyzer
# suggestions with confidence below this floor must be manually edited before apply.
MAX_ACTIVE_OVERRIDES = int(os.getenv("MAX_ACTIVE_OVERRIDES", "5"))
OVERRIDE_MIN_CONFIDENCE = float(os.getenv("OVERRIDE_MIN_CONFIDENCE", "0.5"))
EVAL_BASELINE_MAX_AGE_HOURS = int(os.getenv("EVAL_BASELINE_MAX_AGE_HOURS", "24"))

# Question-bank dedup for analyzer: "active_only" uses only live prompt coverage;
# "include_history" also treats training examples ever tied to an applied override
# (including superseded) as claimed for suggestion filtering.
QUESTION_BANK_DEDUP_SCOPE = os.getenv("QUESTION_BANK_DEDUP_SCOPE", "include_history").strip().lower()
if QUESTION_BANK_DEDUP_SCOPE not in {"active_only", "include_history"}:
    QUESTION_BANK_DEDUP_SCOPE = "include_history"

# Fernet key material for encrypting LLM profile API keys in SQLite (see llm_crypto).
LLM_PROFILES_SECRET = os.getenv("LLM_PROFILES_SECRET", "").strip()
# Tri-state ``ALLOW_INLINE_LLM_KEYS`` (pasted API key into admin profile form):
# - explicit false (0, false, no, off): never persist inline keys, even if secret is set
# - explicit true (1, true, yes, on): allow inline keys (encryption still needs secret + db_salt)
# - unset: allow inline keys iff ``LLM_PROFILES_SECRET`` is set (single-knob encrypted storage)
_allow_inline_raw = os.getenv("ALLOW_INLINE_LLM_KEYS", "").strip().lower()
if _allow_inline_raw in {"0", "false", "no", "off"}:
    ALLOW_INLINE_LLM_KEYS = False
elif _allow_inline_raw in {"1", "true", "yes", "on"}:
    ALLOW_INLINE_LLM_KEYS = True
else:
    ALLOW_INLINE_LLM_KEYS = bool(LLM_PROFILES_SECRET)

# ---------------------------------------------------------------------------
# Training Quality tunables (moved out of module-level constants).
# All thresholds and caps used by the analyzer pipeline / replay / dedup live
# here so reviewers can adjust them without code edits.
# ---------------------------------------------------------------------------

# How many recently-rejected analyzer suggestions to load from the DB for
# post-LLM filtering (server-side only; not all are forwarded to the LLM).
ANALYZER_DISCARD_FILTER_DB_LIMIT = int(
    os.getenv("ANALYZER_DISCARD_FILTER_DB_LIMIT", "80")
)
# How many recently-rejected analyzer suggestions are inlined into the LLM
# system prompt as "do not repeat these ideas".
ANALYZER_DISCARD_PROMPT_LIMIT = int(
    os.getenv("ANALYZER_DISCARD_PROMPT_LIMIT", "12")
)

# Max supporting training examples attached per analyzer group / RAG suggestion
# in the response payload (training_quality_analysis_enrich).
SUPPORTING_EXAMPLES_CAP = int(os.getenv("SUPPORTING_EXAMPLES_CAP", "12"))

# Heuristic clustering threshold used by the consolidator before feeding the
# merge LLM. Higher = stricter grouping (fewer, larger clusters).
CONSOLIDATE_LINE_CLUSTER_THRESHOLD = float(
    os.getenv("CONSOLIDATE_LINE_CLUSTER_THRESHOLD", "0.62")
)

# Duplicate detection thresholds for analyzer suggestions and apply-time
# duplicate-rule check (prompt_rule_similarity).
SEQUENCE_DUPLICATE_THRESHOLD = float(
    os.getenv("SEQUENCE_DUPLICATE_THRESHOLD", "0.82")
)
TOKEN_DUPLICATE_THRESHOLD = float(
    os.getenv("TOKEN_DUPLICATE_THRESHOLD", "0.72")
)

# Replay defaults (override via the request body in the admin UI).
REPLAY_DEFAULT_MAX_INPUTS = int(os.getenv("REPLAY_DEFAULT_MAX_INPUTS", "8"))
REPLAY_DEFAULT_PARAPHRASES = int(os.getenv("REPLAY_DEFAULT_PARAPHRASES", "3"))
# Hard upper bound the replay endpoint enforces irrespective of request body
# (protects the global RPM bucket from one-click LLM blasts).
REPLAY_MAX_LLM_CALLS = int(os.getenv("REPLAY_MAX_LLM_CALLS", "40"))

# Cache + event sweep cadence (Phase 1 background maintenance).
CACHE_SWEEP_INTERVAL_SECONDS = int(os.getenv("CACHE_SWEEP_INTERVAL_SECONDS", "3600"))
EVENT_LOG_KEEP_PER_KIND = int(os.getenv("EVENT_LOG_KEEP_PER_KIND", "10"))

# Phase 4: embedding-based dedup (second-stage filter).
# When the cheap token+sequence pre-filter (prompt_rule_similarity) returns a
# borderline score in ``[lower, upper]``, the analyzer asks
# ``prompt_rule_embeddings.cosine_search`` for a final verdict. Scores below
# ``lower`` are kept; scores at or above ``upper`` are already classified as
# duplicates by the cheap pass.
EMBEDDING_DEDUP_ENABLED = os.getenv(
    "EMBEDDING_DEDUP_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
EMBEDDING_DEDUP_LOWER_BOUND = float(
    os.getenv("EMBEDDING_DEDUP_LOWER_BOUND", "0.50")
)
EMBEDDING_DEDUP_UPPER_BOUND = float(
    os.getenv("EMBEDDING_DEDUP_UPPER_BOUND", "0.85")
)
# Cosine similarity at or above this counts as an embedding-confirmed duplicate
# in the borderline band. Calibrated against NV embed model defaults; tune in
# admin /dedup/audit.
EMBEDDING_DEDUP_COSINE_THRESHOLD = float(
    os.getenv("EMBEDDING_DEDUP_COSINE_THRESHOLD", "0.86")
)

# One user message may yield multiple maintenance tickets when the model lists
# separate actionable issues in ``issues`` (see rag.SYSTEM_PROMPT_HEAD).
MULTI_TICKET_PER_MESSAGE_ENABLED = os.getenv(
    "MULTI_TICKET_PER_MESSAGE_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
CHAT_MULTI_ISSUE_MAX = int(os.getenv("CHAT_MULTI_ISSUE_MAX", "5"))

# Chat input/output guardrails (prompt injection). See chat_injection_guard.py, chat_output_guard.py.
CHAT_INJECTION_REGEX_ENABLED = os.getenv(
    "CHAT_INJECTION_REGEX_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
_chat_inj_mode = os.getenv("CHAT_INJECTION_REGEX_MODE", "conservative").strip().lower()
CHAT_INJECTION_REGEX_MODE = _chat_inj_mode if _chat_inj_mode in {"conservative", "strict"} else "conservative"
CHAT_INJECTION_LLM_FILTER = os.getenv(
    "CHAT_INJECTION_LLM_FILTER", "false"
).strip().lower() in {"1", "true", "yes", "on"}
CHAT_INJECTION_LLM_FILTER_FAIL_CLOSED = os.getenv(
    "CHAT_INJECTION_LLM_FILTER_FAIL_CLOSED", "false"
).strip().lower() in {"1", "true", "yes", "on"}
LLM_INJECTION_FILTER_MODEL = _env_str("LLM_INJECTION_FILTER_MODEL", default="").strip() or LLM_MODEL
LLM_INJECTION_FILTER_TIMEOUT_SECONDS = float(
    os.getenv("LLM_INJECTION_FILTER_TIMEOUT_SECONDS", "12")
)
LLM_INJECTION_FILTER_MAX_TOKENS = int(os.getenv("LLM_INJECTION_FILTER_MAX_TOKENS", "12"))
CHAT_INJECTION_CANNED_RESPONSE = _env_str("CHAT_INJECTION_CANNED_RESPONSE", default="").strip()
# Comma-separated substrings (case-insensitive) to flag in model response text; default none.
CHAT_OUTPUT_SENSITIVE_TERMS: tuple[str, ...] = tuple(
    t.strip().lower()
    for t in (_env_str("CHAT_OUTPUT_SENSITIVE_TERMS", default="").split(","))
    if t.strip()
)
