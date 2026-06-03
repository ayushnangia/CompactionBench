"""Scoring tests for direct run artifacts."""

from __future__ import annotations

import json

from compactionbench.core.schema import AgentAnswer, RunRecord
from compactionbench.core.score import score_runs


def test_score_runs_writes_summary(tmp_path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "results"
    target = runs / "claude_code" / "claude-sonnet-4-6" / "auto"
    target.mkdir(parents=True)

    rec = RunRecord(
        task_id="ruler-niah_single_1-0001",
        source_benchmark="ruler",
        source_task="niah_single_1",
        source_sample_id="1",
        harness="claude_code",
        model="claude-sonnet-4-6",
        condition="auto",
        session_id="s1",
        chunk_tokens=4000,
        chunk_count=3,
        context_tokens_est=12000,
        scorer="exact_ci",
        gold_answer="75128",
        gold_answer_aliases=[],
        final_answer_parsed=AgentAnswer(answer="75128"),
        parse_ok=True,
        correct=True,
    )
    (target / "ruler-niah_single_1-0001.json").write_text(rec.model_dump_json(indent=2))

    rows = score_runs(runs, out)
    assert len(rows) == 1
    assert rows[0].correct is True
    summary = json.loads((out / "summary.json").read_text())
    assert summary["by_harness_model_condition"]["claude_code:claude-sonnet-4-6:auto"]["accuracy"] == 1.0
