from __future__ import annotations

from compactionbench.core.score import score_one, score_value_one


def test_numeric_075_partial_credit() -> None:
    assert score_value_one(scorer="numeric_075", gold="10", gold_aliases=[], answer="11") == 0.75
    assert score_one(scorer="numeric_075", gold="10", gold_aliases=[], answer="10")
    assert not score_one(scorer="numeric_075", gold="10", gold_aliases=[], answer="11")



def test_oolong_text_and_comparison_normalization() -> None:
    assert score_one(scorer="oolong_text_ci", gold="incorrect", gold_aliases=[], answer="Label: incorrect")
    assert score_one(
        scorer="oolong_comparison_ci",
        gold="the same frequency",
        gold_aliases=[],
        answer="Answer: incorrect is same frequency before 2024-12-20",
    )



def test_date_and_month_year_scoring() -> None:
    assert score_one(scorer="date_ci", gold="2023-10-21", gold_aliases=[], answer="Date: October 21, 2023")
    assert score_one(scorer="month_year_ci", gold="October 2022", gold_aliases=[], answer="Answer: Oct 2022")



def test_csv_overlap_ci_partial_credit() -> None:
    assert score_value_one(
        scorer="csv_overlap_ci",
        gold="Fire Bolt, Gust of Wind, Transport Via Plants",
        gold_aliases=[],
        answer="Fire Bolt, Wrong Spell, Transport Via Plants",
    ) == 2 / 3
