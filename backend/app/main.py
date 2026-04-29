from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
import uvicorn
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .classifier import fallback_response, parse_llm_json
from .config import (
    AUTH_SESSION_COOKIE,
    AUTH_SESSION_TTL_HOURS,
    DOCS_DIR,
    LLM_MODEL,
    NVIDIA_API_KEY,
    RAG_TOP_K,
    TRAINING_DATA_AUTO_REFRESH,
    TRAINING_DATA_AUTO_REFRESH_SECONDS,
    TRAINING_DATA_DIR,
)
from .doc_extract import UPLOAD_ALLOWED_EXTENSIONS, extract_text_from_upload
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
    append_chat_exchange,
    start_new_chat_thread,
    ticket_stats,
    update_knowledge_gap,
    update_ticket_status,
    update_training_example_review,
    update_user_admin_fields,
    export_training_examples_jsonl,
    backfill_training_examples_from_tickets,
    backfill_training_examples_from_test_results,
    build_v1_dataset_view,
    export_v1_jsonl,
    export_v1_review_csv,
    rebuild_json_store_from_db,
    write_v1_dataset_files,
)
from .ingest import run_ingest
from .llm import chat, embed
from .rag import generate, generate_stream, retrieve_with_sources
from .training_json_store import (
    bootstrap_from_examples,
    get_candidate_for_api,
    list_candidates_for_api,
    mass_mark_all_edited_if_any_custom_reasoning,
    update_candidate_review_for_api,
)


app = FastAPI(title="FM Chatbot Backend")
_DATASET_REFRESH_THREAD_STARTED = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    run_id: str = ""
    source_type: str = ""
    source_id: str = ""
    source_ref: str = ""


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


class KnowledgeGapUpdateRequest(BaseModel):
    status: str
    notes: str | None = None


class KnowledgeGapResolveRequest(BaseModel):
    doc_name: str
    category: str = "General"
    content: str
    mode: str = "append"  # append | overwrite
    auto_reindex: bool = True


class AdminTrainingExampleUpdateRequest(BaseModel):
    correction_type: str
    ideal_output: dict | None = None
    human_notes: str | None = None
    context_used: list[str] | None = None
    reasoning: str | None = None


