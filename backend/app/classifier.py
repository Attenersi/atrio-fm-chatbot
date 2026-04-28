from __future__ import annotations

import json
from typing import Any


ALLOWED_CATEGORY = {"HVAC", "Electrical", "Plumbing", "Safety", "General"}
ALLOWED_PRIORITY = {"URGENT", "HIGH", "NORMAL", "LOW"}
ALLOWED_YES_NO = {"YES", "NO"}
ALLOWED_QUERY_TYPE = {"INFORMATIONAL", "SERVICE_REQUEST", "INCIDENT", "OUT_OF_SCOPE"}


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
    }
