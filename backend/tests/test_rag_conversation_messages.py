"""Smoke tests for rag._conversation_messages template assembly.

Phase-3 cleanup removed the `str.format()` step from the chat path so that
RAG snippets and admin overrides containing literal `{` / `}` (e.g. JSON
examples) no longer blow up the template engine. These tests pin that
contract.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import rag  # noqa: E402


def test_conversation_messages_passes_json_in_context_unchanged(monkeypatch):
    monkeypatch.setattr(rag, "_build_override_block", lambda: "")
    context = [
        'Service log entry: {"ticket": 42, "category": "HVAC"}',
        "Plain text snippet without braces.",
    ]

    messages = rag._conversation_messages("Why is the AC dripping?", context)

    assert messages[0]["role"] == "system"
    system = messages[0]["content"]
    assert '{"ticket": 42, "category": "HVAC"}' in system
    assert "<<<BEGIN_UNTRUSTED_REFERENCE>>>" in system
    assert "<<<END_UNTRUSTED_REFERENCE>>>" in system
    assert messages[-1]["role"] == "user"
    assert "<<<BEGIN_USER_INPUT>>>" in messages[-1]["content"]
    assert "<<<END_USER_INPUT>>>" in messages[-1]["content"]
    assert "Why is the AC dripping?" in messages[-1]["content"]
    assert "USER QUERY:" not in system, "user query must not be injected into system prompt"


def test_conversation_messages_appends_override_block(monkeypatch):
    monkeypatch.setattr(
        rag,
        "_build_override_block",
        lambda: "\n\n## Additional rules (auto-tuned)\n- always cite the source\n",
    )
    messages = rag._conversation_messages("hi", ["snippet"])

    system = messages[0]["content"]
    assert "## Additional rules (auto-tuned)" in system
    assert "always cite the source" in system


def test_conversation_messages_handles_empty_context(monkeypatch):
    monkeypatch.setattr(rag, "_build_override_block", lambda: "")
    messages = rag._conversation_messages("hi", [])

    system = messages[0]["content"]
    assert "<<<BEGIN_UNTRUSTED_REFERENCE>>>" in system
    assert "No context found." in system


def test_conversation_messages_keeps_history_order(monkeypatch):
    monkeypatch.setattr(rag, "_build_override_block", lambda: "")
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "system", "content": "ignored"},
    ]
    messages = rag._conversation_messages("now", ["snippet"], history)

    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1]["role"] == "user"
    assert "<<<BEGIN_USER_INPUT>>>" in messages[1]["content"]
    assert "earlier question" in messages[1]["content"]
    assert messages[2]["content"] == "earlier answer"
    assert messages[-1]["role"] == "user"
    assert "<<<BEGIN_USER_INPUT>>>" in messages[-1]["content"]
    assert "now" in messages[-1]["content"]
