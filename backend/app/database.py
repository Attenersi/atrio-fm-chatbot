from __future__ import annotations

import sqlite3
import hashlib
import hmac
import csv
import json
import logging
import secrets
import uuid
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_db_log = logging.getLogger("fm.observability")

from .config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    AUTH_BOOTSTRAP_USER_PASSWORD,
    AUTH_BOOTSTRAP_USER_USERNAME,
    AUTH_SESSION_TTL_HOURS,
    SQLITE_DB_PATH,
    TRAINING_DATA_AUTO_REFRESH,
    TRAINING_DATA_AUTO_REFRESH_SECONDS,
    TRAINING_DATA_DIR,
)


ALLOWED_STATUS = {"Open", "In Progress", "Resolved"}
ALLOWED_GAP_STATUS = {"new", "reviewed", "resolved"}
ALLOWED_CORRECTION_TYPES = {"pending", "approved", "edited", "rejected"}
ALLOWED_SOURCE_TYPES = {"chat_log", "ticket", "test_case"}
ALLOWED_OVERRIDE_FIELDS = {"category", "priority", "department"}
_AUTO_REFRESH_LOCK = threading.Lock()
_LAST_AUTO_REFRESH_TS = 0.0
STATUS_ALIASES = {
    "open": "Open",
    "in progress": "In Progress",
    "in_progress": "In Progress",
    "inprogress": "In Progress",
    "resolved": "Resolved",
}


def normalize_status(value: str) -> str:
    normalized = STATUS_ALIASES.get(value.strip().lower(), value.strip())
    return normalized


def get_conn() -> sqlite3.Connection:
    db_file = Path(SQLITE_DB_PATH)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    # WAL: better read concurrency; busy_timeout reduces "database is locked" under dev load.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def _normalize_input_text(value: str) -> str:
    cleaned = " ".join((value or "").strip().lower().split())
    return cleaned


def _include_in_review_candidates_jsonl(item: dict[str, Any]) -> bool:
    """Rows exported to fine_tuning_v1_candidates.jsonl: test cases, edited rows, chat turns that created a ticket."""
    source_type = str(item.get("source_type", "") or "")
    correction = str(item.get("correction_type", "") or "").lower()
    ticket_created = bool(item.get("ticket_created", False))
    if source_type == "test_case":
        return True
    if correction == "edited":
        return True
    if source_type == "chat_log" and ticket_created:
        return True
    return False


def _auto_refresh_v1_dataset_files() -> None:
    global _LAST_AUTO_REFRESH_TS
    if str(TRAINING_DATA_AUTO_REFRESH).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    if not _AUTO_REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        now = time.monotonic()
        min_interval = max(0, int(TRAINING_DATA_AUTO_REFRESH_SECONDS))
        if min_interval > 0 and (now - _LAST_AUTO_REFRESH_TS) < min_interval:
            return
        try:
            write_v1_dataset_files(TRAINING_DATA_DIR)
            _LAST_AUTO_REFRESH_TS = now
        except Exception:
            # Dataset export should never break primary DB operations,
            # but it must surface in logs so we can diagnose later.
            _db_log.exception("write_v1_dataset_files failed in auto-refresh")
    finally:
        _AUTO_REFRESH_LOCK.release()


def _hash_password(password: str, salt: str | None = None) -> str:
    password = password or ""
    used_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        used_salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"{used_salt}${digest}"


def _verify_password(password: str, encoded: str) -> bool:
    if "$" not in encoded:
        return False
    salt, digest = encoded.split("$", 1)
    expected = _hash_password(password, salt)
    return hmac.compare_digest(expected, f"{salt}${digest}")