class AdminV1BuildRequest(BaseModel):
    test_results_path: str = "test_results_full.json"
    output_dir: str = "data"


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
    "napraw",
    "fix",
    "repair",
    "check",
    "sprawdz",
    "replace",
    "wymien",
    "interwenc",
    "service",
}
INCIDENT_HINTS = {
    "awaria",
    "leak",
    "wyciek",
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
    "dym",
    "brak",
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
    "dziala",
    "działa",
    "dzieki",
    "dzięki",
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
                pass
            time.sleep(interval)

    th = threading.Thread(target=_runner, name="training-dataset-refresh", daemon=True)
    th.start()
    _DATASET_REFRESH_THREAD_STARTED = True


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


def _history_from_active_chat(user: dict, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        return list(fallback)
    try:
        payload = list_active_chat_messages(user_id, limit=60)
    except Exception:
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
    words = _tokens(message)
    category = str(payload.get("category", "General") or "General")
    priority = str(payload.get("priority", "NORMAL") or "NORMAL").upper()
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
        return True
    if words.issubset(ACK_HINTS):
        return True
    # Short "confirmation only" messages should never create knowledge gaps.
    normalized = " ".join(message.strip().split())
    return len(normalized) <= 28 and bool(words & ACK_HINTS)


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


def _finalize_chat_payload(
    req: ChatRequest,
    payload: dict,
    context: list[str],
    sources: list[str],
    user: dict,
) -> dict:
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
        heuristic_input = f"{conversation_text}\nUser: {req.message}".strip()
        should_create_ticket = _should_auto_create_ticket(
            heuristic_input,
            query_type,
            payload.get("in_scope", "YES"),
        ) and query_type in AUTO_TICKET_QUERY_TYPES
    else:
        heuristic_input = f"{conversation_text}\nUser: {req.message}".strip()
        should_create_ticket = _should_auto_create_ticket(
            heuristic_input, query_type, payload.get("in_scope", "YES")
        )
    if hidden_issue and payload.get("in_scope") == "YES":
        should_create_ticket = True
        if query_type == "INFORMATIONAL":
            query_type = "INCIDENT"
    elif info_lookup or followup_status:
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
    issue_summary = _fallback_issue_summary(payload.get("issue_summary", ""))
    if issue_summary == "No issue summary provided.":
        issue_summary = _fallback_issue_summary(req.message)
    ticket_id: int | None = None
    if should_create_ticket:
        ticket = create_ticket(
            message=req.message,
            issue_summary=issue_summary,
            category=payload["category"],
            priority=payload["priority"],
            department=payload["department"],
            response=payload["response"],
            created_by_user_id=user.get("id"),
        )
        ticket_id = ticket["id"]
        try:
            mail_notify.notify_ticket_created(ticket, user.get("username"))
        except Exception:
            pass
    payload["context_count"] = len(context)
    payload["used_sources"] = sources
    payload["query_type"] = query_type
    payload["ticket_created"] = should_create_ticket
    payload["ticket_id"] = ticket_id
    payload["issue_summary"] = issue_summary
    heuristic_input = f"{conversation_text}\nUser: {req.message}".strip()
    should_log_knowledge_gap = (
        payload.get("in_scope") == "YES"
        and payload.get("grounded") == "NO"
        and query_type == "INFORMATIONAL"
        and not should_create_ticket
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
        "create_ticket": bool(should_create_ticket),
        "response": payload.get("response", ""),
        "issue_summary": issue_summary,
    }
    try:
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
            ticket_created=bool(should_create_ticket),
            ticket_id=ticket_id,
            model=LLM_MODEL,
            run_id=req.run_id.strip(),
            source_type=req.source_type.strip() or "chat_log",
            source_id=req.source_id.strip(),
            source_ref=req.source_ref.strip(),
            knowledge_gap_logged=bool(should_log_knowledge_gap),
            knowledge_gap_reason=gap_reason,
        )
    except Exception:
        # Training log must not break chat flow.
        pass
    try:
        append_chat_exchange(
            int(user.get("id") or 0),
            req.message,
            str(payload.get("response", "") or ""),
        )
    except Exception:
        # Chat history persistence must not break chat flow.
        pass
    return payload


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        bootstrap_from_examples(get_training_examples(limit=200000, offset=0))
    except Exception:
        pass
    _start_training_dataset_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    if not NVIDIA_API_KEY:
        return {"status": "warning", "message": "Missing NVIDIA_API_KEY"}
    try:
        reply = chat([{"role": "user", "content": "Reply with: ok"}], temperature=0)
        return {"status": "ok", "provider": "nvidia_nim", "probe": reply.strip()}
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "message": str(exc)}


