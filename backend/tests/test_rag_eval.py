from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.rag_eval import (
    build_test_cases_from_csv_bytes,
    build_test_cases_from_json_bytes,
    evaluate_case,
    merge_report,
    run_suite_internal,
)


def test_csv_basic_rows() -> None:
    csv_text = (
        "id,message,should_create_ticket,expected_category\n"
        "a1,Hello leak,false,\n"
        "b2,AC broken,true,HVAC\n"
    )
    cases = build_test_cases_from_csv_bytes(csv_text.encode("utf-8"))
    assert len(cases) == 2
    assert cases[0].id == "a1"
    assert cases[0].message == "Hello leak"
    assert cases[0].expected_ticket_created is False
    assert cases[1].expected_category == "HVAC"
    assert cases[1].expected_ticket_created is True


def test_csv_question_alias_and_expected_in_response() -> None:
    csv_text = (
        "id,question,expected_in_response\n"
        "q1,What address?,Graanstraat|Breda\n"
    )
    cases = build_test_cases_from_csv_bytes(csv_text.encode("utf-8"))
    assert len(cases) == 1
    spec = cases[0].expected_in_response
    assert spec is not None
    assert isinstance(spec[0], list)
    assert "Graanstraat" in spec[0]


def test_csv_skips_empty_message_rows() -> None:
    csv_text = "id,message\n" "x1,\n" "x2,ok\n"
    cases = build_test_cases_from_csv_bytes(csv_text.encode("utf-8"))
    assert [c.id for c in cases] == ["x2"]


def test_evaluate_case_ticket_and_tokens() -> None:
    from app.rag_eval import TestCase

    case = TestCase(
        id="t",
        category="c",
        message="m",
        expected_ticket_created=True,
        expected_in_response=["hello"],
    )
    ok, failures = evaluate_case(
        case,
        {
            "ticket_created": True,
            "category": "X",
            "priority": "LOW",
            "response": "Say hello there",
        },
    )
    assert ok
    assert failures == []

    ok2, failures2 = evaluate_case(
        case,
        {
            "ticket_created": False,
            "response": "no",
        },
    )
    assert not ok2
    assert any("ticket_created" in f for f in failures2)
    assert any("tokens" in f for f in failures2)


def test_run_suite_internal_uses_run_chat_core() -> None:
    from app.rag_eval import TestCase

    cases = [
        TestCase(id="1", category="g", message="hi", expected_ticket_created=False)
    ]

    fake_payload = {
        "ticket_created": False,
        "category": "General",
        "priority": "LOW",
        "response": "ok",
        "issue_summary": "",
        "query_type": "INFORMATIONAL",
    }

    async def _run() -> None:
        with patch("app.main.run_chat_core", new_callable=AsyncMock) as m:
            m.return_value = fake_payload
            results, summary = await run_suite_internal(
                cases,
                {"id": 1, "username": "admin", "role": "admin"},
                run_id="r1",
                source_ref="unit",
                sleep_between_seconds=0,
                max_retries=0,
                retry_wait_seconds=0,
                per_request_timeout=None,
                on_progress=None,
            )
            assert m.await_count == 1
            call_kw = m.await_args.kwargs
            assert call_kw["isolate_history"] is True
            assert len(results) == 1
            assert results[0]["pass"] is True
            assert summary["passed"] == 1

    asyncio.run(_run())


def test_merge_report_diff() -> None:
    prev = [{"id": "a", "pass": False}, {"id": "b", "pass": True}]
    curr = [{"id": "a", "pass": True}, {"id": "b", "pass": False}]
    report = merge_report(
        results=curr,
        summary={"total": 2, "passed": 1, "api_ok_count": 2, "api_ok_passed": 1},
        user={"username": "u"},
        compare_prev_results=prev,
    )
    assert report["diff"] is not None
    assert "a" in report["diff"]["improved"]
    assert "b" in report["diff"]["regressed"]


def test_json_suite_bytes() -> None:
    raw = {
        "groups": [
            {
                "group": "g",
                "tests": [
                    {
                        "id": "j1",
                        "message": "m",
                        "should_create_ticket": False,
                        "expected_in_response": ["x", ["y", "z"]],
                    }
                ],
            }
        ]
    }
    cases = build_test_cases_from_json_bytes(
        json.dumps(raw).encode("utf-8"),
    )
    assert len(cases) == 1
    assert cases[0].expected_in_response is not None
    assert isinstance(cases[0].expected_in_response[1], list)
