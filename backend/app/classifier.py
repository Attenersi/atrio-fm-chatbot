from __future__ import annotations

import json
import re
from typing import Any

from .config import CHAT_MULTI_ISSUE_MAX

ALLOWED_CATEGORY = {"HVAC", "Electrical", "Plumbing", "Safety", "General"}
ALLOWED_PRIORITY = {"URGENT", "HIGH", "NORMAL", "LOW"}
ALLOWED_YES_NO = {"YES", "NO"}
ALLOWED_QUERY_TYPE = {"INFORMATIONAL", "SERVICE_REQUEST", "INCIDENT", "OUT_OF_SCOPE"}


def _normalize_issue_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    issue_summary = str(raw.get("issue_summary", "")).strip()
    if not issue_summary:
        return None
    category = str(raw.get("category", "General"))
    priority = str(raw.get("priority", "NORMAL"))
    department = str(raw.get("department", "Facility Management") or "Facility Management").strip()
    create_ticket = str(raw.get("create_ticket", "NO")).upper()
    if category not in ALLOWED_CATEGORY:
        category = "General"
    if priority not in ALLOWED_PRIORITY:
        priority = "NORMAL"
    if create_ticket not in ALLOWED_YES_NO:
        create_ticket = "NO"
    return {
        "issue_summary": issue_summary,
        "category": category,
        "priority": priority,
        "department": department,
        "create_ticket": create_ticket,
    }


def _issue_dedupe_key(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]+", " ", text.lower()).split())


def _parse_issues_list(raw_issues: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_issues, list):
        return []
    cap = max(1, min(20, int(CHAT_MULTI_ISSUE_MAX or 5)))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_issues:
        if len(out) >= cap:
            break
        if not isinstance(item, dict):
            continue
        norm = _normalize_issue_dict(item)
        if not norm:
            continue
        key = _issue_dedupe_key(norm["issue_summary"])
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    data = json.loads(cleaned)
    category = data.get("category", "General")
    priority = data.get("priority", "NORMAL")
    department = data.get("department", "Facility Management")
    response = data.get("response", "No response generated.")
    in_scope = str(data.get("in_scope", "YES")).upper()
    grounded = str(data.get("grounded", "YES")).upper()
    query_type = str(data.get("query_type", "INFORMATIONAL")).upper()
    create_ticket = str(data.get("create_ticket", "NO")).upper()
    issue_summary = str(data.get("issue_summary", "")).strip()

    if category not in ALLOWED_CATEGORY:
        category = "General"
    if priority not in ALLOWED_PRIORITY:
        priority = "NORMAL"
    if in_scope not in ALLOWED_YES_NO:
        in_scope = "YES"
    if grounded not in ALLOWED_YES_NO:
        grounded = "YES"
    if query_type not in ALLOWED_QUERY_TYPE:
        query_type = "INFORMATIONAL"
    if create_ticket not in ALLOWED_YES_NO:
        create_ticket = "NO"
    if not issue_summary:
        issue_summary = "No issue summary provided."

    issues = _parse_issues_list(data.get("issues"))

    return {
        "category": category,
        "priority": priority,
        "department": department,
        "in_scope": in_scope,
        "grounded": grounded,
        "query_type": query_type,
        "create_ticket": create_ticket,
        "issue_summary": issue_summary,
        "response": response,
        "issues": issues,
    }


def fallback_response(raw: str) -> dict[str, Any]:
    return {
        "category": "General",
        "priority": "NORMAL",
        "department": "Facility Management",
        "in_scope": "YES",
        "grounded": "NO",
        "query_type": "INFORMATIONAL",
        "create_ticket": "NO",
        "issue_summary": "General informational request.",
        "response": raw,
        "issues": [],
    }
