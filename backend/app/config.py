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

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_EMBED_API_KEY = os.getenv("NVIDIA_EMBED_API_KEY", NVIDIA_API_KEY)
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/llama-nemotron-embed-1b-v2")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
# Hard ceiling for LLM HTTP calls; prevents event loop / threads from waiting forever.
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
# Short timeout used only by /health/llm probe so monitors don't hang.
LLM_HEALTH_TIMEOUT_SECONDS = int(os.getenv("LLM_HEALTH_TIMEOUT_SECONDS", "5"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
# LRU size for query embeddings in RAG (0 = disable cache).
RAG_QUERY_EMBED_CACHE_SIZE = int(os.getenv("RAG_QUERY_EMBED_CACHE_SIZE", "192"))
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
DOCS_DIR = os.getenv("DOCS_DIR", "docs_fm")
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

# Hard cap on outbound NVIDIA RPM (chat + embed + analyzer + eval all share
# this token bucket). NVIDIA's account-wide limit is 40 RPM, leave 5 as buffer.
NVIDIA_RPM_BUDGET = int(os.getenv("NVIDIA_RPM_BUDGET", "35"))

# Faza D: prompt analyzer settings.
# Defaults to the same chat model so a fresh deploy works without extra config.
# For better suggestions, set LLM_ANALYZER_MODEL to a stronger NIM model.
LLM_ANALYZER_MODEL = os.getenv("LLM_ANALYZER_MODEL", LLM_MODEL)
ANALYZER_MAX_GROUPS = int(os.getenv("ANALYZER_MAX_GROUPS", "4"))
ANALYZER_MAX_EXAMPLES_PER_GROUP = int(os.getenv("ANALYZER_MAX_EXAMPLES_PER_GROUP", "5"))
ANALYZER_CACHE_TTL_HOURS = int(os.getenv("ANALYZER_CACHE_TTL_HOURS", "24"))

# Faza E: prompt override safeguards.
# Cap on simultaneously active overrides to force consolidation; analyzer
# suggestions with confidence below this floor must be manually edited before apply.
MAX_ACTIVE_OVERRIDES = int(os.getenv("MAX_ACTIVE_OVERRIDES", "5"))
OVERRIDE_MIN_CONFIDENCE = float(os.getenv("OVERRIDE_MIN_CONFIDENCE", "0.5"))
EVAL_BASELINE_MAX_AGE_HOURS = int(os.getenv("EVAL_BASELINE_MAX_AGE_HOURS", "24"))
