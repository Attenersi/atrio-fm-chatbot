import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_EMBED_API_KEY = os.getenv("NVIDIA_EMBED_API_KEY", NVIDIA_API_KEY)
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/llama-nemotron-embed-1b-v2")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
DOCS_DIR = os.getenv("DOCS_DIR", "docs_fm")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "tickets.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
AUTH_SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "8"))
AUTH_SESSION_COOKIE = os.getenv("AUTH_SESSION_COOKIE", "fm_session")
AUTH_BOOTSTRAP_USER_USERNAME = os.getenv("AUTH_BOOTSTRAP_USER_USERNAME", "user")
AUTH_BOOTSTRAP_USER_PASSWORD = os.getenv("AUTH_BOOTSTRAP_USER_PASSWORD", "user")
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