def _ensure_default_user(conn: sqlite3.Connection, username: str, password: str, role: str) -> None:
    row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        if role == "admin":
            conn.execute(
                "UPDATE users SET role = 'admin', is_active = 1 WHERE id = ?",
                (row["id"],),
            )
        return
    conn.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
        """,
        (username, _hash_password(password), role, _utc_now_iso()),
    )


def _get_user_id_by_username(conn: sqlite3.Connection, username: str) -> int | None:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    return int(row["id"])


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                issue_summary TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                department TEXT NOT NULL,
                response TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_by_user_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                ticket_id INTEGER,
                category TEXT NOT NULL DEFAULT 'General',
                response TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_text TEXT NOT NULL,
                normalized_input TEXT NOT NULL DEFAULT '',
                actual_output_json TEXT NOT NULL,
                ideal_output_json TEXT NOT NULL DEFAULT '',
                human_notes TEXT NOT NULL DEFAULT '',
                correction_type TEXT NOT NULL DEFAULT 'pending',
                context_used_json TEXT NOT NULL DEFAULT '[]',
                reasoning TEXT NOT NULL DEFAULT '',
                used_sources_json TEXT NOT NULL DEFAULT '[]',
                context_count INTEGER NOT NULL DEFAULT 0,
                query_type TEXT NOT NULL DEFAULT '',
                in_scope TEXT NOT NULL DEFAULT '',
                grounded TEXT NOT NULL DEFAULT '',
                ticket_created INTEGER NOT NULL DEFAULT 0,
                ticket_id INTEGER,
                user_id INTEGER,
                user_role TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                run_id TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT 'chat_log',
                source_id TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                knowledge_gap_logged INTEGER NOT NULL DEFAULT 0,
                knowledge_gap_reason TEXT NOT NULL DEFAULT '',
                mismatch_fields TEXT NOT NULL DEFAULT '[]',
                expected_payload TEXT NOT NULL DEFAULT '{}',
                actual_payload TEXT NOT NULL DEFAULT '{}',
                retrieval_meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resolution_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                added_by TEXT NOT NULL DEFAULT '',
                parts_used TEXT NOT NULL DEFAULT '',
                cost REAL,
                time_spent_minutes INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classification_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                field_changed TEXT NOT NULL,
                ai_value TEXT NOT NULL,
                manager_value TEXT NOT NULL,
                changed_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
            """
        )
        # Lightweight migration for older DBs created before category column.
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(knowledge_gaps)").fetchall()
        }
        if "category" not in cols:
            conn.execute(
                "ALTER TABLE knowledge_gaps ADD COLUMN category TEXT NOT NULL DEFAULT 'General'"
            )
        ticket_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
        }
        if "issue_summary" not in ticket_cols:
            conn.execute(
                "ALTER TABLE tickets ADD COLUMN issue_summary TEXT NOT NULL DEFAULT ''"
            )
        if "created_by_user_id" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN created_by_user_id INTEGER")
        user_cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        tr_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(training_examples)").fetchall()
        }
        if "model" not in tr_cols:
            conn.execute("ALTER TABLE training_examples ADD COLUMN model TEXT NOT NULL DEFAULT ''")
        if "run_id" not in tr_cols:
            conn.execute("ALTER TABLE training_examples ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")
        if "normalized_input" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN normalized_input TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "UPDATE training_examples SET normalized_input = lower(trim(input_text)) WHERE normalized_input = ''"
            )
        if "source_type" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN source_type TEXT NOT NULL DEFAULT 'chat_log'"
            )
        if "source_id" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN source_id TEXT NOT NULL DEFAULT ''"
            )
        if "source_ref" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''"
            )
        if "knowledge_gap_logged" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN knowledge_gap_logged INTEGER NOT NULL DEFAULT 0"
            )
        if "knowledge_gap_reason" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN knowledge_gap_reason TEXT NOT NULL DEFAULT ''"
            )
        if "mismatch_fields" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN mismatch_fields TEXT NOT NULL DEFAULT '[]'"
            )
        if "expected_payload" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN expected_payload TEXT NOT NULL DEFAULT '{}'"
            )
        if "actual_payload" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN actual_payload TEXT NOT NULL DEFAULT '{}'"
            )
        if "retrieval_meta" not in tr_cols:
            conn.execute(
                "ALTER TABLE training_examples ADD COLUMN retrieval_meta TEXT NOT NULL DEFAULT '{}'"
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_training_examples_source
            ON training_examples(source_type, source_id, source_ref)
            WHERE source_id != ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_training_examples_correction_type
            ON training_examples(correction_type)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_override_active_ids TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                accuracy_overall REAL,
                accuracy_category REAL,
                accuracy_priority REAL,
                accuracy_ticket_created REAL,
                accuracy_response_tokens REAL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                details_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_eval_runs_status
            ON eval_runs(status)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_analysis_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                suggested_change TEXT NOT NULL DEFAULT '',
                approved_change TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                affected_example_ids TEXT NOT NULL DEFAULT '[]',
                created_by_user_id INTEGER,
                created_at TEXT NOT NULL,
                activated_at TEXT,
                deactivated_at TEXT,
                eval_baseline_id INTEGER,
                eval_after_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_prompt_overrides_status
            ON prompt_overrides(status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_training_examples_norm_input
            ON training_examples(normalized_input)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_threads_user_active
            ON chat_threads(user_id, is_active, updated_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created
            ON chat_messages(thread_id, created_at ASC)
            """
        )
        _ensure_default_user(conn, ADMIN_USERNAME, ADMIN_PASSWORD or "admin", "admin")
        if AUTH_BOOTSTRAP_USER_PASSWORD:
            _ensure_default_user(
                conn,
                AUTH_BOOTSTRAP_USER_USERNAME,
                AUTH_BOOTSTRAP_USER_PASSWORD,
                "user",
            )
        else:
            _db_log.warning(
                "AUTH_BOOTSTRAP_USER_PASSWORD not set; skipping default user bootstrap"
            )
        admin_user_id = _get_user_id_by_username(conn, ADMIN_USERNAME)
        if admin_user_id is not None:
            # Backfill legacy rows created before ownership enforcement.
            conn.execute(
                "UPDATE tickets SET created_by_user_id = ? WHERE created_by_user_id IS NULL",
                (admin_user_id,),
            )
        conn.commit()


def create_ticket(
    *,
    message: str,
    issue_summary: str,
    category: str,
    priority: str,
    department: str,
    response: str,
    created_by_user_id: int,
) -> dict[str, Any]:
    if created_by_user_id <= 0:
        raise ValueError("created_by_user_id is required")
    created_at = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tickets (message, issue_summary, category, priority, department, response, status, created_by_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Open', ?, ?)
            """,
            (message, issue_summary, category, priority, department, response, created_by_user_id, created_at),
        )
        ticket_id = cur.lastrowid
        conn.commit()
    return get_ticket(ticket_id)


def get_ticket(ticket_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.*, u.username AS created_by_username
            FROM tickets t
            LEFT JOIN users u ON u.id = t.created_by_user_id
            WHERE t.id = ?
            """,
            (ticket_id,),
        ).fetchone()
    return dict(row) if row else {}


def get_tickets(
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    created_by_user_id: int | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT t.*, u.username AS created_by_username
        FROM tickets t
        LEFT JOIN users u ON u.id = t.created_by_user_id
        WHERE 1=1
    """
    params: list[Any] = []
    if category:
        query += " AND t.category = ?"
        params.append(category)
    if priority:
        query += " AND t.priority = ?"
        params.append(priority)
    if status:
        status = normalize_status(status)
        query += " AND t.status = ?"
        params.append(status)
    if created_by_user_id is not None:
        query += " AND t.created_by_user_id = ?"
        params.append(created_by_user_id)
    query += " ORDER BY t.id DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_ticket_status(ticket_id: int, status: str) -> dict[str, Any]:
    status = normalize_status(status)
    if status not in ALLOWED_STATUS:
        raise ValueError(
            "Invalid status. Allowed values: Open, In Progress, Resolved"
        )
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status = ? WHERE id = ?",
            (status, ticket_id),
        )
        conn.commit()
    return get_ticket(ticket_id)


def update_ticket_classification(
    ticket_id: int,
    *,
    category: str | None = None,
    priority: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    existing = get_ticket(ticket_id)
    if not existing:
        return {}
    next_category = (category or existing.get("category") or "General").strip() or "General"
    next_priority = (priority or existing.get("priority") or "NORMAL").strip() or "NORMAL"
    next_department = (department or existing.get("department") or "Facility Management").strip() or "Facility Management"
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tickets
            SET category = ?, priority = ?, department = ?
            WHERE id = ?
            """,
            (next_category, next_priority, next_department, ticket_id),
        )
        conn.commit()
    return get_ticket(ticket_id)


def create_resolution_note(
    *,
    ticket_id: int,
    note: str,
    added_by: str = "",
    parts_used: str = "",
    cost: float | None = None,
    time_spent_minutes: int | None = None,
) -> dict[str, Any]:
    if not note.strip():
        raise ValueError("Resolution note is required")
    created_at = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO resolution_notes (ticket_id, note, added_by, parts_used, cost, time_spent_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                note.strip(),
                added_by.strip(),
                parts_used.strip(),
                cost,
                time_spent_minutes,
                created_at,
            ),
        )
        note_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("SELECT * FROM resolution_notes WHERE id = ?", (note_id,)).fetchone()
    return dict(row) if row else {}


def get_resolution_notes(ticket_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM resolution_notes WHERE ticket_id = ? ORDER BY id DESC",
            (ticket_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_classification_overrides(ticket_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM classification_overrides WHERE ticket_id = ? ORDER BY id DESC",
            (ticket_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_classification_override(
    *,
    ticket_id: int,
    field_changed: str,
    manager_value: str,
    changed_by: str = "",
) -> dict[str, Any]:
    field = field_changed.strip().lower()
    if field not in ALLOWED_OVERRIDE_FIELDS:
        raise ValueError("Invalid field_changed. Allowed: category, priority, department")
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket not found")
    ai_value = str(ticket.get(field, "") or "")
    manager_clean = manager_value.strip()
    if not manager_clean:
        raise ValueError("manager_value is required")
    created_at = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO classification_overrides (ticket_id, field_changed, ai_value, manager_value, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, field, ai_value, manager_clean, changed_by.strip(), created_at),
        )
        override_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("SELECT * FROM classification_overrides WHERE id = ?", (override_id,)).fetchone()
    return dict(row) if row else {}


def _sync_training_examples_from_override(
    *,
    ticket_id: int,
    changed_by: str,
    field_changed: str,
    manager_value: str,
) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM training_examples WHERE ticket_id = ? ORDER BY id DESC",
            (ticket_id,),
        ).fetchall()
        updated = 0
        for row in rows:
            item = _hydrate_training_example(row)
            ideal = dict(item.get("ideal_output") or item.get("actual_output") or {})
            actual = dict(item.get("actual_output") or {})
            if field_changed == "category":
                ideal["category"] = manager_value
            elif field_changed == "priority":
                ideal["priority"] = manager_value
            elif field_changed == "department":
                ideal["department"] = manager_value
            if "create_ticket" not in ideal:
                ideal["create_ticket"] = bool(actual.get("create_ticket", True))
            if "response" not in ideal:
                ideal["response"] = actual.get("response", "")
            if "issue_summary" not in ideal:
                ideal["issue_summary"] = actual.get("issue_summary", "")
            existing_notes = str(item.get("human_notes", "") or "").strip()
            note_suffix = (
                f"Override by {changed_by or 'manager'}: "
                f"{field_changed} => {manager_value}."
            )
            human_notes = f"{existing_notes} {note_suffix}".strip()
            conn.execute(
                """
                UPDATE training_examples
                SET correction_type = 'edited',
                    ideal_output_json = ?,
                    human_notes = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (_json_dump(ideal), human_notes, _utc_now_iso(), int(row["id"])),
            )
            updated += 1
        conn.commit()
    return updated


def apply_classification_override(
    *,
    ticket_id: int,
    field_changed: str,
    manager_value: str,
    changed_by: str = "",
) -> dict[str, Any]:
    field = field_changed.strip().lower()
    override = create_classification_override(
        ticket_id=ticket_id,
        field_changed=field,
        manager_value=manager_value,
        changed_by=changed_by,
    )
    ticket_kwargs: dict[str, str] = {}
    if field == "category":
        ticket_kwargs["category"] = manager_value
    elif field == "priority":
        ticket_kwargs["priority"] = manager_value
    else:
        ticket_kwargs["department"] = manager_value
    ticket = update_ticket_classification(ticket_id, **ticket_kwargs)
    training_examples_updated = _sync_training_examples_from_override(
        ticket_id=ticket_id,
        changed_by=changed_by,
        field_changed=field,
        manager_value=manager_value,
    )
    _auto_refresh_v1_dataset_files()
    return {
        "ticket": ticket,
        "override": override,
        "training_examples_updated": training_examples_updated,
    }


def ticket_stats(created_by_user_id: int | None = None) -> dict[str, Any]:
    where_clause = ""
    params: list[Any] = []
    urgent_query = "SELECT COUNT(*) FROM tickets WHERE priority = 'URGENT'"
    urgent_params: list[Any] = []
    if created_by_user_id is not None:
        where_clause = " WHERE created_by_user_id = ?"
        params = [created_by_user_id]
        urgent_query += " AND created_by_user_id = ?"
        urgent_params = [created_by_user_id]
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    trend_query = """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS count
        FROM tickets
        WHERE created_at >= ?
    """
    trend_params: list[Any] = [since]
    if created_by_user_id is not None:
        trend_query += " AND created_by_user_id = ?"
        trend_params.append(created_by_user_id)
    trend_query += " GROUP BY day ORDER BY day"
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM tickets{where_clause}",
            params,
        ).fetchone()[0]
        urgent = conn.execute(urgent_query, urgent_params).fetchone()[0]
        by_category_rows = conn.execute(
            f"SELECT category, COUNT(*) AS count FROM tickets{where_clause} GROUP BY category",
            params,
        ).fetchall()
        by_priority_rows = conn.execute(
            f"SELECT priority, COUNT(*) AS count FROM tickets{where_clause} GROUP BY priority",
            params,
        ).fetchall()
        by_day_rows = conn.execute(trend_query, trend_params).fetchall()
    by_day = {str(row["day"]): int(row["count"]) for row in by_day_rows}

    return {
        "total": total,
        "urgent": urgent,
        "by_category": {row["category"]: row["count"] for row in by_category_rows},
        "by_priority": {row["priority"]: row["count"] for row in by_priority_rows},
        "by_day": by_day,
    }


def create_knowledge_gap(
    *,
    question: str,
    ticket_id: int | None,
    category: str,
    response: str,
    notes: str = "",
) -> dict[str, Any]:
    created_at = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO knowledge_gaps (question, ticket_id, category, response, status, notes, created_at, resolved_at)
            VALUES (?, ?, ?, ?, 'new', ?, ?, NULL)
            """,
            (question, ticket_id, category, response, notes, created_at),
        )
        gap_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)).fetchone()
    return dict(row) if row else {}


def get_knowledge_gaps(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM knowledge_gaps WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_knowledge_gap(gap_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)).fetchone()
    return dict(row) if row else {}


def update_knowledge_gap(
    gap_id: int,
    status: str,
    notes: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_GAP_STATUS:
        raise ValueError("Invalid gap status. Allowed: new, reviewed, resolved")
    resolved_at = _utc_now_iso() if status == "resolved" else None
    with get_conn() as conn:
        if notes is None and category is None:
            conn.execute(
                """
                UPDATE knowledge_gaps
                SET status = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, resolved_at, gap_id),
            )
        elif category is None:
            conn.execute(
                """
                UPDATE knowledge_gaps
                SET status = ?, notes = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, notes, resolved_at, gap_id),
            )
        else:
            conn.execute(
                """
                UPDATE knowledge_gaps
                SET status = ?, notes = COALESCE(?, notes), category = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, notes, category, resolved_at, gap_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)).fetchone()
    return dict(row) if row else {}


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, role, is_active, created_at, email
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row or not row["is_active"]:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    user = dict(row)
    user.pop("password_hash", None)
    return user


