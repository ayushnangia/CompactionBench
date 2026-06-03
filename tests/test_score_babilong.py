"""BABILong-specific scoring behaviors."""

from __future__ import annotations

from compactionbench.core.score import score_one


def test_csv_set_ci_matches_comma_separated_sets_order_insensitively() -> None:
    assert score_one(
        scorer="csv_set_ci",
        gold="apple,football",
        gold_aliases=[],
        answer="football, apple",
    )


def test_csv_set_ci_rejects_different_sets() -> None:
    assert not score_one(
        scorer="csv_set_ci",
        gold="apple,football",
        gold_aliases=[],
        answer="apple,milk",
    )
