"""Synthetic task generators for controlled compaction experiments.

Each generator produces a list of TaskRow objects where the failure mechanism
is isolated and interpretable. Tasks are designed to test specific aspects of
context compaction:

- stale update / latest value wins
- entity binding
- counting / aggregation
"""

from __future__ import annotations

import random
from copy import deepcopy
from pathlib import Path

from .schema import Scorer, TaskRow

BENCHMARK = "ruler"
SCORER_EXACT_CI: Scorer = "exact_ci"
SCORER_NUMERIC_075: Scorer = "numeric_075"


def generate_stale_update_tasks(
    *,
    count: int,
    filler_sentences: int = 200,
    seed: int = 0,
) -> list[TaskRow]:
    """Tasks where old facts are replaced by new ones in a long filler context.

    Tests whether compaction preserves the latest valid value or the old stale
    value.
    """
    rng = random.Random(seed)
    tasks: list[TaskRow] = []
    filler = _build_filler_paragraphs(rng, filler_sentences)

    templates: list[dict] = [
        {"topic": "deployment_branch", "old": "alpha", "new": "beta"},
        {"topic": "API endpoint", "old": "/v1/search", "new": "/v2/query"},
        {"topic": "default model", "old": "gpt-5.4-mini", "new": "gpt-5.4"},
        {"topic": "port number", "old": "8080", "new": "9090"},
        {"topic": "cache directory", "old": "/tmp/cache", "new": "/var/cache"},
        {"topic": "database host", "old": "db-old.example.com", "new": "db-new.example.com"},
        {"topic": "log level", "old": "debug", "new": "warn"},
        {"topic": "max workers", "old": "4", "new": "8"},
        {"topic": "timeout seconds", "old": "30", "new": "60"},
        {"topic": "feature flag", "old": "off", "new": "on"},
    ]

    for idx in range(count):
        t = rng.choice(templates)
        topic = t["topic"]
        old = t["old"]
        new = t["new"]

        old_fact = f"At first, the {topic} was set to {old}."
        new_fact = f"Later, the team changed the {topic} to {new}."
        final_fact = f"The final confirmed value for the {topic} is {new}."

        context = _inject_signals(
            rng,
            filler,
            signals=[old_fact, new_fact, final_fact],
            positions=[0.2, 0.5, 0.8],
        )
        question = f"What is the current {topic}?"
        gold = new

        tasks.append(
            TaskRow(
                task_id=f"synthetic-stale-update-{idx:03d}",
                source_benchmark=BENCHMARK,
                source_task="stale_update",
                source_sample_id=str(idx),
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=SCORER_EXACT_CI,
                metadata={
                    "generator": "stale_update",
                    "topic": topic,
                    "old_value": old,
                    "new_value": new,
                    "filler_sentences": filler_sentences,
                },
            )
        )
    return tasks


def generate_entity_binding_tasks(
    *,
    count: int,
    filler_sentences: int = 200,
    seed: int = 0,
) -> list[TaskRow]:
    """Tasks where many entities are bound to values in a long filler context.

    Tests whether compaction preserves exact entity-value associations or
    mixes them up.
    """
    rng = random.Random(seed)
    tasks: list[TaskRow] = []
    filler = _build_filler_paragraphs(rng, filler_sentences)

    entity_pools = [
        [
            ("Project Orion", "K-1942"),
            ("Project Lyra", "K-7721"),
            ("Project Vega", "K-0388"),
        ],
        [
            ("user admin", "token A7X9"),
            ("user editor", "token B3F2"),
            ("user viewer", "token C8H5"),
        ],
        [
            ("service alpha", "port 3000"),
            ("service beta", "port 3001"),
            ("service gamma", "port 3002"),
        ],
        [
            ("team frontend", "repo ui-core"),
            ("team backend", "repo api-core"),
            ("team infra", "repo infra-tools"),
        ],
        [
            ("region us-east", "instance i-001"),
            ("region eu-west", "instance i-002"),
            ("region ap-south", "instance i-003"),
        ],
    ]

    for idx in range(count):
        pool = rng.choice(entity_pools)
        bindings = list(pool)
        rng.shuffle(bindings)

        binding_lines = [f"{entity} uses {value}." for entity, value in bindings]
        context = _inject_signals(
            rng,
            filler,
            signals=binding_lines,
            positions=[0.3, 0.5, 0.7],
        )

        target_entity, target_value = rng.choice(bindings)
        question = f"What {_pick_value_noun(target_value)} belongs to {target_entity}?"
        gold = target_value

        tasks.append(
            TaskRow(
                task_id=f"synthetic-entity-binding-{idx:03d}",
                source_benchmark=BENCHMARK,
                source_task="entity_binding",
                source_sample_id=str(idx),
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=SCORER_EXACT_CI,
                metadata={
                    "generator": "entity_binding",
                    "entities": [e for e, _ in bindings],
                    "target_entity": target_entity,
                    "bindings": {e: v for e, v in bindings},
                    "filler_sentences": filler_sentences,
                },
            )
        )
    return tasks