def create_user_account(username: str, password: str, role: str = "user") -> dict[str, Any]:
    cleaned_username = username.strip()
    if not cleaned_username:
        raise ValueError("Username is required")
    if len(cleaned_username) < 3:
        raise ValueError("Username must have at least 3 characters")
    if role != "user":
        raise ValueError("Only user accounts can be created")
    if not password or len(password) < 6:
        raise ValueError("Password must have at least 6 characters")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (cleaned_username,),
        ).fetchone()
        if existing:
            raise ValueError("Username already exists")
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at)
            VALUES (?, ?, 'user', 1, ?)
            """,
            (cleaned_username, _hash_password(password), _utc_now_iso()),
        )
        user_id = cur.lastrowid
        conn.commit()
    user = get_user_by_id(int(user_id))
    if not user:
        raise ValueError("Could not create user")
    return user


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active, created_at, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, is_active, created_at, email
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def update_user_admin_fields(
    user_id: int,
    *,
    role: str | None = None,
    is_active: int | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Admin-only updates. Preserves at least one active admin. Raises ValueError on rule violations."""
    current = get_user_by_id(user_id)
    if not current:
        raise ValueError("User not found")
    new_role = role if role is not None else str(current["role"])
    new_active = is_active if is_active is not None else int(current["is_active"])
    if new_role not in {"admin", "user"}:
        raise ValueError("Invalid role")
    new_active = 1 if new_active else 0

    new_email: str | None
    if email is not None:
        cleaned = email.strip()
        new_email = cleaned if cleaned else None
    else:
        new_email = current.get("email")
        if isinstance(new_email, str) and not new_email.strip():
            new_email = None

    with get_conn() as conn:
        other_admins = conn.execute(
            """
            SELECT COUNT(*) FROM users
            WHERE id != ? AND role = 'admin' AND is_active = 1
            """,
            (user_id,),
        ).fetchone()[0]
        this_stays_admin = new_role == "admin" and new_active == 1
        admins_after = int(other_admins) + (1 if this_stays_admin else 0)
        if admins_after < 1:
            raise ValueError("Cannot remove the last active admin")

        conn.execute(
            """
            UPDATE users
            SET role = ?, is_active = ?, email = ?
            WHERE id = ?
            """,
            (new_role, new_active, new_email, user_id),
        )
        conn.commit()
    updated = get_user_by_id(user_id)
    if not updated:
        raise ValueError("User not found after update")
    return updated


def create_session(user_id: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=max(1, AUTH_SESSION_TTL_HOURS))
    session_id = uuid.uuid4().hex
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_id, expires.isoformat(), now.isoformat()),
        )
        conn.commit()
    return {
        "id": session_id,
        "user_id": user_id,
        "expires_at": expires.isoformat(),
        "created_at": now.isoformat(),
    }


def get_session(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.id, s.user_id, s.expires_at, s.created_at, u.username, u.role, u.is_active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= datetime.now(timezone.utc) or not row["is_active"]:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return None
    return dict(row)


def delete_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def _to_chat_message_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "thread_id": int(row["thread_id"]),
        "role": str(row["role"]),
        "content": str(row["content"]),
        "created_at": str(row["created_at"]),
    }


