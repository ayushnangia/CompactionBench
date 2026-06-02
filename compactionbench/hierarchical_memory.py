"""Deterministic hierarchical memory packets for age-aware experiments.

This module is deliberately small and auditable.  It is not a learned memory
writer; it gives us a controlled hierarchy to compare against flat grep/RAG and
PEEK-style maps.

Synthetic memory events are stored as lines like::

    [MEM day=-030 id=s00-d030-meal type=meal key=dinner value=ramen importance=1] ...

The hierarchy is:

- L0 hot recent raw events
- L1 day/session summaries
- L2 semantic facts and repeated patterns
- L3 cold raw archive search

The packet builder routes each question to one or more tiers and records the
route in metadata so failures can be diagnosed as routing vs reasoning errors.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from .chunking import estimate_tokens

_EVENT_RE = re.compile(
    r"^\[MEM\s+day=(?P<day>-?\d+)\s+id=(?P<event_id>[^\s]+)\s+"
    r"type=(?P<kind>[^\s]+)\s+key=(?P<key>[^\s]+)\s+value=(?P<value>.*?)\s+"
    r"importance=(?P<importance>\d+)\]\s*(?P<text>.*)$"
)
_DAY_RE = re.compile(r"(?:day\s*-?\s*(\d+)|(?:\b(\d+)\s+days?\s+ago\b))", re.IGNORECASE)


@dataclass(frozen=True)
class MemoryEvent:
    day: int
    event_id: str
    kind: str
    key: str
    value: str
    importance: int
    text: str

    @property
    def age_days(self) -> int:
        return abs(self.day)

    def render(self) -> str:
        return (
            f"[day={self.day:+04d} id={self.event_id} type={self.kind} "
            f"key={self.key} value={self.value} importance={self.importance}] {self.text}"
        )


@dataclass(frozen=True)
class MemoryTier:
    name: str
    title: str
    items: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        if not self.items:
            return f"## {self.title}\n(no selected evidence)\n"
        return f"## {self.title}\n" + "\n".join(f"- {item}" for item in self.items) + "\n"


@dataclass(frozen=True)
class HierarchicalMemoryPacket:
    strategy: str
    question: str
    selected_tiers: tuple[str, ...]
    evidence_text: str
    evidence_tokens_est: int
    events_total: int
    route_reason: str
    tiers: tuple[MemoryTier, ...] = field(default_factory=tuple)

    def metadata(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "selected_tiers": list(self.selected_tiers),
            "evidence_tokens_est": self.evidence_tokens_est,
            "events_total": self.events_total,
            "route_reason": self.route_reason,
            "tiers": [
                {"name": tier.name, "title": tier.title, "item_count": len(tier.items)}
                for tier in self.tiers
            ],
        }


@dataclass(frozen=True)
class HierarchicalMemoryConfig:
    hot_days: int = 2
    warm_days: int = 14
    max_items_per_tier: int = 24
    budget_tokens: int = 4000


def parse_memory_events(context: str) -> list[MemoryEvent]:
    """Parse synthetic memory events from a context string."""

    events: list[MemoryEvent] = []
    for line in context.splitlines():
        match = _EVENT_RE.match(line.strip())
        if not match:
            continue
        events.append(
            MemoryEvent(
                day=int(match.group("day")),
                event_id=match.group("event_id"),
                kind=match.group("kind"),
                key=match.group("key"),
                value=match.group("value").strip(),
                importance=int(match.group("importance")),
                text=match.group("text").strip(),
            )
        )
    events.sort(key=lambda ev: (ev.day, ev.event_id))
    return events


def build_hierarchical_memory_packet(
    context: str,
    question: str,
    *,
    config: HierarchicalMemoryConfig | None = None,
) -> HierarchicalMemoryPacket:
    """Build a routed evidence packet from the deterministic memory hierarchy."""

    cfg = config or HierarchicalMemoryConfig()
    events = parse_memory_events(context)
    selected_names, reason = route_question(question)
    tiers: list[MemoryTier] = []

    if "L0" in selected_names:
        tiers.append(_hot_tier(events, question, cfg))
    if "L1" in selected_names:
        tiers.append(_episodic_tier(events, question, cfg))
    if "L2" in selected_names:
        tiers.append(_semantic_tier(events, question, cfg))
    if "L3" in selected_names:
        tiers.append(_cold_tier(events, question, cfg))

    if not tiers:
        tiers = [_semantic_tier(events, question, cfg), _cold_tier(events, question, cfg)]
        selected_names = ("L2", "L3")
        reason = "fallback semantic plus cold archive"

    evidence_text = render_hierarchical_packet(question, tiers, route_reason=reason)
    # Enforce budget coarsely by dropping least-preferred tiers from the end,
    # while keeping at least one tier.  This keeps the canary deterministic.
    while estimate_tokens(evidence_text) > cfg.budget_tokens and len(tiers) > 1:
        tiers = tiers[:-1]
        selected_names = tuple(tier.name for tier in tiers)
        evidence_text = render_hierarchical_packet(question, tiers, route_reason=reason + "; truncated to budget")

    return HierarchicalMemoryPacket(
        strategy="deterministic_hierarchical_memory_v1",
        question=question,
        selected_tiers=tuple(tier.name for tier in tiers),
        evidence_text=evidence_text,
        evidence_tokens_est=estimate_tokens(evidence_text),
        events_total=len(events),
        route_reason=reason,
        tiers=tuple(tiers),
    )


def build_flat_memory_packet(
    context: str,
    question: str,
    *,
    config: HierarchicalMemoryConfig | None = None,
) -> HierarchicalMemoryPacket:
    """Build an equal-budget flat retrieval packet with no hierarchy or consolidation.

    This baseline scores raw memory events directly against the query and returns
    the top events under the same coarse token budget as the hierarchy packet.
    It deliberately does not build current-state tables, semantic summaries, or
    archive absence checks.
    """

    cfg = config or HierarchicalMemoryConfig()
    events = parse_memory_events(context)
    tier = _flat_retrieval_tier(events, question, cfg)
    evidence_text = render_hierarchical_packet(
        question,
        [tier],
        route_reason="flat query-term retrieval over raw memory events; no tiers or consolidation",
    )
    items = list(tier.items)
    while estimate_tokens(evidence_text) > cfg.budget_tokens and len(items) > 1:
        items = items[:-1]
        tier = MemoryTier("FLAT", "FLAT RAW RETRIEVAL MEMORY", tuple(items))
        evidence_text = render_hierarchical_packet(
            question,
            [tier],
            route_reason="flat query-term retrieval over raw memory events; truncated to budget",
        )
    return HierarchicalMemoryPacket(
        strategy="flat_query_term_retrieval_v1",
        question=question,
        selected_tiers=("FLAT",),
        evidence_text=evidence_text,
        evidence_tokens_est=estimate_tokens(evidence_text),
        events_total=len(events),
        route_reason="flat query-term retrieval over raw memory events; no tiers or consolidation",
        tiers=(tier,),
    )


def build_hierarchical_memory_prompt(question: str, *, packet: HierarchicalMemoryPacket) -> str:
    return (
        "You are answering from a HIERARCHICAL MEMORY PACKET.\n"
        "The packet has selected memory tiers before you answer: hot recent memory, episodic summaries, semantic facts, and/or cold archive evidence.\n"
        "Do not use tools or the web. Answer only from the packet. If the packet says no matching memory exists, answer unknown.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        "<HIERARCHICAL_MEMORY_PACKET>\n"
        f"{packet.evidence_text}\n"
        "</HIERARCHICAL_MEMORY_PACKET>\n\n"
        f"Question:\n{question}\n"
    )


def build_flat_memory_prompt(question: str, *, packet: HierarchicalMemoryPacket) -> str:
    return (
        "You are answering from a FLAT RETRIEVAL MEMORY PACKET.\n"
        "The packet contains raw retrieved memory events only. It has no hierarchical summaries, current-state table, or full archive scan.\n"
        "Do not use tools or the web. Answer only from the packet. If the packet is insufficient, answer unknown.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        "<FLAT_RETRIEVAL_MEMORY_PACKET>\n"
        f"{packet.evidence_text}\n"
        "</FLAT_RETRIEVAL_MEMORY_PACKET>\n\n"
        f"Question:\n{question}\n"
    )


def build_oracle_memory_prompt(question: str, *, oracle_evidence: str) -> str:
    return (
        "You are answering from ORACLE MEMORY EVIDENCE for a benchmark diagnostic.\n"
        "Do not use tools or the web. Answer only from the evidence.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        "<ORACLE_MEMORY_EVIDENCE>\n"
        f"{oracle_evidence}\n"
        "</ORACLE_MEMORY_EVIDENCE>\n\n"
        f"Question:\n{question}\n"
    )


def render_hierarchical_packet(question: str, tiers: Iterable[MemoryTier], *, route_reason: str) -> str:
    lines = [
        "HIERARCHICAL MEMORY PACKET",
        f"Question used for routing: {question}",
        f"Route reason: {route_reason}",
        "",
    ]
    for tier in tiers:
        lines.append(tier.text.rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def route_question(question: str) -> tuple[tuple[str, ...], str]:
    q = question.lower()
    if any(phrase in q for phrase in ("last night", "yesterday", "today", "recent")):
        return ("L0", "L1"), "recent exact recall"
    if (
        "usually" in q
        or "most often" in q
        or "least often" in q
        or "least common" in q
        or "typical" in q
        or "pattern" in q
        or "how many" in q
        or "count" in q
        or "times" in q
    ):
        return ("L2",), "pattern/count or semantic recall"
    if "current" in q or "now" in q or "latest" in q:
        return ("L2", "L1"), "current/stale-update recall"
    if "never mentioned" in q or "not mentioned" in q or "unknown" in q:
        return ("L3",), "abstention check against cold archive"
    if _requested_age(question) is not None:
        return ("L1", "L3"), "old exact recall with cold fallback"
    return ("L2", "L3"), "default semantic plus archive retrieval"


def _hot_tier(events: list[MemoryEvent], question: str, cfg: HierarchicalMemoryConfig) -> MemoryTier:
    recent = [ev for ev in events if ev.age_days <= cfg.hot_days]
    filtered = _filter_events_for_question(recent, question)
    picked = [ev.render() for ev in filtered]
    return MemoryTier("L0", "L0 HOT RECENT RAW MEMORY", tuple(picked[-cfg.max_items_per_tier :]))


def _episodic_tier(events: list[MemoryEvent], question: str, cfg: HierarchicalMemoryConfig) -> MemoryTier:
    requested = _requested_age(question)
    if requested is not None:
        filtered = _filter_events_for_question([ev for ev in events if ev.age_days == requested], question)
        picked = [ev.render() for ev in filtered]
        if not picked:
            picked = [f"No event found for age {requested} days ago in warm episodic memory."]
        return MemoryTier("L1", "L1 WARM EPISODIC MEMORY", tuple(picked[: cfg.max_items_per_tier]))

    days: dict[int, list[MemoryEvent]] = defaultdict(list)
    for ev in events:
        if ev.age_days <= cfg.warm_days:
            days[ev.day].append(ev)
    items = []
    for day in sorted(days, reverse=True)[: cfg.max_items_per_tier]:
        rendered = "; ".join(f"{ev.kind}/{ev.key}={ev.value}" for ev in days[day])
        items.append(f"day {day:+04d}: {rendered}")
    return MemoryTier("L1", "L1 WARM EPISODIC MEMORY", tuple(items))


def _semantic_tier(events: list[MemoryEvent], question: str, cfg: HierarchicalMemoryConfig) -> MemoryTier:
    del cfg
    items: list[str] = []
    dinner_counts = Counter(ev.value for ev in events if ev.kind == "meal" and ev.key == "dinner")
    if dinner_counts:
        value, count = dinner_counts.most_common(1)[0]
        count_parts = "; ".join(f"{name}={num}" for name, num in sorted(dinner_counts.items()))
        items.append(f"Dinner counts across all meal events: {count_parts}.")
        items.append(f"Most common dinner pattern: {value} ({count} mentions).")

    latest_by_key: dict[tuple[str, str], MemoryEvent] = {}
    for ev in sorted(events, key=lambda e: e.day):
        if ev.kind in {"preference", "profile", "decision"}:
            latest_by_key[(ev.kind, ev.key)] = ev
    for (kind, key), ev in sorted(latest_by_key.items()):
        items.append(f"Current {kind} {key}: {ev.value} (from day {ev.day:+04d}, event {ev.event_id}).")

    terms = set(_content_terms(question))
    pinned = [ev for ev in events if ev.importance >= 3 and (ev.key.lower() in terms or ev.kind.lower() in terms or ev.value.lower() in terms)]
    for ev in pinned[:8]:
        items.append(f"Pinned/high-importance memory: {ev.render()}")
    return MemoryTier("L2", "L2 SEMANTIC / CONSOLIDATED MEMORY", tuple(items))


def _flat_retrieval_tier(events: list[MemoryEvent], question: str, cfg: HierarchicalMemoryConfig) -> MemoryTier:
    terms = set(_content_terms(question))
    requested = _requested_age(question)
    scored: list[tuple[int, int, str, MemoryEvent]] = []
    for ev in events:
        hay = f"{ev.kind} {ev.key} {ev.value} {ev.text}".lower()
        score = sum(1 for term in terms if term in hay)
        if requested is not None and ev.age_days == requested:
            score += 8
        if score:
            # Prefer high lexical score, then recent events.  This intentionally
            # biases flat retrieval toward recent stale imports/proposals when
            # they share query words such as "current".
            scored.append((score, ev.age_days, ev.event_id, ev))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    picked = [ev.render() for _score, _age, _event_id, ev in scored[: cfg.max_items_per_tier]]
    if not picked:
        picked = ["No raw events matched the query terms in the flat retriever."]
    return MemoryTier("FLAT", "FLAT RAW RETRIEVAL MEMORY", tuple(picked))


def _cold_tier(events: list[MemoryEvent], question: str, cfg: HierarchicalMemoryConfig) -> MemoryTier:
    requested = _requested_age(question)
    if requested is not None:
        filtered = _filter_events_for_question([ev for ev in events if ev.age_days == requested], question)
        picked = [ev.render() for ev in filtered]
        if not picked:
            picked = [f"No raw archive event found for age {requested} days ago."]
        return MemoryTier("L3", "L3 COLD RAW ARCHIVE", tuple(picked[: cfg.max_items_per_tier]))

    terms = set(_content_terms(question))
    scored: list[tuple[int, MemoryEvent]] = []
    for ev in events:
        hay = f"{ev.kind} {ev.key} {ev.value} {ev.text}".lower()
        score = sum(1 for term in terms if term in hay)
        if score:
            scored.append((score, ev))
    scored.sort(key=lambda item: (-item[0], item[1].age_days, item[1].event_id))
    picked = [ev.render() for _score, ev in scored[: cfg.max_items_per_tier]]
    if not picked:
        picked = ["No matching cold-archive evidence found for the query terms."]
    return MemoryTier("L3", "L3 COLD RAW ARCHIVE", tuple(picked))


def _filter_events_for_question(events: list[MemoryEvent], question: str) -> list[MemoryEvent]:
    q = question.lower()
    if "dinner" in q or "eat" in q or "ate" in q:
        picked = [ev for ev in events if ev.kind == "meal" and ev.key == "dinner"]
        return picked if picked else []
    if "tea" in q:
        picked = [ev for ev in events if ev.kind == "preference" and ev.key == "tea"]
        return picked if picked else []
    if "project" in q or "decision" in q:
        picked = [ev for ev in events if ev.kind == "decision"]
        return picked if picked else []
    return [ev for ev in events if ev.kind != "note"] or events


def _requested_age(question: str) -> int | None:
    q = question.lower()
    if "last night" in q or "yesterday" in q:
        return 1
    match = _DAY_RE.search(q)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return int(value) if value is not None else None


def _content_terms(question: str) -> list[str]:
    stop = {
        "answer",
        "current",
        "days",
        "does",
        "from",
        "have",
        "last",
        "memory",
        "night",
        "what",
        "when",
        "where",
        "which",
        "user",
        "usually",
    }
    terms = []
    for raw in re.findall(r"[a-zA-Z0-9_]+", question.lower()):
        if len(raw) >= 3 and raw not in stop:
            terms.append(raw)
    return terms