def generate_counting_tasks(
    *,
    count: int,
    filler_sentences: int = 200,
    seed: int = 0,
) -> list[TaskRow]:
    """Tasks where events are scattered across a long filler context.

    Tests whether compaction preserves enough local facts to compute a correct
    aggregate count.
    """
    rng = random.Random(seed)
    tasks: list[TaskRow] = []
    filler = _build_filler_paragraphs(rng, filler_sentences)

    event_types = ["job_failed", "job_passed", "deploy_succeeded", "deploy_failed"]
    target_event = "job_failed"
    target_count = 15

    for idx in range(count):
        extra_events = rng.randint(0, 15)
        events: list[str] = []

        # insert target events
        for _ in range(target_count):
            events.append(f"{target_event} at step {rng.randint(1, 1000)}")
        # insert distractor events
        for et in event_types:
            if et == target_event:
                continue
            for _ in range(rng.randint(1, 6)):
                events.append(f"{et} at step {rng.randint(1, 1000)}")
        rng.shuffle(events)

        positions = [rng.uniform(0.1, 0.9) for _ in events]
        context = _inject_signals(rng, filler, signals=events, positions=positions)
        question = f"How many {target_event} events occurred across the log?"
        gold = str(target_count)

        tasks.append(
            TaskRow(
                task_id=f"synthetic-counting-{idx:03d}",
                source_benchmark=BENCHMARK,
                source_task="counting",
                source_sample_id=str(idx),
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=SCORER_NUMERIC_075,
                metadata={
                    "generator": "counting",
                    "target_event": target_event,
                    "target_count": target_count,
                    "total_events": len(events),
                    "filler_sentences": filler_sentences,
                },
            )
        )
    return tasks


def generate_all_synthetic_tasks(
    *,
    count_per_type: int = 5,
    filler_sentences: int = 200,
    seed: int = 0,
) -> list[TaskRow]:
    tasks: list[TaskRow] = []
    tasks.extend(
        generate_stale_update_tasks(
            count=count_per_type,
            filler_sentences=filler_sentences,
            seed=seed,
        )
    )
    tasks.extend(
        generate_entity_binding_tasks(
            count=count_per_type,
            filler_sentences=filler_sentences,
            seed=seed + 1,
        )
    )
    tasks.extend(
        generate_counting_tasks(
            count=count_per_type,
            filler_sentences=filler_sentences,
            seed=seed + 2,
        )
    )
    return tasks


def _build_filler_paragraphs(rng: random.Random, sentences: int) -> str:
    templates = [
        "The team discussed background topics and general infrastructure updates without mentioning any specific identifiers or values.",
        "Routine maintenance was performed on several internal systems with no notable changes.",
        "Several meetings covered standard operational procedures and upcoming roadmap items.",
        "The documentation was reviewed for accuracy and several minor typos were corrected.",
        "Performance metrics were reported as within normal range for the quarter.",
        "Lunch was ordered from the usual place and everyone agreed the food was adequate.",
        "Someone asked about the conference schedule and was told to check the shared calendar.",
        "The hallway conversation drifted toward weekend plans and movie recommendations.",
        "A new intern introduced themselves and was assigned a minor bug to fix.",
        "The coffee machine was reported broken again and a maintenance ticket was filed.",
        "Several emails were exchanged about the upcoming release timeline.",
        "Weather discussions occupied approximately five minutes of the standup.",
        "The team reviewed last month's incident report and agreed on preventive measures.",
        "Parking permits were renewed for the quarter.",
        "Someone mentioned a useful VSCode extension and shared the link.",
    ]
    return " ".join(rng.choice(templates) for _ in range(sentences))


def _inject_signals(
    rng: random.Random,
    filler: str,
    signals: list[str],
    positions: list[float],
) -> str:
    sentences = filler.split(". ")
    n = len(sentences)
    for signal, pos in zip(signals, positions):
        idx = min(n - 1, max(0, int(n * pos)))
        sentences[idx] = sentences[idx] + " " + signal
    return ". ".join(sentences)


def _pick_value_noun(value: str) -> str:
    value = value.strip()
    if re.match(r"^[A-Z]{2,}[-_A-Z0-9]*\b", value):
        return "key"
    if re.match(r"^token\s", value, re.IGNORECASE):
        return "token"
    if re.match(r"^port\s", value, re.IGNORECASE):
        return "port"
    if re.match(r"^repo\s", value, re.IGNORECASE):
        return "repository"
    if re.match(r"^instance\s", value, re.IGNORECASE):
        return "instance"
    return "value"


import re
