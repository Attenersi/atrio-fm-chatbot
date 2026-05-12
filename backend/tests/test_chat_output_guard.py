"""Tests for chat_output_guard post-parse checks."""

from __future__ import annotations

from unittest.mock import patch

from app.chat_output_guard import apply_output_guardrails, validate_chat_output


def test_ticket_contradiction_detected() -> None:
    payload = {
        "category": "General",
        "priority": "NORMAL",
        "create_ticket": "NO",
        "response": "I have created a ticket for the maintenance team.",
        "issue_summary": "test",
    }
    issues = validate_chat_output(payload, "lights")
    assert "TICKET_CONTRADICTION" in issues


def test_ticket_contradiction_rewrite() -> None:
    payload = {
        "category": "General",
        "priority": "NORMAL",
        "create_ticket": "NO",
        "response": "I'll create a ticket right away.",
        "issue_summary": "test",
    }
    out = apply_output_guardrails(payload, "x")
    assert out["response"] != payload["response"]
    assert "facility" in out["response"].lower()


def test_sensitive_terms_empty_by_default() -> None:
    payload = {
        "category": "HVAC",
        "priority": "NORMAL",
        "create_ticket": "NO",
        "response": "The BMS schedule controls night setback for HVAC.",
        "issue_summary": "info",
    }
    with patch("app.chat_output_guard.CHAT_OUTPUT_SENSITIVE_TERMS", ()):
        assert validate_chat_output(payload, "") == []


def test_sensitive_terms_when_configured() -> None:
    payload = {
        "category": "General",
        "priority": "NORMAL",
        "create_ticket": "NO",
        "response": "We use Siemens controllers on this site.",
        "issue_summary": "x",
    }
    with patch("app.chat_output_guard.CHAT_OUTPUT_SENSITIVE_TERMS", ("siemens",)):
        out = apply_output_guardrails(payload, "")
        assert "siemens" not in out["response"].lower()