def _to_chat_thread_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "is_active": bool(row["is_active"]),
        "title": str(row["title"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _ensure_active_chat_thread(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT * FROM chat_threads
        WHERE user_id = ? AND is_active = 1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()
    if row:
        return _to_chat_thread_row(row)
    now = _utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO chat_threads (user_id, is_active, title, created_at, updated_at)
        VALUES (?, 1, '', ?, ?)
        """,
        (int(user_id), now, now),
    )
    thread_id = int(cur.lastrowid)
    row = conn.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,)).fetchone()
    return _to_chat_thread_row(row) if row else {}


def start_new_chat_thread(user_id: int) -> dict[str, Any]:
    now = _utc_now_iso()
    with get_conn() as conn:
        conn.execute("UPDATE chat_threads SET is_active = 0 WHERE user_id = ?", (int(user_id),))
        cur = conn.execute(
            """
            INSERT INTO chat_threads (user_id, is_active, title, created_at, updated_at)
            VALUES (?, 1, '', ?, ?)
            """,
            (int(user_id), now, now),
        )
        thread_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("SELECT * FROM chat_threads WHERE id = ?", (thread_id,)).fetchone()
    return _to_chat_thread_row(row) if row else {}


def get_active_chat_thread(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        thread = _ensure_active_chat_thread(conn, int(user_id))
        conn.commit()
    return thread


def list_chat_messages(thread_id: int, limit: int = 200) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE thread_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(thread_id), max(1, int(limit))),
        ).fetchall()
    return [_to_chat_message_row(r) for r in rows]


def list_active_chat_messages(user_id: int, limit: int = 200) -> dict[str, Any]:
    with get_conn() as conn:
        thread = _ensure_active_chat_thread(conn, int(user_id))
        conn.commit()
    messages = list_chat_messages(int(thread["id"]), limit=limit) if thread else []
    return {"thread": thread, "messages": messages}


def append_chat_exchange(user_id: int, user_message: str, assistant_message: str) -> dict[str, Any]:
    user_text = str(user_message or "").strip()
    assistant_text = str(assistant_message or "").strip()
    if not user_text or not assistant_text:
        return {}
    now = _utc_now_iso()
    with get_conn() as conn:
        thread = _ensure_active_chat_thread(conn, int(user_id))
        thread_id = int(thread["id"])
        if not str(thread.get("title", "")).strip():
            title = user_text[:80]
            conn.execute("UPDATE chat_threads SET title = ? WHERE id = ?", (title, thread_id))
        conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content, created_at)
            VALUES (?, 'user', ?, ?)
            """,
            (thread_id, user_text, now),
        )
        conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content, created_at)
            VALUES (?, 'assistant', ?, ?)
            """,
            (thread_id, assistant_text, now),
        )
        conn.execute("UPDATE chat_threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        conn.commit()
    return {"thread_id": thread_id}


def _hydrate_training_example(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["actual_output"] = _json_load(item.pop("actual_output_json", "{}"), {})
    item["ideal_output"] = _json_load(item.pop("ideal_output_json", "{}") or "{}", {})
    item["context_used"] = _json_load(item.pop("context_used_json", "[]"), [])
    item["used_sources"] = _json_load(item.pop("used_sources_json", "[]"), [])
    item["ticket_created"] = bool(item.get("ticket_created"))
    item["knowledge_gap_logged"] = bool(item.get("knowledge_gap_logged"))
    item["mismatch_fields"] = _json_load(item.get("mismatch_fields") or "[]", [])
    item["expected_payload"] = _json_load(item.get("expected_payload") or "{}", {})
    item["actual_payload"] = _json_load(item.get("actual_payload") or "{}", {})
    item["retrieval_meta"] = _json_load(item.get("retrieval_meta") or "{}", {})
    return item


def create_training_example(
    *,
    input_text: str,
    actual_output: dict[str, Any],
    user_id: int | None,
    user_role: str,
    query_type: str,
    in_scope: str,
    grounded: str,
    context_used: list[str] | None,
    used_sources: list[str] | None,
    context_count: int,
    ticket_created: bool,
    ticket_id: int | None,
    model: str = "",
    run_id: str = "",
    source_type: str = "chat_log",
    source_id: str = "",
    source_ref: str = "",
    knowledge_gap_logged: bool = False,
    knowledge_gap_reason: str = "",
    mismatch_fields: list[str] | None = None,
    expected_payload: dict[str, Any] | None = None,
    actual_payload: dict[str, Any] | None = None,
    retrieval_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "chat_log"
    created_at = _utc_now_iso()
    normalized = _normalize_input_text(input_text)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO training_examples (
                input_text, normalized_input, actual_output_json, ideal_output_json, human_notes,
                correction_type, context_used_json, reasoning, used_sources_json,
                context_count, query_type, in_scope, grounded, ticket_created,
                ticket_id, user_id, user_role, model, run_id, source_type, source_id, source_ref,
                knowledge_gap_logged, knowledge_gap_reason,
                mismatch_fields, expected_payload, actual_payload, retrieval_meta,
                created_at, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                input_text,
                normalized,
                _json_dump(actual_output),
                "",
                "",
                "pending",
                _json_dump(context_used or []),
                "",
                _json_dump(used_sources or []),
                int(context_count),
                query_type,
                in_scope,
                grounded,
                1 if ticket_created else 0,
                ticket_id,
                user_id,
                user_role,
                model,
                run_id,
                source_type,
                source_id,
                source_ref,
                1 if knowledge_gap_logged else 0,
                knowledge_gap_reason.strip(),
                _json_dump(mismatch_fields or []),
                _json_dump(expected_payload or {}),
                _json_dump(actual_payload or {}),
                _json_dump(retrieval_meta or {}),
                created_at,
                None,
            ),
        )
        example_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (example_id,)).fetchone()
    _auto_refresh_v1_dataset_files()
    return _hydrate_training_example(row) if row else {}


def get_training_example(example_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (example_id,)).fetchone()
    return _hydrate_training_example(row) if row else {}


def update_training_example_mismatch(
    example_id: int,
    *,
    mismatch_fields: list[str] | None = None,
    expected_payload: dict[str, Any] | None = None,
    actual_payload: dict[str, Any] | None = None,
    retrieval_meta: dict[str, Any] | None = None,
) -> bool:
    """Update only structural mismatch / retrieval columns (Faza A).
    Returns True if a row was updated, False otherwise. None args mean "leave as-is"."""
    sets: list[str] = []
    params: list[Any] = []
    if mismatch_fields is not None:
        sets.append("mismatch_fields = ?")
        params.append(_json_dump(mismatch_fields))
    if expected_payload is not None:
        sets.append("expected_payload = ?")
        params.append(_json_dump(expected_payload))
    if actual_payload is not None:
        sets.append("actual_payload = ?")
        params.append(_json_dump(actual_payload))
    if retrieval_meta is not None:
        sets.append("retrieval_meta = ?")
        params.append(_json_dump(retrieval_meta))
    if not sets:
        return False
    params.append(int(example_id))
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE training_examples SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
    return cur.rowcount > 0


def list_pending_grouped(limit_per_group: int = 5) -> dict[str, Any]:
    """Return Faza B aggregation: counts + small example previews per mismatch type.

    Notes:
    - A single training_example may have multiple mismatch_fields (e.g. both
      category and ticket_created), so it is counted in every applicable group.
      Caller must surface this in the UI.
    - We rely on `mismatch_fields` JSON column populated either at seed time
      (test runner / backfill) or via Faza A backfill script.
    """
    groups: dict[str, dict[str, Any]] = {}
    total_pending = 0
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, input_text, mismatch_fields, expected_payload, actual_payload,
                   retrieval_meta, source_type, created_at
            FROM training_examples
            WHERE correction_type = 'pending'
            ORDER BY id DESC
            """
        ).fetchall()
    for row in rows:
        total_pending += 1
        try:
            fields = json.loads(row["mismatch_fields"] or "[]")
        except Exception:
            fields = []
        if not isinstance(fields, list) or not fields:
            continue
        try:
            expected = json.loads(row["expected_payload"] or "{}")
        except Exception:
            expected = {}
        try:
            actual = json.loads(row["actual_payload"] or "{}")
        except Exception:
            actual = {}
        for field in fields:
            bucket = groups.setdefault(field, {"type": field, "count": 0, "affected_ids": [], "examples_preview": []})
            bucket["count"] += 1
            bucket["affected_ids"].append(int(row["id"]))
            if len(bucket["examples_preview"]) < int(limit_per_group):
                bucket["examples_preview"].append(
                    {
                        "id": int(row["id"]),
                        "input_excerpt": (row["input_text"] or "")[:160],
                        "expected": expected,
                        "actual": actual,
                        "source_type": row["source_type"],
                    }
                )
    rag_signal_types = {"response_tokens_missing"}
    ordered = sorted(groups.values(), key=lambda g: -g["count"])
    for g in ordered:
        g["rag_signal"] = g["type"] in rag_signal_types
    return {
        "total_pending": total_pending,
        "groups": ordered,
        "generated_at": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# eval_runs (Faza C) helpers
# ---------------------------------------------------------------------------
def has_running_eval_run() -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM eval_runs WHERE status = 'running' LIMIT 1"
        ).fetchone()
    return row is not None


def create_eval_run(*, override_active_ids: list[int] | None = None) -> int:
    started_at = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO eval_runs (
                prompt_override_active_ids, total, passed, status, started_at, details_json
            )
            VALUES (?, 0, 0, 'running', ?, '{}')
            """,
            (_json_dump(override_active_ids or []), started_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def finalize_eval_run(
    run_id: int,
    *,
    status: str,
    total: int,
    passed: int,
    accuracy_overall: float | None,
    accuracy_category: float | None,
    accuracy_priority: float | None,
    accuracy_ticket_created: float | None,
    accuracy_response_tokens: float | None,
    details: dict[str, Any] | None = None,
) -> None:
    finished_at = _utc_now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE eval_runs
            SET status = ?, total = ?, passed = ?, accuracy_overall = ?,
                accuracy_category = ?, accuracy_priority = ?,
                accuracy_ticket_created = ?, accuracy_response_tokens = ?,
                finished_at = ?, details_json = ?
            WHERE id = ?
            """,
            (
                status,
                int(total),
                int(passed),
                accuracy_overall,
                accuracy_category,
                accuracy_priority,
                accuracy_ticket_created,
                accuracy_response_tokens,
                finished_at,
                _json_dump(details or {}),
                int(run_id),
            ),
        )
        conn.commit()


def get_eval_run(run_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (int(run_id),)).fetchone()
    if not row:
        return {}
    item = dict(row)
    item["prompt_override_active_ids"] = _json_load(
        item.get("prompt_override_active_ids") or "[]", []
    )
    item["details"] = _json_load(item.get("details_json") or "{}", {})
    item.pop("details_json", None)
    return item


def list_eval_runs(limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eval_runs ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["prompt_override_active_ids"] = _json_load(
            item.get("prompt_override_active_ids") or "[]", []
        )
        # Drop heavy details_json from list view; clients fetch it via /runs/{id}.
        item.pop("details_json", None)
        out.append(item)
    return out


def compute_pending_cache_key() -> str:
    """sha256 of sorted pending example IDs. Used as cache key for analyzer
    output so re-running with the same data set is free."""
    import hashlib

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM training_examples WHERE correction_type = 'pending' ORDER BY id"
        ).fetchall()
    ids = ",".join(str(int(r["id"])) for r in rows)
    return hashlib.sha256(ids.encode("utf-8")).hexdigest()


