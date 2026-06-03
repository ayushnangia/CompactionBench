"""Loader tests for direct task-row preparation."""

from __future__ import annotations

from pathlib import Path

import pytest

from compactionbench.datasets.lme_loader import prepare_lme_tasks
from compactionbench.datasets.loaders import (
    _clean_babilong_carrier_text,
    extend_babilong_rows_with_long_carriers,
    prepare_babilong_tasks,
    prepare_oolong_real_tasks,
    prepare_oolong_synth_tasks,
    prepare_ruler_tasks,
)
from compactionbench.core.schema import TaskRow

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RULER_FIXTURE = FIXTURES / "ruler_sample_3.jsonl"
BABILONG_FIXTURE = FIXTURES / "babilong_sample_2.jsonl"
OOLONG_SYNTH_FIXTURE = FIXTURES / "oolong_synth_sample_2.jsonl"
OOLONG_REAL_FIXTURE = FIXTURES / "oolong_real_sample_2.jsonl"
LME_HAYSTACK_FIXTURE = FIXTURES / "lme_haystack.json"
LME_TRAJECTORIES_FIXTURE = FIXTURES / "lme_trajectories.jsonl"
LME_QUESTIONS_FIXTURE = FIXTURES / "lme_questions.jsonl"


def test_prepare_ruler_tasks_emits_rows() -> None:
    rows = prepare_ruler_tasks(
        RULER_FIXTURE,
        count=2,
        min_length=0,
        allowed_tasks={"niah_single_1"},
    )
    assert len(rows) == 2
    assert rows[0].source_benchmark == "ruler"
    assert rows[0].source_task == "niah_single_1"
    assert rows[0].question
    assert rows[0].context


def test_prepare_babilong_tasks_emits_rows() -> None:
    rows = prepare_babilong_tasks(
        BABILONG_FIXTURE,
        count=2,
        source_task="qa1",
        length_label="1M",
    )
    assert len(rows) == 2
    assert rows[0].source_benchmark == "babilong"
    assert rows[0].source_task == "qa1"
    assert rows[0].gold_answer == "bathroom"
    assert rows[0].metadata["length_label"] == "1M"
    assert rows[0].metadata["dataset_name"] == "RMT-team/babilong"
    assert rows[0].metadata["task_name"] == "single supporting fact"


def test_prepare_babilong_rejects_impossible_1m_1k_samples_combo() -> None:
    with pytest.raises(ValueError):
        prepare_babilong_tasks(
            BABILONG_FIXTURE,
            count=1,
            source_task="qa1",
            length_label="1M",
            dataset_name="RMT-team/babilong-1k-samples",
        )


def test_clean_babilong_carrier_text_removes_babi_like_lines() -> None:
    text = (
        "A long literary paragraph without benchmark entities.\n"
        "Mary went to the bathroom.\n"
        "Another safe paragraph.\n"
        "Fred picked up the football there.\n"
    )
    got = _clean_babilong_carrier_text(text)
    assert "Mary went to the bathroom." not in got
    assert "Fred picked up the football there." not in got
    assert "Another safe paragraph." in got


def test_prepare_lme_tasks_emits_one_per_question_type() -> None:
    rows = prepare_lme_tasks(
        LME_HAYSTACK_FIXTURE,
        LME_TRAJECTORIES_FIXTURE,
        LME_QUESTIONS_FIXTURE,
        count=10,
        target_tokens=100,
        count_per_type=1,
    )
    assert len(rows) == 2
    assert rows[0].source_benchmark == "lme"
    assert {row.metadata["question_type"] for row in rows} == {"static-environment", "dynamic-environment"}
    assert rows[0].context
    assert rows[0].scorer == "exact_ci"
    assert rows[1].scorer == "csv_set_ci"


def test_prepare_oolong_synth_tasks_emits_rows() -> None:
    rows = prepare_oolong_synth_tasks(
        OOLONG_SYNTH_FIXTURE,
        count=2,
        min_context_len=131072,
    )
    assert len(rows) == 2
    assert rows[0].source_benchmark == "oolong"
    assert rows[0].source_task == "counting"
    assert rows[0].gold_answer == "incorrect"
    assert rows[0].scorer == "oolong_text_ci"
    assert rows[0].metadata["length_label"] == "128k"
    assert rows[1].scorer == "month_year_ci"



def test_prepare_oolong_real_tasks_emits_rows() -> None:
    rows = prepare_oolong_real_tasks(
        OOLONG_REAL_FIXTURE,
        count=2,
    )
    assert len(rows) == 2
    assert rows[0].source_benchmark == "oolong"
    assert rows[0].source_task == "singledoc_rolls"
    assert rows[0].gold_answer == "114"
    assert rows[0].scorer == "numeric_075"
    assert rows[1].scorer == "csv_overlap_ci"



def test_prepare_oolong_real_tasks_uses_length_label_when_present(tmp_path) -> None:
    path = tmp_path / "real.jsonl"
    path.write_text(
        '{"id":"x1","context_window_id":"cw1","context_window_text":"ctx","question":"q?","answer":"5","question_type":"multidoc_rolls","episodes":[1,2,3],"campaign":"campaign1","length_label":"3ep","estimated_context_tokens":129000}\n'
    )
    rows = prepare_oolong_real_tasks(path, count=1)
    assert rows[0].task_id == "oolong-real-multidoc_rolls-3ep-x1"
    assert rows[0].metadata["length_label"] == "3ep"
    assert rows[0].metadata["estimated_context_tokens"] == 129000



def test_extend_babilong_rows_with_long_carriers_embeds_short_context() -> None:
    short_row = TaskRow(
        task_id="babilong-qa11-0k-s0",
        source_benchmark="babilong",
        source_task="qa11",
        source_sample_id="s0",
        context="Mary went to the kitchen. John went to the office.",
        question="Where is Mary?",
        gold_answer="kitchen",
        scorer="exact_ci",
        metadata={"length_label": "0k", "dataset_name": "RMT-team/babilong"},
    )
    carrier_rows = [
        TaskRow(
            task_id="babilong-qa1-128k-c0",
            source_benchmark="babilong",
            source_task="qa1",
            source_sample_id="c0",
            context=(
                "Noise paragraph one.\n"
                "Mary went to the bathroom.\n"
                + ("Neutral prose line.\n" * 200)
            ),
            question="Where is Mary?",
            gold_answer="bathroom",
            scorer="exact_ci",
            metadata={"length_label": "128k"},
        ),
        TaskRow(
            task_id="babilong-qa2-128k-c1",
            source_benchmark="babilong",
            source_task="qa2",
            source_sample_id="c1",
            context=("Different neutral prose line.\n" * 200),
            question="Where is the football?",
            gold_answer="garden",
            scorer="exact_ci",
            metadata={"length_label": "128k"},
        ),
    ]

    rows = extend_babilong_rows_with_long_carriers(
        short_rows=[short_row],
        carrier_rows=carrier_rows,
        length_label="128k",
    )
    assert len(rows) == 1
    got = rows[0]
    assert got.source_task == "qa11"
    assert got.question == "Where is Mary?"
    assert got.gold_answer == "kitchen"
    assert got.metadata["construction"] == "babilong_0k_embedded_in_cleaned_long_carrier"
    assert got.metadata["carrier_length_label"] == "128k"
    assert short_row.context in got.context
    assert "Mary went to the bathroom." not in got.context
    assert len(got.context) >= len(carrier_rows[0].context) - 10
