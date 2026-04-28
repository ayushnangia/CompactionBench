from __future__ import annotations

import pytest

from compactionbench.compression import compress_context, compress_task_row, normalize_policy_name
from compactionbench.schema import TaskRow


def _row() -> TaskRow:
    filler = "The group discussed ordinary background details with no special identifiers. " * 40
    context = "\n".join(
        [
            filler,
            "Project Orion uses key K-1942 and Project Lyra uses key K-7721.",
            filler,
            "The deployment branch changed from alpha to beta, and beta is now the current final branch.",
            filler,
        ]
    )
    return TaskRow(
        task_id="toy-binding-001",
        source_benchmark="ruler",
        source_task="toy_binding",
        source_sample_id="1",
        context=context,
        question="Which key belongs to Project Orion?",
        gold_answer="K-1942",
        gold_answer_aliases=[],
        scorer="exact_ci",
        metadata={"kind": "toy"},
    )


def test_normalize_policy_aliases() -> None:
    assert normalize_policy_name("entropy") == "entropy-notebook"
    assert normalize_policy_name("static-heuristic") == "static-notebook"
    with pytest.raises(ValueError):
        normalize_policy_name("unknown")


def test_entropy_compression_keeps_high_signal_query_relevant_facts() -> None:
    row = _row()
    result = compress_context(
        row.context,
        question=row.question,
        policy="entropy",
        budget_tokens=180,
        query_aware=True,
    )
    assert "Project Orion" in result.context
    assert "K-1942" in result.context
    assert result.stats.selected_units > 0
    assert result.stats.compressed_tokens_est < result.stats.original_tokens_est


def test_static_notebook_renders_structured_note() -> None:
    row = _row()
    result = compress_context(
        row.context,
        question=None,
        policy="static-notebook",
        budget_tokens=180,
    )
    assert "COMPRESSED CONTEXT NOTE" in result.context
    assert "Numbers, dates, paths, and IDs" in result.context or "Entity bindings" in result.context
    assert result.stats.policy == "static-notebook"


def test_compress_task_row_preserves_scoring_fields_and_adds_metadata() -> None:
    row = _row()
    compressed = compress_task_row(
        row,
        policy="entropy-notebook",
        budget_tokens=180,
        query_aware=True,
    )
    assert compressed.task_id == "toy-binding-001--entropy-notebook-b180-qaware"
    assert compressed.gold_answer == row.gold_answer
    assert compressed.scorer == row.scorer
    assert compressed.metadata["kind"] == "toy"
    assert compressed.metadata["compression"]["original_task_id"] == row.task_id
    assert compressed.metadata["compression"]["policy"] == "entropy-notebook"
    assert compressed.metadata["compression"]["query_aware"] is True
    assert compressed.context != row.context