def get_prompt_analysis_cache(cache_key: str, ttl_hours: int) -> dict[str, Any] | None:
    """Return cached result if fresh; None if missing or expired."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT result_json, model, created_at FROM prompt_analysis_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        ts = _isoformat_to_datetime(row["created_at"])
    except Exception:
        return None
    age = _utc_now() - ts
    if age.total_seconds() > max(0, int(ttl_hours)) * 3600:
        return None
    try:
        result = _json_load(row["result_json"], None)
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    return {
        "result": result,
        "model": row["model"],
        "created_at": row["created_at"],
        "cache_key": cache_key,
    }


def put_prompt_analysis_cache(cache_key: str, result: dict[str, Any], model: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO prompt_analysis_cache (cache_key, result_json, model, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (cache_key, _json_dump(result), model, _utc_now_iso()),
        )
        conn.commit()


def _isoformat_to_datetime(s: str):
    from datetime import datetime
    s = (s or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# prompt_overrides (Faza E) helpers
# ---------------------------------------------------------------------------
import threading as _threading

_active_overrides_lock = _threading.Lock()
# `ts` is None until first populated, so a fresh process (monotonic_now < TTL)
# never returns a stale empty list.
_active_overrides_cache: dict[str, Any] = {"ts": None, "data": []}
_ACTIVE_OVERRIDES_TTL_SECONDS = 30.0


def _hydrate_override(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["affected_example_ids"] = _json_load(item.get("affected_example_ids") or "[]", [])
    except Exception:
        item["affected_example_ids"] = []
    return item


def get_active_prompt_overrides(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Return active overrides (status='active'), in stable order (id ASC).
    Uses a process-local 30s cache so each chat call doesn't hit SQLite."""
    import time as _time

    now = _time.monotonic()
    with _active_overrides_lock:
        ts = _active_overrides_cache["ts"]
        if (
            not force_refresh
            and ts is not None
            and (now - ts) < _ACTIVE_OVERRIDES_TTL_SECONDS
        ):
            return list(_active_overrides_cache["data"])
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM prompt_overrides
            WHERE status = 'active'
            ORDER BY id ASC
            """
        ).fetchall()
    data = [_hydrate_override(r) for r in rows]
    with _active_overrides_lock:
        _active_overrides_cache["ts"] = now
        _active_overrides_cache["data"] = data
    return list(data)


def invalidate_active_overrides_cache() -> None:
    """Force the next get_active_prompt_overrides() to re-read from DB."""
    with _active_overrides_lock:
        _active_overrides_cache["ts"] = None
        _active_overrides_cache["data"] = []


def count_active_prompt_overrides() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM prompt_overrides WHERE status = 'active'"
        ).fetchone()
    return int(row["c"]) if row else 0


def apply_prompt_override(
    *,
    error_type: str,
    suggested_change: str,
    approved_change: str,
    affected_example_ids: list[int] | None,
    created_by_user_id: int | None,
    eval_baseline_id: int | None,
) -> dict[str, Any]:
    """Insert a new active override row. Caller is responsible for guard rails
    (max-active count, baseline-required, confidence floor)."""
    now = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO prompt_overrides (
                error_type, suggested_change, approved_change, status,
                affected_example_ids, created_by_user_id, created_at, activated_at,
                eval_baseline_id
            )
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                error_type,
                suggested_change,
                approved_change,
                _json_dump(affected_example_ids or []),
                created_by_user_id,
                now,
                now,
                eval_baseline_id,
            ),
        )
        oid = int(cur.lastrowid)
        # Mark affected training_examples for traceability.
        ids = affected_example_ids or []
        if ids:
            placeholders = ",".join(["?"] * len(ids))
            conn.execute(
                f"UPDATE training_examples SET correction_type = 'prompt_proposed' "
                f"WHERE id IN ({placeholders}) AND correction_type = 'pending'",
                tuple(int(x) for x in ids),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM prompt_overrides WHERE id = ?", (oid,)).fetchone()
    invalidate_active_overrides_cache()
    return _hydrate_override(row) if row else {}


def rollback_prompt_override(override_id: int) -> dict[str, Any]:
    now = _utc_now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE prompt_overrides
            SET status = 'superseded', deactivated_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (now, int(override_id)),
        )
        affected = cur.rowcount
        conn.commit()
        row = conn.execute("SELECT * FROM prompt_overrides WHERE id = ?", (int(override_id),)).fetchone()
    if affected == 0:
        return {}
    invalidate_active_overrides_cache()
    return _hydrate_override(row) if row else {}


def get_prompt_override(override_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM prompt_overrides WHERE id = ?", (int(override_id),)
        ).fetchone()
    return _hydrate_override(row) if row else {}


def list_prompt_overrides(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status = ?"
        params.append(status)
    params.append(max(1, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM prompt_overrides {where} ORDER BY id DESC LIMIT ?", params
        ).fetchall()
    return [_hydrate_override(r) for r in rows]


def set_prompt_override_eval_after(override_id: int, eval_after_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE prompt_overrides SET eval_after_id = ? WHERE id = ?",
            (int(eval_after_id), int(override_id)),
        )
        conn.commit()


def latest_done_eval_run(within_seconds: int | None = None) -> dict[str, Any]:
    where = "WHERE status = 'done'"
    params: list[Any] = []
    if within_seconds is not None and within_seconds > 0:
        # SQLite-compatible time comparison; finished_at is ISO-8601 UTC string.
        cutoff_iso = _utc_now_iso()
        where += " AND finished_at >= datetime(?, ?)"
        params.extend([cutoff_iso, f"-{int(within_seconds)} seconds"])
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT * FROM eval_runs {where} ORDER BY id DESC LIMIT 1", params
        ).fetchone()
    if not row:
        return {}
    item = dict(row)
    item["prompt_override_active_ids"] = _json_load(
        item.get("prompt_override_active_ids") or "[]", []
    )
    item.pop("details_json", None)
    return item


def get_training_examples(
    *,
    correction_type: str | None = None,
    user_role: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM training_examples WHERE 1=1"
    params: list[Any] = []
    if correction_type:
        query += " AND correction_type = ?"
        params.append(correction_type)
    if user_role:
        query += " AND user_role = ?"
        params.append(user_role)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([max(1, limit), max(0, offset)])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_hydrate_training_example(r) for r in rows]


def update_training_example_review(
    example_id: int,
    *,
    correction_type: str,
    ideal_output: dict[str, Any] | None = None,
    human_notes: str | None = None,
    context_used: list[str] | None = None,
    reasoning: str | None = None,
) -> dict[str, Any]:
    if correction_type not in ALLOWED_CORRECTION_TYPES:
        raise ValueError("Invalid correction_type. Allowed: pending, approved, edited, rejected")
    reviewed_at = _utc_now_iso() if correction_type != "pending" else None
    with get_conn() as conn:
        current = conn.execute("SELECT * FROM training_examples WHERE id = ?", (example_id,)).fetchone()
        if not current:
            return {}
        current_h = _hydrate_training_example(current)
        next_ideal = ideal_output if ideal_output is not None else current_h.get("ideal_output", {})
        next_notes = human_notes if human_notes is not None else str(current_h.get("human_notes", ""))
        next_reasoning = reasoning if reasoning is not None else str(current_h.get("reasoning", ""))
        next_context_used = context_used if context_used is not None else list(current_h.get("context_used", []))
        conn.execute(
            """
            UPDATE training_examples
            SET correction_type = ?, ideal_output_json = ?, human_notes = ?,
                context_used_json = ?, reasoning = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (
                correction_type,
                _json_dump(next_ideal),
                next_notes,
                _json_dump(next_context_used),
                next_reasoning,
                reviewed_at,
                example_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (example_id,)).fetchone()
    _auto_refresh_v1_dataset_files()
    return _hydrate_training_example(row) if row else {}


BULK_REVIEW_MAX_IDS = 500


