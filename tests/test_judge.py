"""Tests for secondary LLM judge helpers."""

from __future__ import annotations

import json

from compactionbench.core.judge import JudgeDecision, JudgeResult, _parse_judge_json, _should_judge, judge_runs
from compactionbench.core.schema import AgentAnswer, RunRecord


def test_parse_judge_json_wrapped_text() -> None:
    decision = _parse_judge_json('notes\n{"equivalent": true, "reason": "same answer"}\nend')
    assert decision == JudgeDecision(equivalent=True, reason='same answer')


def test_should_judge_only_for_clean_parseable_failures() -> None:
    rec = RunRecord(
        task_id='x',
        source_benchmark='babilong',
        source_task='qa1',
        source_sample_id='1',
        harness='codex',
        model='gpt-5.4-mini',
        condition='auto',
        session_id='s1',
        chunk_tokens=1000,
        chunk_count=1,
        context_tokens_est=1000,
        scorer='exact_ci',
        gold_answer='bathroom',
        final_answer_parsed=AgentAnswer(answer='the bathroom'),
        parse_ok=True,
        contaminated_by_tools=False,
        correct=False,
    )
    assert _should_judge(rec, False, 'the bathroom') is True
    assert _should_judge(rec, True, 'the bathroom') is False

    rec_bad = rec.model_copy(update={'parse_ok': False})
    assert _should_judge(rec_bad, False, 'the bathroom') is False

    rec_dirty = rec.model_copy(update={'contaminated_by_tools': True})
    assert _should_judge(rec_dirty, False, 'the bathroom') is False


def test_judge_runs_parallel_with_stubbed_judge(tmp_path, monkeypatch) -> None:
    runs = tmp_path / 'runs' / 'codex' / 'gpt-5.4-mini' / 'auto'
    runs.mkdir(parents=True)

    good = RunRecord(
        task_id='good',
        source_benchmark='babilong',
        source_task='qa6',
        source_sample_id='1',
        harness='codex',
        model='gpt-5.4-mini',
        condition='auto',
        session_id='s1',
        chunk_tokens=1000,
        chunk_count=1,
        context_tokens_est=1000,
        scorer='exact_ci',
        gold_answer='yes',
        final_answer_parsed=AgentAnswer(answer='Yes.'),
        parse_ok=True,
        contaminated_by_tools=False,
        correct=False,
    )
    already = RunRecord(
        task_id='already',
        source_benchmark='babilong',
        source_task='qa5',
        source_sample_id='2',
        harness='codex',
        model='gpt-5.4-mini',
        condition='auto',
        session_id='s2',
        chunk_tokens=1000,
        chunk_count=1,
        context_tokens_est=1000,
        scorer='exact_ci',
        gold_answer='Jeff',
        final_answer_parsed=AgentAnswer(answer='Jeff'),
        parse_ok=True,
        contaminated_by_tools=False,
        correct=True,
    )
    (runs / 'good.json').write_text(good.model_dump_json(indent=2))
    (runs / 'already.json').write_text(already.model_dump_json(indent=2))

    monkeypatch.setattr('compactionbench.core.judge._make_client', lambda: object())
    monkeypatch.setattr(
        'compactionbench.core.judge.judge_one',
        lambda **kwargs: JudgeResult(
            decision=JudgeDecision(equivalent=True, reason='normalized yes/no'),
            raw_text='{"equivalent": true, "reason": "normalized yes/no"}',
        ),
    )

    out = tmp_path / 'judge'
    rows = judge_runs(runs.parent.parent.parent, out, max_workers=2)
    assert len(rows) == 2
    summary = json.loads((out / 'judge_summary.json').read_text())
    assert summary['n_total'] == 2
    assert summary['n_judged'] == 1
    assert summary['judge_overturns'] == 1
