from __future__ import annotations

from compactionbench.taskgen.synthetic import (
    generate_all_synthetic_tasks,
    generate_counting_tasks,
    generate_entity_binding_tasks,
    generate_stale_update_tasks,
)


def test_generate_stale_update_tasks_produces_expected_count() -> None:
    tasks = generate_stale_update_tasks(count=5, filler_sentences=50, seed=0)
    assert len(tasks) == 5
    for t in tasks:
        assert "changed" in t.context.lower()
        assert t.source_task == "stale_update"
        assert t.question.startswith("What is the current")
        assert t.gold_answer
        assert t.scorer == "exact_ci"


def test_generate_entity_binding_tasks_produces_expected_count() -> None:
    tasks = generate_entity_binding_tasks(count=3, filler_sentences=30, seed=0)
    assert len(tasks) == 3
    for t in tasks:
        assert t.source_task == "entity_binding"
        assert t.gold_answer
        assert t.question


def test_generate_counting_tasks_produces_expected_count() -> None:
    tasks = generate_counting_tasks(count=4, filler_sentences=40, seed=0)
    assert len(tasks) == 4
    for t in tasks:
        assert t.source_task == "counting"
        assert t.gold_answer == "15"
        assert "job_failed" in t.question.lower()
        assert t.scorer == "numeric_075"


def test_generate_all_synthetic_tasks_combines_all_types() -> None:
    tasks = generate_all_synthetic_tasks(count_per_type=2, filler_sentences=20, seed=0)
    assert len(tasks) == 6
    types = {t.source_task for t in tasks}
    assert types == {"stale_update", "entity_binding", "counting"}


def test_synthetic_tasks_have_signal_in_context() -> None:
    tasks = generate_stale_update_tasks(count=1, filler_sentences=30, seed=0)
    ctx = tasks[0].context
    gold = tasks[0].gold_answer
    assert gold.lower() in ctx.lower()


def test_synthetic_context_grows_with_filler() -> None:
    small = generate_stale_update_tasks(count=1, filler_sentences=10, seed=0)
    large = generate_stale_update_tasks(count=1, filler_sentences=100, seed=0)
    assert len(large[0].context) > len(small[0].context)
