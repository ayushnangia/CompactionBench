from __future__ import annotations

from collections import Counter

from compactionbench.taskgen.hierarchical import generate_hierarchical_memory_tasks


def test_generate_hierarchical_memory_tasks_reuses_context_per_stream() -> None:
    rows = generate_hierarchical_memory_tasks(streams=2, days=35, seed=0)

    assert len(rows) == 22
    by_stream = {}
    for row in rows:
        by_stream.setdefault(row.metadata["stream_id"], set()).add(row.context)
    assert set(len(contexts) for contexts in by_stream.values()) == {1}


def test_generate_hierarchical_memory_tasks_covers_query_types() -> None:
    rows = generate_hierarchical_memory_tasks(streams=1, days=35, seed=0)
    counts = Counter(row.metadata["query_type"] for row in rows)

    assert counts == {
        "recent_exact": 1,
        "old_exact": 1,
        "corrected_old_exact": 1,
        "pattern": 1,
        "dinner_count": 1,
        "least_common_dinner": 1,
        "stale_update": 1,
        "confirmed_preference": 1,
        "project_decision": 1,
        "confirmed_project_decision": 1,
        "abstention": 1,
    }
    assert {row.source_benchmark for row in rows} == {"synthetic"}
    assert all(row.metadata["oracle_evidence"] for row in rows)


def test_abstention_task_has_unknown_gold_and_aliases() -> None:
    rows = generate_hierarchical_memory_tasks(streams=1, days=35, seed=0)
    abstention = next(row for row in rows if row.metadata["query_type"] == "abstention")

    assert abstention.gold_answer == "unknown"
    assert "not mentioned" in abstention.gold_answer_aliases


def test_generator_includes_rejected_decoys_for_semantic_failures() -> None:
    rows = generate_hierarchical_memory_tasks(streams=1, days=35, seed=0, include_noise=True)
    context = rows[0].context

    assert "stale imported note" in context
    assert "stale profile import" in context
    assert "explicitly rejected" in context
    assert "dashboard is outdated" in context
    assert "proposal was rejected" in context
