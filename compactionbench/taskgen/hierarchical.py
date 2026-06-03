"""Age-controlled synthetic memory tasks for hierarchy experiments."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

from ..core.schema import TaskRow

DINNERS = ("pasta", "rice bowl", "soup", "ramen", "salad")
TEAS = ("black tea", "green tea", "mint tea", "ginger tea")
PROJECTS = ("Atlas", "Beacon", "Cedar", "Delta")


@dataclass(frozen=True)
class SyntheticMemoryEvent:
    day: int
    event_id: str
    kind: str
    key: str
    value: str
    importance: int
    text: str

    def line(self) -> str:
        return (
            f"[MEM day={self.day:+04d} id={self.event_id} type={self.kind} "
            f"key={self.key} value={self.value} importance={self.importance}] {self.text}"
        )


def generate_hierarchical_memory_tasks(
    *,
    streams: int = 4,
    seed: int = 0,
    days: int = 45,
    include_noise: bool = True,
) -> list[TaskRow]:
    """Generate repeated-context long-term memory tasks.

    Each stream is one recurring user memory context with multiple questions over
    different ages and abstraction levels.  The generator is deterministic, and
    every task includes oracle evidence in metadata for retrieval upper bounds.
    """

    rng = random.Random(seed)
    rows: list[TaskRow] = []
    for stream_idx in range(streams):
        events = _build_stream_events(rng, stream_idx=stream_idx, days=days, include_noise=include_noise)
        context = _render_context(events, stream_idx=stream_idx)
        by_day = {ev.day: ev for ev in events if ev.kind == "meal" and ev.key == "dinner"}
        dinner_counts = Counter(ev.value for ev in events if ev.kind == "meal" and ev.key == "dinner")
        usual_dinner, usual_dinner_count = dinner_counts.most_common(1)[0]
        least_common_dinner, least_common_dinner_count = min(dinner_counts.items(), key=lambda item: (item[1], item[0]))
        latest_tea = max((ev for ev in events if ev.kind == "preference" and ev.key == "tea"), key=lambda ev: ev.day)
        old_day = -min(30, days - 1)
        missing_day = -(days + 7)
        project_decision = max((ev for ev in events if ev.kind == "decision"), key=lambda ev: ev.day)

        specs = [
            {
                "query_type": "recent_exact",
                "question": "What did the user eat for dinner last night?",
                "gold": by_day[-1].value,
                "expected_tier": "L0/L1",
                "age_days": 1,
                "oracle": by_day[-1].line(),
            },
            {
                "query_type": "old_exact",
                "question": f"What did the user eat for dinner {abs(old_day)} days ago?",
                "gold": by_day[old_day].value,
                "expected_tier": "L3",
                "age_days": abs(old_day),
                "oracle": by_day[old_day].line(),
            },
            {
                "query_type": "corrected_old_exact",
                "question": f"After corrections, what did the user actually eat for dinner {abs(old_day)} days ago?",
                "gold": by_day[old_day].value,
                "expected_tier": "L1/L3",
                "age_days": abs(old_day),
                "oracle": by_day[old_day].line(),
            },
            {
                "query_type": "pattern",
                "question": "What dinner does the user usually eat most often?",
                "gold": usual_dinner,
                "expected_tier": "L2",
                "age_days": None,
                "oracle": f"Dinner counts: {dict(dinner_counts)}. Most common: {usual_dinner}.",
            },
            {
                "query_type": "dinner_count",
                "question": f"Answer with just the number: across the whole memory log, how many times did the user eat {usual_dinner} for dinner?",
                "gold": str(usual_dinner_count),
                "expected_tier": "L2",
                "age_days": None,
                "oracle": f"Dinner counts: {dict(dinner_counts)}. {usual_dinner}: {usual_dinner_count}.",
            },
            {
                "query_type": "least_common_dinner",
                "question": "Across the whole memory log, which dinner did the user eat least often? If there is a tie, answer with the alphabetically earliest dinner name.",
                "gold": least_common_dinner,
                "expected_tier": "L2",
                "age_days": None,
                "oracle": f"Dinner counts: {dict(dinner_counts)}. Least common by count then alphabetical tie-break: {least_common_dinner} ({least_common_dinner_count}).",
            },
            {
                "query_type": "stale_update",
                "question": "What is the user's current favorite tea?",
                "gold": latest_tea.value,
                "expected_tier": "L2",
                "age_days": abs(latest_tea.day),
                "oracle": latest_tea.line(),
            },
            {
                "query_type": "confirmed_preference",
                "question": "Ignoring stale profile imports and rejected suggestions, what is the user's confirmed current favorite tea?",
                "gold": latest_tea.value,
                "expected_tier": "L2",
                "age_days": abs(latest_tea.day),
                "oracle": latest_tea.line(),
            },
            {
                "query_type": "project_decision",
                "question": f"What is the current decision for project {project_decision.key}?",
                "gold": project_decision.value,
                "expected_tier": "L2/L3",
                "age_days": abs(project_decision.day),
                "oracle": project_decision.line(),
            },
            {
                "query_type": "confirmed_project_decision",
                "question": f"Ignoring rejected proposals, what is the confirmed current decision for project {project_decision.key}?",
                "gold": project_decision.value,
                "expected_tier": "L2/L3",
                "age_days": abs(project_decision.day),
                "oracle": project_decision.line(),
            },
            {
                "query_type": "abstention",
                "question": f"What did the user eat for dinner {abs(missing_day)} days ago?",
                "gold": "unknown",
                "expected_tier": "L3",
                "age_days": abs(missing_day),
                "oracle": f"No memory event exists for day {missing_day:+04d}; answer unknown.",
            },
        ]

        for spec_idx, spec in enumerate(specs):
            rows.append(
                TaskRow(
                    task_id=f"hiermem-s{stream_idx:02d}-{spec['query_type']}",
                    source_benchmark="synthetic",
                    source_task=f"hier_memory_{spec['query_type']}",
                    source_sample_id=f"stream-{stream_idx:02d}",
                    context=context,
                    question=str(spec["question"]),
                    gold_answer=str(spec["gold"]),
                    gold_answer_aliases=[] if spec["gold"] != "unknown" else ["not mentioned", "not enough information"],
                    scorer="exact_ci",
                    metadata={
                        "generator": "hierarchical_memory_v1",
                        "stream_id": f"stream-{stream_idx:02d}",
                        "query_type": spec["query_type"],
                        "memory_age_days": spec["age_days"],
                        "expected_tier": spec["expected_tier"],
                        "oracle_evidence": spec["oracle"],
                        "days": days,
                        "include_noise": include_noise,
                    },
                )
            )
    return rows


def _build_stream_events(
    rng: random.Random,
    *,
    stream_idx: int,
    days: int,
    include_noise: bool,
) -> list[SyntheticMemoryEvent]:
    events: list[SyntheticMemoryEvent] = []
    dominant_dinner = DINNERS[stream_idx % len(DINNERS)]
    project = PROJECTS[stream_idx % len(PROJECTS)]

    for age in range(days, 0, -1):
        day = -age
        dinner = dominant_dinner if (age + stream_idx) % 3 != 0 else rng.choice([d for d in DINNERS if d != dominant_dinner])
        events.append(
            SyntheticMemoryEvent(
                day=day,
                event_id=f"s{stream_idx:02d}-d{age:03d}-meal",
                kind="meal",
                key="dinner",
                value=dinner,
                importance=1,
                text=f"On day {age} days ago, the user ate {dinner} for dinner.",
            )
        )
        if include_noise and age % 5 == 0:
            events.append(
                SyntheticMemoryEvent(
                    day=day,
                    event_id=f"s{stream_idx:02d}-d{age:03d}-noise",
                    kind="note",
                    key="weather",
                    value=rng.choice(("rain", "sun", "wind")),
                    importance=0,
                    text="Low-importance weather note that should not affect meal or preference questions.",
                )
            )
        if include_noise and (age % 6 == 0 or age in {1, 30}):
            decoy = rng.choice([d for d in DINNERS if d != dinner])
            events.append(
                SyntheticMemoryEvent(
                    day=day,
                    event_id=f"s{stream_idx:02d}-d{age:03d}-dinner-decoy",
                    kind="note",
                    key="dinner_decoy",
                    value=decoy,
                    importance=0,
                    text=(
                        f"A stale imported note says: on day {age} days ago, the user ate {decoy} for dinner. "
                        "This import was later marked unreliable; prefer the typed meal event when answering what actually happened."
                    ),
                )
            )

    preference_days = [-(days - 3), -14, -2]
    for idx, day in enumerate(preference_days):
        tea = TEAS[(stream_idx + idx) % len(TEAS)]
        events.append(
            SyntheticMemoryEvent(
                day=day,
                event_id=f"s{stream_idx:02d}-tea-{idx}",
                kind="preference",
                key="tea",
                value=tea,
                importance=3,
                text=f"The user updated their favorite tea to {tea}.",
            )
        )
    if include_noise:
        rejected_tea = TEAS[(stream_idx + len(preference_days)) % len(TEAS)]
        events.append(
            SyntheticMemoryEvent(
                day=-1,
                event_id=f"s{stream_idx:02d}-tea-profile-import",
                kind="note",
                key="tea_profile_import",
                value=rejected_tea,
                importance=0,
                text=(
                    f"A stale profile import says the user's current favorite tea is {rejected_tea}. "
                    "This imported profile is stale and should be ignored."
                ),
            )
        )
        events.append(
            SyntheticMemoryEvent(
                day=-1,
                event_id=f"s{stream_idx:02d}-tea-rejected",
                kind="note",
                key="tea_decoy",
                value=rejected_tea,
                importance=0,
                text=(
                    f"Yesterday someone suggested changing the favorite tea to {rejected_tea}, "
                    "but the user explicitly rejected that suggestion."
                ),
            )
        )

    decision_days = [-(days - 8), -7]
    decisions = ["use flat retrieval", "use hierarchical memory"]
    for idx, (day, decision) in enumerate(zip(decision_days, decisions)):
        events.append(
            SyntheticMemoryEvent(
                day=day,
                event_id=f"s{stream_idx:02d}-project-{idx}",
                kind="decision",
                key=project,
                value=decision,
                importance=3,
                text=f"For project {project}, the current decision changed to: {decision}.",
            )
        )
    if include_noise:
        events.append(
            SyntheticMemoryEvent(
                day=-1,
                event_id=f"s{stream_idx:02d}-project-dashboard-stale",
                kind="note",
                key=f"{project}_stale_dashboard",
                value="use flat retrieval",
                importance=0,
                text=(
                    f"A stale project dashboard says the current decision for project {project} is to use flat retrieval. "
                    "The dashboard is outdated and should be ignored."
                ),
            )
        )
        events.append(
            SyntheticMemoryEvent(
                day=-1,
                event_id=f"s{stream_idx:02d}-project-rejected",
                kind="note",
                key=f"{project}_rejected_decision",
                value="use flat retrieval",
                importance=0,
                text=(
                    f"A teammate proposed reverting project {project} to use flat retrieval, "
                    "but this proposal was rejected and is not the current decision."
                ),
            )
        )

    events.sort(key=lambda ev: (ev.day, ev.event_id))
    return events


def _render_context(events: list[SyntheticMemoryEvent], *, stream_idx: int) -> str:
    lines = [
        f"# Synthetic hierarchical memory stream {stream_idx:02d}",
        "The following memory log contains dated user events. Day -001 is yesterday; larger negative numbers are older.",
        "Some old events become semantic patterns or current preferences, but raw events remain in the cold archive.",
        "",
    ]
    lines.extend(ev.line() for ev in events)
    return "\n".join(lines) + "\n"