@app.post("/api/chat")
def api_chat(req: ChatRequest, user: dict = Depends(_require_auth)) -> dict:
    try:
        req.history = _history_from_active_chat(user, req.history)
        context, sources = retrieve_with_sources(req.message, k=RAG_TOP_K)
        raw_response = generate(req.message, context, req.history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        payload = parse_llm_json(raw_response)
    except Exception:
        payload = fallback_response(raw_response)
    # Safety net: if the LLM marks an obviously FM query as out-of-scope,
    # treat it as in-scope but not grounded so it lands in knowledge gaps.
    if payload.get("in_scope") == "NO" and _looks_like_fm_query(req.message):
        payload["in_scope"] = "YES"
        payload["grounded"] = "NO"
        payload["response"] = (
            "I can help only with Facility Management topics. "
            "This FM question is not covered well enough in the current documentation yet."
        )
    return _finalize_chat_payload(req, payload, context, sources, user)


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest, user: dict = Depends(_require_auth)) -> StreamingResponse:
    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    def generate_events():
        try:
            req.history = _history_from_active_chat(user, req.history)
            context, sources = retrieve_with_sources(req.message, k=RAG_TOP_K)
            raw = ""
            streamed_len = 0
            for chunk in generate_stream(req.message, context, req.history):
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
            if payload.get("in_scope") == "NO" and _looks_like_fm_query(req.message):
                payload["in_scope"] = "YES"
                payload["grounded"] = "NO"
                payload["response"] = (
                    "I can help only with Facility Management topics. "
                    "This FM question is not covered well enough in the current documentation yet."
                )
            final_payload = _finalize_chat_payload(req, payload, context, sources, user)
            final_response = final_payload.get("response", "")
            if isinstance(final_response, str) and len(final_response) > streamed_len:
                yield event(
                    {"type": "chunk", "delta": final_response[streamed_len:]}
                )
            yield event({"type": "final", "payload": final_payload})
        except Exception as exc:
            yield event({"type": "error", "message": str(exc)})

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
def api_embed(req: EmbedRequest) -> dict:
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
        samesite="lax",
        secure=False,
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
        pass
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
        pass
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


@app.post("/api/admin/reindex")
def api_admin_reindex(_: dict = Depends(_require_admin)) -> dict:
    try:
        count = run_ingest()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"chunks_indexed": count}


@app.post("/api/admin/upload")
async def api_admin_upload(
    file: UploadFile = File(...),
    overwrite: bool = Form(default=True),
    auto_reindex: bool = Form(default=False),
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

    target_name = f"{_safe_stem(filename)}.md"
    path = _doc_path(target_name)
    if path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="Target document already exists")
    path.write_text(text, encoding="utf-8")
    reindex_count: int | None = None
    if auto_reindex:
        try:
            reindex_count = run_ingest()
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
        samesite="lax",
        secure=False,
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
            chunks_indexed = run_ingest()
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
    rows = list_candidates_for_api(
        correction_type=correction_type,
        user_role=user_role,
        limit=limit,
        offset=offset,
    )
    return {"examples": rows}


@app.get("/api/admin/training-examples/{example_id}")
def api_admin_training_example_by_id(
    example_id: int,
    _: dict = Depends(_require_admin),
) -> dict:
    item = get_candidate_for_api(example_id)
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
        item = update_candidate_review_for_api(
            example_id=example_id,
            correction_type=req.correction_type,
            ideal_output=req.ideal_output,
            human_notes=req.human_notes,
            context_used=req.context_used,
            reasoning=req.reasoning,
        )
        # Keep SQLite mirrored for operational compatibility.
        try:
            update_training_example_review(
                example_id,
                correction_type=req.correction_type,
                ideal_output=req.ideal_output,
                human_notes=req.human_notes,
                context_used=req.context_used,
                reasoning=req.reasoning,
            )
        except Exception:
            pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Training example not found")
    return {"example": item}


@app.get("/api/admin/training-examples/export")
def api_admin_training_examples_export(
    correction_types: str = Query(default="approved,edited"),
    _: dict = Depends(_require_admin),
) -> Response:
    include = [x.strip() for x in correction_types.split(",") if x.strip()]
    if not include:
        include = ["approved", "edited"]
    data = export_training_examples_jsonl(include_correction_types=include)
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
    # JSON-first mode: build-files does not run backfills.
    # New records should come only from normal chat/test flows and manual review edits.
    out_dir = Path(req.output_dir)
    if not out_dir.is_absolute():
        out_dir = (_backend_root() / out_dir).resolve()
    result = write_v1_dataset_files(str(out_dir))
    result["test_results_path"] = str(test_path)
    return result


@app.post("/api/admin/training-examples/v1/mark-all-edited")
def api_admin_training_examples_mark_all_edited(
    _: dict = Depends(_require_admin),
) -> dict:
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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