def bulk_update_training_examples_review(
    ids: list[int],
    updates: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mass-update review fields for many rows by ID.

    Allowed keys in ``updates``:

    - ``human_notes`` / ``reasoning``: full replacement if present in dict.
    - ``correction_type``: if present, set to that value (must be in ALLOWED_CORRECTION_TYPES).

    If only ``human_notes`` and/or ``reasoning`` are updated (no ``correction_type`` in
    ``updates``), ``correction_type`` is forced to ``edited`` (same as single-record save).

    If only ``correction_type`` is updated, notes and reasoning are left unchanged.
    ``reviewed_at`` follows the same rule as ``update_training_example_review`` (set for
    non-pending, cleared for pending).
    """
    touch_notes = "human_notes" in updates
    touch_reasoning = "reasoning" in updates
    touch_corr = "correction_type" in updates
    if not touch_notes and not touch_reasoning and not touch_corr:
        raise ValueError(
            "At least one of human_notes, reasoning, or correction_type must be provided to update."
        )
    if touch_corr:
        ct = str(updates["correction_type"] or "").strip()
        if ct not in ALLOWED_CORRECTION_TYPES:
            raise ValueError(
                f"Invalid correction_type {ct!r}. Allowed: {', '.join(sorted(ALLOWED_CORRECTION_TYPES))}"
            )
    seen: set[int] = set()
    clean_ids: list[int] = []
    for raw in ids or []:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        if i <= 0 or i in seen:
            continue
        seen.add(i)
        clean_ids.append(i)
    if not clean_ids:
        raise ValueError("No valid positive integer IDs in list.")
    if len(clean_ids) > BULK_REVIEW_MAX_IDS:
        raise ValueError(f"Too many IDs (max {BULK_REVIEW_MAX_IDS}).")

    placeholders = ",".join("?" for _ in clean_ids)
    with get_conn() as conn:
        existing_rows = conn.execute(
            f"SELECT id FROM training_examples WHERE id IN ({placeholders})",
            clean_ids,
        ).fetchall()
        existing_ids = {int(r["id"]) for r in existing_rows}
        missing_ids = sorted(i for i in clean_ids if i not in existing_ids)

        if dry_run:
            return {
                "dry_run": True,
                "ids_requested": len(clean_ids),
                "would_update": len(existing_ids),
                "missing_ids": missing_ids,
                "updated": 0,
            }

        updated = 0
        for eid in clean_ids:
            if eid not in existing_ids:
                continue
            row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (eid,)).fetchone()
            if not row:
                continue
            cur_h = _hydrate_training_example(row)
            next_notes = (
                str(updates["human_notes"]) if touch_notes else str(cur_h.get("human_notes", ""))
            )
            next_reasoning = (
                str(updates["reasoning"]) if touch_reasoning else str(cur_h.get("reasoning", ""))
            )
            if touch_corr:
                next_corr = str(updates["correction_type"]).strip()
            else:
                next_corr = "edited"
            reviewed_at = _utc_now_iso() if next_corr != "pending" else None
            conn.execute(
                """
                UPDATE training_examples
                SET human_notes = ?, reasoning = ?, correction_type = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (next_notes, next_reasoning, next_corr, reviewed_at, eid),
            )
            updated += 1
        conn.commit()

    _auto_refresh_v1_dataset_files()
    return {
        "dry_run": False,
        "ids_requested": len(clean_ids),
        "updated": updated,
        "missing_ids": missing_ids,
    }


def export_training_examples_jsonl(
    *,
    include_correction_types: list[str] | None = None,
) -> str:
    include = include_correction_types or ["approved", "edited"]
    placeholders = ",".join("?" for _ in include)
    query = (
        f"SELECT * FROM training_examples WHERE correction_type IN ({placeholders}) "
        "ORDER BY id ASC"
    )
    with get_conn() as conn:
        rows = conn.execute(query, include).fetchall()

    lines: list[str] = []
    for row in rows:
        item = _hydrate_training_example(row)
        ideal_output = item.get("ideal_output") or item.get("actual_output") or {}
        record = {
            "input": item.get("input_text", ""),
            "ideal_output": {
                "category": ideal_output.get("category"),
                "priority": ideal_output.get("priority"),
                "create_ticket": bool(ideal_output.get("create_ticket")),
                "response": ideal_output.get("response"),
                "issue_summary": ideal_output.get("issue_summary"),
            },
            "human_notes": item.get("human_notes", ""),
            "correction_type": item.get("correction_type", "pending"),
            "context_used": item.get("context_used", []),
            "reasoning": item.get("reasoning", ""),
        }
        lines.append(_json_dump(record))
    return "\n".join(lines) + ("\n" if lines else "")


def _source_rank(source_type: str) -> int:
    ranks = {"chat_log": 3, "test_case": 2, "ticket": 1}
    return ranks.get(source_type, 0)


def _correction_rank(correction_type: str) -> int:
    ranks = {"edited": 4, "approved": 3, "pending": 2, "rejected": 1}
    return ranks.get(correction_type, 0)


