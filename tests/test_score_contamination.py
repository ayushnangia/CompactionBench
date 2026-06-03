"""Contaminated runs must not count toward main accuracy."""

from __future__ import annotations

import json

from compactionbench.core.schema import AgentAnswer, RunRecord, ToolEvent
from compactionbench.core.score import score_runs


def test_summary_excludes_contaminated_runs_from_main_accuracy(tmp_path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "results"
    target = runs / "claude_code" / "claude-sonnet-4-6" / "auto"
    target.mkdir(parents=True)

    clean = RunRecord(
        task_id="ruler-clean",
        source_benchmark="ruler",
        source_task="niah_single_1",
        source_sample_id="1",
        harness="claude_code",
        model="claude-sonnet-4-6",
        condition="auto",
        session_id="s1",
        chunk_tokens=4000,
        chunk_count=1,
        context_tokens_est=4000,
        scorer="exact_ci",
        gold_answer="42",
        final_answer_parsed=AgentAnswer(answer="42"),
        parse_ok=True,
        correct=True,
    )
    contaminated = RunRecord(
        task_id="ruler-dirty",
        source_benchmark="ruler",
        source_task="niah_single_1",
        source_sample_id="2",
        harness="claude_code",
        model="claude-sonnet-4-6",
        condition="auto",
        session_id="s2",
        chunk_tokens=4000,
        chunk_count=1,
        context_tokens_est=4000,
        scorer="exact_ci",
        gold_answer="42",
        final_answer_parsed=AgentAnswer(answer="wrong"),
        parse_ok=True,
        correct=False,
        contaminated_by_tools=True,
        tool_events=[ToolEvent(tool_name="Bash")],
    )

    (target / "clean.json").write_text(clean.model_dump_json(indent=2))
    (target / "dirty.json").write_text(contaminated.model_dump_json(indent=2))

    score_runs(runs, out)
    summary = json.loads((out / "summary.json").read_text())
    stats = summary["by_harness_model_condition"]["claude_code:claude-sonnet-4-6:auto"]
    assert stats["n_total"] == 2
    assert stats["n_clean"] == 1
    assert stats["accuracy"] == 1.0
    assert stats["accuracy_all"] == 0.5
