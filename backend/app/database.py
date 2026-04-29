from __future__ import annotations

import sqlite3
import hashlib
import hmac
import csv
import json
import secrets
import uuid
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
_AUTO_REFRESH_LOCK = False
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


def _auto_refresh_v1_dataset_files() -> None:
    global _AUTO_REFRESH_LOCK, _LAST_AUTO_REFRESH_TS
    if str(TRAINING_DATA_AUTO_REFRESH).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    if _AUTO_REFRESH_LOCK:
        return
    now = time.monotonic()
    min_interval = max(0, int(TRAINING_DATA_AUTO_REFRESH_SECONDS))
    if min_interval > 0 and (now - _LAST_AUTO_REFRESH_TS) < min_interval:
        return
    _AUTO_REFRESH_LOCK = True
    try:
        write_v1_dataset_files(TRAINING_DATA_DIR)
        _LAST_AUTO_REFRESH_TS = now
    except Exception:
        # Dataset export should never break primary DB operations.
        pass
    finally:
        _AUTO_REFRESH_LOCK = False


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
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_training_examples_source
            ON training_examples(source_type, source_id, source_ref)
            WHERE source_id != ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_training_examples_norm_input
            ON training_examples(normalized_input)
            """
        )
        _ensure_default_user(conn, ADMIN_USERNAME, ADMIN_PASSWORD or "admin", "admin")
        _ensure_default_user(
            conn,
            AUTH_BOOTSTRAP_USER_USERNAME,
            AUTH_BOOTSTRAP_USER_PASSWORD or "user",
            "user",
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


def _hydrate_training_example(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["actual_output"] = _json_load(item.pop("actual_output_json", "{}"), {})
    item["ideal_output"] = _json_load(item.pop("ideal_output_json", "{}") or "{}", {})
    item["context_used"] = _json_load(item.pop("context_used_json", "[]"), [])
    item["used_sources"] = _json_load(item.pop("used_sources_json", "[]"), [])
    item["ticket_created"] = bool(item.get("ticket_created"))
    item["knowledge_gap_logged"] = bool(item.get("knowledge_gap_logged"))
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
                knowledge_gap_logged, knowledge_gap_reason, created_at, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
) -> dict[str, Any]:
    if correction_type not in ALLOWED_CORRECTION_TYPES:
        correction_type = "pending"
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "chat_log"
    normalized = _normalize_input_text(input_text)
    created_at = _utc_now_iso()
    reviewed_at = _utc_now_iso() if correction_type in {"approved", "edited", "rejected"} else None
    with get_conn() as conn:
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
            return _hydrate_training_example(row) if row else {}

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
    return _hydrate_training_example(row) if row else {}


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
        )
        if item.get("source_id") == str(ticket_id):
            # We cannot directly know insert/update without extra query; infer from reviewed_at/history.
            if str(item.get("created_at", "")).startswith(str(row["created_at"])[:10]):
                updated += 1
            else:
                inserted += 1
    _auto_refresh_v1_dataset_files()
    return {"processed": len(rows), "inserted_estimate": inserted, "updated_estimate": updated}


def backfill_training_examples_from_test_results(results_path: str) -> dict[str, Any]:
    path = Path(results_path)
    data = _json_load(path.read_text(encoding="utf-8"), {})
    results = list(data.get("results", []))
    processed = 0
    approved = 0
    pending = 0
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
        corr = "approved" if is_pass else "pending"
        notes = "Auto-approved from passing test case." if is_pass else "Needs review: " + " | ".join(
            [str(x) for x in row.get("failures", [])]
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
        )
        processed += 1
        if is_pass:
            approved += 1
        else:
            pending += 1
    _auto_refresh_v1_dataset_files()
    return {"processed": processed, "approved_seeded": approved, "pending_seeded": pending}


def build_v1_dataset_view() -> dict[str, Any]:
    rows = get_training_examples(limit=200000, offset=0)
    all_rows = list(rows)
    train_rows = [r for r in all_rows if str(r.get("correction_type")) in {"approved", "edited"}]
    review_rows = [r for r in all_rows if str(r.get("correction_type")) in {"pending", "rejected"}]

    # Keep dedup stats in manifest for diagnostics only.
    dedup: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        key = str(row.get("normalized_input") or _normalize_input_text(str(row.get("input_text", ""))))
        if not key:
            continue
        if key not in dedup:
            dedup[key] = row
            continue
        dedup[key] = _choose_preferred_example(dedup[key], row)
    dedup_rows = list(dedup.values())
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in all_rows:
        ideal = row.get("ideal_output") or row.get("actual_output") or {}
        cat = str(ideal.get("category") or "Unknown")
        pr = str(ideal.get("priority") or "Unknown")
        src = str(row.get("source_type") or "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1
        by_source[src] = by_source.get(src, 0) + 1
    return {
        "all_rows": all_rows,
        "train_rows": train_rows,
        "review_rows": review_rows,
        "manifest": {
            "total_raw_rows": len(rows),
            "total_dedup_rows": len(dedup_rows),
            "train_rows": len(train_rows),
            "review_rows": len(review_rows),
            "dedup_ratio": round((1 - (len(dedup_rows) / len(rows))), 4) if rows else 0.0,
            "by_category": by_category,
            "by_priority": by_priority,
            "by_source_type": by_source,
        },
    }


def export_v1_jsonl(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        ideal = row.get("ideal_output") or row.get("actual_output") or {}
        rec = {
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
        }
        lines.append(_json_dump(rec))
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