def _choose_preferred_example(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    c_rank = _correction_rank(str(current.get("correction_type", "")))
    n_rank = _correction_rank(str(candidate.get("correction_type", "")))
    if n_rank != c_rank:
        return candidate if n_rank > c_rank else current
    cs_rank = _source_rank(str(current.get("source_type", "")))
    ns_rank = _source_rank(str(candidate.get("source_type", "")))
    if ns_rank != cs_rank:
        return candidate if ns_rank > cs_rank else current
    # Newer example wins as tie breaker.
    c_ts = str(current.get("created_at", ""))
    n_ts = str(candidate.get("created_at", ""))
    return candidate if n_ts >= c_ts else current


def upsert_review_seed_example(
    *,
    source_type: str,
    source_id: str,
    source_ref: str,
    input_text: str,
    actual_output: dict[str, Any],
    ideal_output: dict[str, Any],
    correction_type: str,
    human_notes: str,
    context_used: list[str] | None = None,
    reasoning: str = "",
    user_role: str = "system",
    query_type: str = "",
    in_scope: str = "YES",
    grounded: str = "YES",
    ticket_created: bool = False,
    ticket_id: int | None = None,
    model: str = "",
    run_id: str = "",
    force_append: bool = False,
    mismatch_fields: list[str] | None = None,
    expected_payload: dict[str, Any] | None = None,
    actual_payload: dict[str, Any] | None = None,
    retrieval_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if correction_type not in ALLOWED_CORRECTION_TYPES:
        correction_type = "pending"
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "chat_log"
    normalized = _normalize_input_text(input_text)
    created_at = _utc_now_iso()
    reviewed_at = _utc_now_iso() if correction_type in {"approved", "edited", "rejected"} else None
    with get_conn() as conn:
        if not force_append:
            existing = conn.execute(
                """
                SELECT * FROM training_examples
                WHERE source_type = ? AND source_id = ? AND source_ref = ?
                """,
                (source_type, source_id, source_ref),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE training_examples
                    SET input_text = ?, normalized_input = ?, actual_output_json = ?, ideal_output_json = ?,
                        correction_type = ?, human_notes = ?, context_used_json = ?, reasoning = ?,
                        query_type = ?, in_scope = ?, grounded = ?, ticket_created = ?, ticket_id = ?,
                        user_role = ?, model = ?, run_id = ?, reviewed_at = ?
                    WHERE id = ?
                    """,
                    (
                        input_text,
                        normalized,
                        _json_dump(actual_output),
                        _json_dump(ideal_output),
                        correction_type,
                        human_notes,
                        _json_dump(context_used or []),
                        reasoning,
                        query_type,
                        in_scope,
                        grounded,
                        1 if ticket_created else 0,
                        ticket_id,
                        user_role,
                        model,
                        run_id,
                        reviewed_at,
                        int(existing["id"]),
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (int(existing["id"]),)).fetchone()
                item = _hydrate_training_example(row) if row else {}
                _maybe_update_mismatch_fields(
                    int(existing["id"]),
                    mismatch_fields=mismatch_fields,
                    expected_payload=expected_payload,
                    actual_payload=actual_payload,
                    retrieval_meta=retrieval_meta,
                )
                return item

        cur = conn.execute(
            """
            INSERT INTO training_examples (
                input_text, normalized_input, actual_output_json, ideal_output_json, human_notes,
                correction_type, context_used_json, reasoning, used_sources_json, context_count,
                query_type, in_scope, grounded, ticket_created, ticket_id, user_id, user_role,
                model, run_id, source_type, source_id, source_ref, created_at, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                input_text,
                normalized,
                _json_dump(actual_output),
                _json_dump(ideal_output),
                human_notes,
                correction_type,
                _json_dump(context_used or []),
                reasoning,
                len(context_used or []),
                query_type,
                in_scope,
                grounded,
                1 if ticket_created else 0,
                ticket_id,
                user_role,
                model,
                run_id,
                source_type,
                source_id,
                source_ref,
                created_at,
                reviewed_at,
            ),
        )
        ex_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("SELECT * FROM training_examples WHERE id = ?", (ex_id,)).fetchone()
    item = _hydrate_training_example(row) if row else {}
    _maybe_update_mismatch_fields(
        ex_id,
        mismatch_fields=mismatch_fields,
        expected_payload=expected_payload,
        actual_payload=actual_payload,
        retrieval_meta=retrieval_meta,
    )
    return item


def _maybe_update_mismatch_fields(
    example_id: int,
    *,
    mismatch_fields: list[str] | None,
    expected_payload: dict[str, Any] | None,
    actual_payload: dict[str, Any] | None,
    retrieval_meta: dict[str, Any] | None,
) -> None:
    """Helper used by seed/upsert paths to write Faza A columns only when caller passed them."""
    if mismatch_fields is None and expected_payload is None and actual_payload is None and retrieval_meta is None:
        return
    update_training_example_mismatch(
        example_id,
        mismatch_fields=mismatch_fields,
        expected_payload=expected_payload,
        actual_payload=actual_payload,
        retrieval_meta=retrieval_meta,
    )


def backfill_training_examples_from_tickets(limit: int = 5000) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, message, issue_summary, category, priority, response, created_at, created_by_user_id
            FROM tickets
            ORDER BY id ASC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    inserted = 0
    updated = 0
    for row in rows:
        msg = str(row["message"] or "").strip()
        if not msg:
            continue
        ticket_id = int(row["id"])
        payload = {
            "category": row["category"],
            "priority": row["priority"],
            "create_ticket": True,
            "response": row["response"],
            "issue_summary": row["issue_summary"] or msg,
        }
        item = upsert_review_seed_example(
            source_type="ticket",
            source_id=str(ticket_id),
            source_ref="tickets.db",
            input_text=msg,
            actual_output=payload,
            ideal_output=payload,
            correction_type="pending",
            human_notes="Seeded from historical ticket",
            context_used=[],
            reasoning="Backfilled from ticket history",
            user_role="system",
            query_type="INCIDENT",
            in_scope="YES",
            grounded="YES",
            ticket_created=True,
            ticket_id=ticket_id,
            model="",
            run_id="v1-ticket-backfill",
            force_append=True,
        )
        if item.get("source_id") == str(ticket_id):
            # We cannot directly know insert/update without extra query; infer from reviewed_at/history.
            if str(item.get("created_at", "")).startswith(str(row["created_at"])[:10]):
                updated += 1
            else:
                inserted += 1
    _auto_refresh_v1_dataset_files()
    return {"processed": len(rows), "inserted_estimate": inserted, "updated_estimate": updated}


def _derive_test_row_mismatch(
    expected: dict[str, Any],
    actual: dict[str, Any],
    failures: list[Any],
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """For test_rag.py-style rows: derive structural mismatch_fields directly
    from expected vs actual (avoids regex on human_notes for new seedings)."""
    fields: list[str] = []
    exp_pl: dict[str, Any] = {}
    act_pl: dict[str, Any] = {}

    def add(field_key: str, exp_val: Any, act_val: Any, mismatch_label: str) -> None:
        if exp_val is None:
            return
        exp_pl[field_key] = exp_val
        act_pl[field_key] = act_val
        if str(exp_val).strip().lower() != str(act_val).strip().lower():
            fields.append(mismatch_label)

    add("category", expected.get("category"), actual.get("category"), "category_mismatch")
    add("priority", expected.get("priority"), actual.get("priority"), "priority_mismatch")
    if expected.get("ticket_created") is not None:
        exp_v = bool(expected.get("ticket_created"))
        act_v = bool(actual.get("ticket_created"))
        exp_pl["ticket_created"] = exp_v
        act_pl["ticket_created"] = act_v
        if exp_v and not act_v:
            fields.append("ticket_missing")
        elif exp_v != act_v:
            fields.append("ticket_created_mismatch")
    # response missing tokens come as failure strings; flag the bucket.
    for fail in failures or []:
        if isinstance(fail, str) and "response missing tokens" in fail.lower():
            fields.append("response_tokens_missing")
            break
    # Dedup preserving order.
    seen: set[str] = set()
    deduped = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped, exp_pl, act_pl


def _looks_like_garbage_input(message: str) -> bool:
    raw = (message or "").strip()
    if not raw:
        return True
    # Very short and non-informative inputs should not enter training.
    if len(raw) < 4:
        return True
    normalized = _normalize_input_text(raw)
    if not normalized:
        return True
    # Repeated single-char noise e.g. "aaaaaa", "??????".
    compact = normalized.replace(" ", "")
    if len(set(compact)) == 1 and len(compact) >= 6:
        return True
    return False


def _is_corrupted_test_payload(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return True
    if not expected and not actual:
        return True
    # Missing all key prediction fields is considered unusable for supervised review.
    has_any_signal = any(
        k in actual for k in ("category", "priority", "ticket_created", "response", "issue_summary")
    ) or any(k in expected for k in ("category", "priority", "ticket_created"))
    return not has_any_signal


def _auto_review_bucket_for_test_case(
    *,
    message: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    is_pass: bool,
    failures: list[Any],
    mismatch_fields: list[str],
) -> tuple[str, str]:
    """
    Practical triage:
      - approved: high certainty only
      - rejected: hard-fail / low-value rows only
      - pending: default bucket
    """
    if _looks_like_garbage_input(message):
        return "rejected", "Auto-rejected: low-quality input (empty/spam/nonsense)."
    if _is_corrupted_test_payload(expected, actual):
        return "rejected", "Auto-rejected: corrupted or unusable test payload."

    if is_pass and not failures and not mismatch_fields:
        return "approved", "Auto-approved from passing test case."

    fail_blob = " | ".join([str(x) for x in failures or []]).strip()
    if fail_blob:
        return "pending", f"Needs review: {fail_blob}"
    return "pending", "Needs review: uncertain quality."


def backfill_training_examples_from_test_results(results_path: str) -> dict[str, Any]:
    path = Path(results_path)
    data = _json_load(path.read_text(encoding="utf-8"), {})
    results = list(data.get("results", []))
    processed = 0
    approved = 0
    pending = 0
    rejected = 0
    for row in results:
        case_id = str(row.get("id", "")).strip()
        if not case_id:
            continue
        msg = str(row.get("message", "")).strip()
        if not msg:
            continue
        actual = dict(row.get("actual", {}) or {})
        expected = dict(row.get("expected", {}) or {})
        ideal = {
            "category": expected.get("category") or actual.get("category"),
            "priority": expected.get("priority") or actual.get("priority"),
            "create_ticket": (
                expected.get("ticket_created")
                if expected.get("ticket_created") is not None
                else actual.get("ticket_created")
            ),
            "response": actual.get("response", ""),
            "issue_summary": actual.get("issue_summary") or msg,
        }
        is_pass = bool(row.get("pass"))
        failures = list(row.get("failures", []) or [])
        if is_pass:
            mismatch_fields_v: list[str] = []
            expected_pl_v: dict[str, Any] = {}
            actual_pl_v: dict[str, Any] = {}
        else:
            mismatch_fields_v, expected_pl_v, actual_pl_v = _derive_test_row_mismatch(
                expected, actual, failures
            )
        corr, notes = _auto_review_bucket_for_test_case(
            message=msg,
            expected=expected,
            actual=actual,
            is_pass=is_pass,
            failures=failures,
            mismatch_fields=mismatch_fields_v,
        )
        upsert_review_seed_example(
            source_type="test_case",
            source_id=case_id,
            source_ref=str(path.name),
            input_text=msg,
            actual_output={
                "category": actual.get("category"),
                "priority": actual.get("priority"),
                "create_ticket": actual.get("ticket_created"),
                "response": actual.get("response", ""),
                "issue_summary": actual.get("issue_summary") or msg,
            },
            ideal_output=ideal,
            correction_type=corr,
            human_notes=notes,
            context_used=[],
            reasoning="Seeded from test suite result",
            user_role="system",
            query_type=str(actual.get("query_type", "")),
            in_scope="YES",
            grounded="YES",
            ticket_created=bool(actual.get("ticket_created")),
            ticket_id=actual.get("ticket_id"),
            model="",
            run_id="v1-test-backfill",
            force_append=True,
            mismatch_fields=mismatch_fields_v,
            expected_payload=expected_pl_v,
            actual_payload=actual_pl_v,
        )
        processed += 1
        if corr == "approved":
            approved += 1
        elif corr == "rejected":
            rejected += 1
        else:
            pending += 1
    _auto_refresh_v1_dataset_files()
    return {
        "processed": processed,
        "approved_seeded": approved,
        "pending_seeded": pending,
        "rejected_seeded": rejected,
    }


def _to_v1_dataset_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item.get("id", 0) or 0),
        "input_text": item.get("input_text", ""),
        "actual_output": item.get("actual_output", {}),
        "ideal_output": item.get("ideal_output") or item.get("actual_output", {}),
        "human_notes": item.get("human_notes", ""),
        "correction_type": item.get("correction_type", "pending"),
        "context_used": item.get("context_used", []),
        "reasoning": item.get("reasoning", ""),
        "source_type": item.get("source_type", ""),
        "source_id": item.get("source_id", ""),
        "source_ref": item.get("source_ref", ""),
        "user_role": item.get("user_role", ""),
        "query_type": item.get("query_type", ""),
        "ticket_id": item.get("ticket_id"),
        "created_at": item.get("created_at", _utc_now_iso()),
        "reviewed_at": item.get("reviewed_at"),
        "knowledge_gap_logged": bool(item.get("knowledge_gap_logged", False)),
        "knowledge_gap_reason": item.get("knowledge_gap_reason", ""),
    }


def build_v1_dataset_view() -> dict[str, Any]:
    rows = get_training_examples(limit=500000, offset=0)
    all_rows = [_to_v1_dataset_row(r) for r in rows if _include_in_review_candidates_jsonl(r)]
    train_rows = [
        r for r in all_rows if str(r.get("correction_type", "")).strip().lower() == "edited"
    ]
    review_rows = [
        r
        for r in all_rows
        if str(r.get("correction_type", "")).strip().lower() in {"pending", "rejected"}
    ]
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in all_rows:
        s = str(row.get("correction_type", "pending")).strip().lower() or "pending"
        by_status[s] = by_status.get(s, 0) + 1
        src = str(row.get("source_type", "") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    return {
        "all_rows": all_rows,
        "train_rows": train_rows,
        "review_rows": review_rows,
        "manifest": {
            "version": "db-first-v1",
            "total_raw_rows": len(all_rows),
            "train_rows": len(train_rows),
            "review_rows": len(review_rows),
            "by_status": by_status,
            "by_source_type": by_source,
            "updated_at": _utc_now_iso(),
        },
    }


def rebuild_json_store_from_db() -> dict[str, Any]:
    result = write_v1_dataset_files(TRAINING_DATA_DIR)
    return {
        "rows_written": int(result.get("manifest", {}).get("total_raw_rows", 0)),
        "paths": result.get("paths", {}),
    }


def prune_training_examples_for_review_policy() -> dict[str, Any]:
    with get_conn() as conn:
        before = int(conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0])
        conn.execute(
            """
            DELETE FROM training_examples
            WHERE NOT (
                source_type = 'test_case'
                OR lower(correction_type) = 'edited'
                OR (source_type = 'chat_log' AND ticket_created = 1)
            )
            """
        )
        conn.commit()
        after = int(conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0])
    result = rebuild_json_store_from_db()
    return {"before": before, "after": after, "deleted": before - after, **result}


def _pick_best_example_row(rows: list[sqlite3.Row]) -> int:
    def score(r: sqlite3.Row) -> tuple[int, str, str, int]:
        correction = str(r["correction_type"] or "")
        reviewed = str(r["reviewed_at"] or "")
        created = str(r["created_at"] or "")
        # Higher correction rank first, then latest reviewed/created, then latest id.
        return (_correction_rank(correction), reviewed, created, int(r["id"]))

    best = max(rows, key=score)
    return int(best["id"])


def cleanup_training_examples_and_candidates() -> dict[str, Any]:
    marker = "seeded from test suite result"
    with get_conn() as conn:
        before = int(conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0])

        duplicate_groups = conn.execute(
            """
            SELECT source_type, source_id, source_ref, COUNT(*) AS c
            FROM training_examples
            WHERE source_type <> '' OR source_id <> '' OR source_ref <> ''
            GROUP BY source_type, source_id, source_ref
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        deleted = 0
        for group in duplicate_groups:
            rows = conn.execute(
                """
                SELECT * FROM training_examples
                WHERE source_type = ? AND source_id = ? AND source_ref = ?
                """,
                (group["source_type"], group["source_id"], group["source_ref"]),
            ).fetchall()
            if len(rows) < 2:
                continue
            keep_id = _pick_best_example_row(rows)
            ids_to_delete = [int(r["id"]) for r in rows if int(r["id"]) != keep_id]
            if ids_to_delete:
                placeholders = ",".join("?" for _ in ids_to_delete)
                conn.execute(
                    f"DELETE FROM training_examples WHERE id IN ({placeholders})",
                    ids_to_delete,
                )
                deleted += len(ids_to_delete)

        edited_changed = conn.execute(
            """
            UPDATE training_examples
            SET correction_type = 'edited',
                reviewed_at = COALESCE(NULLIF(reviewed_at, ''), ?)
            WHERE lower(correction_type) IN ('pending', 'approved')
              AND lower(trim(COALESCE(reasoning, ''))) <> ?
            """,
            (_utc_now_iso(), marker),
        ).rowcount

        conn.commit()
        after = int(conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0])

    rebuild = rebuild_json_store_from_db()
    return {
        "before": before,
        "after": after,
        "deleted_duplicates": int(deleted),
        "duplicate_groups": int(len(duplicate_groups)),
        "edited_changed": int(edited_changed or 0),
        **rebuild,
    }


def mass_mark_all_edited_if_any_custom_reasoning() -> dict[str, Any]:
    marker = "seeded from test suite result"
    now = _utc_now_iso()
    with get_conn() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0])
        has_custom = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM training_examples
                WHERE lower(trim(COALESCE(reasoning, ''))) <> ?
                """,
                (marker,),
            ).fetchone()[0]
        )
        if has_custom == 0:
            return {"changed": 0, "total": total, "applied": False, "backup_path": None}
        changed = conn.execute(
            """
            UPDATE training_examples
            SET correction_type = 'edited',
                reviewed_at = COALESCE(NULLIF(reviewed_at, ''), ?)
            WHERE lower(COALESCE(correction_type, 'pending')) <> 'edited'
            """,
            (now,),
        ).rowcount
        conn.commit()
    _auto_refresh_v1_dataset_files()
    return {"changed": int(changed or 0), "total": total, "applied": True, "backup_path": None}


