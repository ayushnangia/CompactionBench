"""Pydantic validation for direct task rows and run artifacts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compactionbench.core.schema import AgentAnswer, RunRecord, TaskRow, parse_agent_answer


def _valid_task_row() -> dict:
    return {
        "task_id": "ruler-niah_single_1-0001",
        "source_benchmark": "ruler",
        "source_task": "niah_single_1",
        "source_sample_id": "1",
        "context": "needle haystack needle",
        "question": "What is the magic number?",
        "gold_answer": "75128",
        "gold_answer_aliases": [],
        "scorer": "exact_ci",
        "metadata": {"upstream_length": 1000000},
    }


def test_task_row_roundtrip() -> None:
    row = TaskRow.model_validate(_valid_task_row())
    row2 = TaskRow.model_validate_json(row.model_dump_json())
    assert row2.model_dump() == row.model_dump()


def test_task_row_rejects_extra_fields() -> None:
    raw = _valid_task_row()
    raw["oops"] = 1
    with pytest.raises(ValidationError):
        TaskRow.model_validate(raw)


def test_task_row_bad_task_id_fails() -> None:
    raw = _valid_task_row()
    raw["task_id"] = "bad id with spaces"
    with pytest.raises(ValidationError):
        TaskRow.model_validate(raw)


def test_agent_answer_roundtrip() -> None:
    ans = AgentAnswer(answer="hello")
    ans2 = AgentAnswer.model_validate_json(ans.model_dump_json())
    assert ans2 == ans


def test_parse_agent_answer_clean_json() -> None:
    got = parse_agent_answer('{"answer": "42"}')
    assert got.answer == "42"


def test_parse_agent_answer_wrapped_in_prose() -> None:
    got = parse_agent_answer('final result\n{"answer": "OK"}\nthanks')
    assert got.answer == "OK"


def test_parse_agent_answer_last_object_wins() -> None:
    got = parse_agent_answer('{"scratch": 1}\n{"answer": "final"}')
    assert got.answer == "final"


def test_parse_agent_answer_missing_json_fails() -> None:
    with pytest.raises(ValueError):
        parse_agent_answer("no json here")


def test_run_record_roundtrip() -> None:
    rec = RunRecord(
        task_id="ruler-niah_single_1-0001",
        source_benchmark="ruler",
        source_task="niah_single_1",
        source_sample_id="1",
        harness="claude_code",
        model="claude-sonnet-4-6",
        condition="off",
        session_id="session-1",
        chunk_tokens=4000,
        chunk_count=3,
        context_tokens_est=12000,
        scorer="exact_ci",
        gold_answer="75128",
        gold_answer_aliases=[],
        parse_ok=True,
        final_answer_parsed=AgentAnswer(answer="75128"),
        correct=True,
    )
    rec2 = RunRecord.model_validate_json(rec.model_dump_json())
    assert rec2.final_answer_parsed is not None
    assert rec2.final_answer_parsed.answer == "75128"