def export_v1_jsonl(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        ideal = row.get("ideal_output") or row.get("actual_output") or {}
        lines.append(
            _json_dump(
                {
                    "id": row.get("id"),
                    "input": row.get("input_text", ""),
                    "ideal_output": {
                        "category": ideal.get("category"),
                        "priority": ideal.get("priority"),
                        "create_ticket": bool(ideal.get("create_ticket")),
                        "response": ideal.get("response"),
                        "issue_summary": ideal.get("issue_summary"),
                    },
                    "human_notes": row.get("human_notes", ""),
                    "correction_type": row.get("correction_type", "pending"),
                    "context_used": row.get("context_used", []),
                    "reasoning": row.get("reasoning", ""),
                    "source_type": row.get("source_type", ""),
                    "source_id": row.get("source_id", ""),
                    "source_ref": row.get("source_ref", ""),
                    "created_at": row.get("created_at", ""),
                }
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def export_v1_review_csv(rows: list[dict[str, Any]]) -> str:
    headers = [
        "id",
        "source_type",
        "source_id",
        "input",
        "category",
        "priority",
        "create_ticket",
        "correction_type",
        "human_notes",
        "reasoning",
        "created_at",
    ]
    # csv module expects file-like; build via StringIO + writer.
    import io

    sio = io.StringIO()
    writer = csv.DictWriter(sio, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        ideal = row.get("ideal_output") or row.get("actual_output") or {}
        writer.writerow(
            {
                "id": row.get("id"),
                "source_type": row.get("source_type", ""),
                "source_id": row.get("source_id", ""),
                "input": row.get("input_text", ""),
                "category": ideal.get("category"),
                "priority": ideal.get("priority"),
                "create_ticket": bool(ideal.get("create_ticket")),
                "correction_type": row.get("correction_type", "pending"),
                "human_notes": row.get("human_notes", ""),
                "reasoning": row.get("reasoning", ""),
                "created_at": row.get("created_at", ""),
            }
        )
    text = sio.getvalue()
    sio.close()
    return text


def write_v1_dataset_files(base_dir: str) -> dict[str, Any]:
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    view = build_v1_dataset_view()
    candidates_path = root / "fine_tuning_v1_candidates.jsonl"
    review_path = root / "fine_tuning_v1_review.csv"
    train_path = root / "fine_tuning_v1_train.jsonl"
    manifest_path = root / "fine_tuning_v1_manifest.json"

    all_rows = list(view["all_rows"])
    review_rows = list(view["review_rows"])
    train_rows = list(view["train_rows"])
    candidates_path.write_text(export_v1_jsonl(all_rows), encoding="utf-8")
    review_path.write_text(export_v1_review_csv(review_rows), encoding="utf-8")
    train_path.write_text(export_v1_jsonl(train_rows), encoding="utf-8")
    manifest_path.write_text(_json_dump(view["manifest"]), encoding="utf-8")

    return {
        "paths": {
            "candidates": str(candidates_path),
            "review_csv": str(review_path),
            "train_jsonl": str(train_path),
            "manifest": str(manifest_path),
        },
        "manifest": view["manifest"],
    }
