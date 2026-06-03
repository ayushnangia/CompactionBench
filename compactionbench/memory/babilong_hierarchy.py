"""Deterministic BABILong state-table hierarchy.

BABILong hides compact BABI-style state transitions inside long carrier text.
This module extracts those transitions into a small hierarchy packet:

- L1 chronological event trace
- L2 current state tables and query-specific derived state
- L3 raw archive summary/fallback note

It is intentionally deterministic so failures are attributable to extraction,
routing, or final-answer reasoning rather than to an opaque memory writer.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..core.chunking import estimate_tokens
from .hierarchical_memory import HierarchicalMemoryConfig, HierarchicalMemoryPacket, MemoryTier, render_hierarchical_packet

BABI_NAMES = ("Mary", "John", "Sandra", "Daniel", "Fred", "Bill", "Jeff", "Julie")
BABI_LOCS = ("bathroom", "bedroom", "garden", "hallway", "kitchen", "office", "school", "cinema", "park")
BABI_OBJECTS = ("football", "apple", "milk")

_NAMES_RE = "|".join(BABI_NAMES)
_LOCS_RE = "|".join(BABI_LOCS)
_OBJS_RE = "|".join(BABI_OBJECTS)
_MOVE_VERB_RE = r"(?:went(?: back)?|journeyed|travelled|traveled|moved)"
_PICKUP_VERB_RE = r"(?:picked up|grabbed|got|took)"
_DROP_VERB_RE = r"(?:dropped|discarded|put down|left)"
_TRANSFER_VERB_RE = r"(?:gave|handed|passed)"

_SINGLE_MOVE_RE = re.compile(rf"\b(?P<name>{_NAMES_RE})\s+{_MOVE_VERB_RE}\s+to\s+the\s+(?P<loc>{_LOCS_RE})\b", re.I)
_PAIR_MOVE_RE = re.compile(rf"\b(?P<a>{_NAMES_RE})\s+and\s+(?P<b>{_NAMES_RE})\s+{_MOVE_VERB_RE}\s+to\s+the\s+(?P<loc>{_LOCS_RE})\b", re.I)
_THEY_MOVE_RE = re.compile(rf"\bthey\s+{_MOVE_VERB_RE}\s+to\s+the\s+(?P<loc>{_LOCS_RE})\b", re.I)
_PRONOUN_MOVE_RE = re.compile(rf"\b(?:he|she)\s+{_MOVE_VERB_RE}\s+to\s+the\s+(?P<loc>{_LOCS_RE})\b", re.I)
_PICKUP_RE = re.compile(rf"\b(?P<name>{_NAMES_RE})\s+{_PICKUP_VERB_RE}\s+the\s+(?P<obj>{_OBJS_RE})\b", re.I)
_DROP_RE = re.compile(rf"\b(?P<name>{_NAMES_RE})\s+{_DROP_VERB_RE}\s+the\s+(?P<obj>{_OBJS_RE})\b", re.I)
_TRANSFER_RE = re.compile(rf"\b(?P<src>{_NAMES_RE})\s+{_TRANSFER_VERB_RE}\s+the\s+(?P<obj>{_OBJS_RE})\s+to\s+(?P<dst>{_NAMES_RE})\b", re.I)


@dataclass(frozen=True)
class BabiEvent:
    index: int
    kind: str
    text: str
    position: int = 0
    people: tuple[str, ...] = ()
    location: str | None = None
    obj: str | None = None
    source: str | None = None
    target: str | None = None

    def render(self) -> str:
        bits = [f"[{self.index:03d}]", self.kind]
        if self.people:
            bits.append("people=" + ",".join(self.people))
        if self.location:
            bits.append(f"location={self.location}")
        if self.obj:
            bits.append(f"object={self.obj}")
        if self.source:
            bits.append(f"source={self.source}")
        if self.target:
            bits.append(f"target={self.target}")
        return " ".join(bits) + f" :: {self.text}"


@dataclass
class BabiState:
    person_locations: dict[str, str] = field(default_factory=dict)
    person_history: dict[str, list[tuple[int, str]]] = field(default_factory=lambda: defaultdict(list))
    object_holders: dict[str, str | None] = field(default_factory=dict)
    object_locations: dict[str, str | None] = field(default_factory=dict)


def build_babilong_state_packet(
    context: str,
    question: str,
    *,
    config: HierarchicalMemoryConfig | None = None,
) -> HierarchicalMemoryPacket:
    """Build a BABILong state-table evidence packet from raw context."""

    cfg = config or HierarchicalMemoryConfig(budget_tokens=1600, max_items_per_tier=40)
    events, state = extract_babi_state(context)
    query_names = _question_names(question)
    query_objects = _question_objects(question)
    tiers = [
        _babi_semantic_tier(state, events, question),
        _babi_trace_tier(events, question, cfg, query_names=query_names, query_objects=query_objects),
        _babi_archive_tier(events),
    ]
    evidence_text = render_hierarchical_packet(
        question,
        tiers,
        route_reason="BABILong state-table hierarchy: extract BABI events, consolidate current state, retain selected trace.",
    )
    while estimate_tokens(evidence_text) > cfg.budget_tokens and len(tiers) > 1:
        tiers = tiers[:-1]
        evidence_text = render_hierarchical_packet(
            question,
            tiers,
            route_reason="BABILong state-table hierarchy; truncated lower-priority tiers to budget.",
        )
    return HierarchicalMemoryPacket(
        strategy="babilong_state_table_hierarchy_v1",
        question=question,
        selected_tiers=tuple(tier.name for tier in tiers),
        evidence_text=evidence_text,
        evidence_tokens_est=estimate_tokens(evidence_text),
        events_total=len(events),
        route_reason="state-table hierarchy over extracted BABI events",
        tiers=tuple(tiers),
    )


def build_babilong_state_prompt(question: str, *, packet: HierarchicalMemoryPacket) -> str:
    return (
        "You are answering from a BABILONG STATE-TABLE MEMORY PACKET.\n"
        "The packet was built by extracting BABI-style movement/object events from long carrier text and consolidating current state.\n"
        "Do not use tools or the web. Answer only from the packet. If the packet is insufficient, answer unknown.\n"
        "For BABILong, return the bare benchmark label: e.g. `office`, not `the office`; `yes`/`no`; or a comma-separated path.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        "<BABILONG_STATE_MEMORY_PACKET>\n"
        f"{packet.evidence_text}\n"
        "</BABILONG_STATE_MEMORY_PACKET>\n\n"
        f"Question:\n{question}\n"
    )


def extract_babi_state(context: str) -> tuple[list[BabiEvent], BabiState]:
    candidates: list[BabiEvent] = []
    last_group: tuple[str, ...] = ()
    last_referents: tuple[str, ...] = ()

    for pos, sent in _sentence_units(context):
        matched = False
        pair = _PAIR_MOVE_RE.search(sent)
        if pair:
            people = (_canon_name(pair.group("a")), _canon_name(pair.group("b")))
            loc = pair.group("loc").lower()
            candidates.append(_event(len(candidates) + 1, "movement", sent, position=pos, people=people, location=loc))
            last_group = people
            last_referents = people
            matched = True

        if not matched:
            they = _THEY_MOVE_RE.search(sent)
            if they and last_group:
                loc = they.group("loc").lower()
                candidates.append(_event(len(candidates) + 1, "movement", sent, position=pos, people=last_group, location=loc))
                last_referents = last_group
                matched = True

        if not matched:
            pronoun = _PRONOUN_MOVE_RE.search(sent)
            if pronoun and len(last_referents) == 1:
                loc = pronoun.group("loc").lower()
                candidates.append(_event(len(candidates) + 1, "movement", sent, position=pos, people=last_referents, location=loc))
                matched = True

        if not matched:
            move = _SINGLE_MOVE_RE.search(sent)
            if move:
                people = (_canon_name(move.group("name")),)
                loc = move.group("loc").lower()
                candidates.append(_event(len(candidates) + 1, "movement", sent, position=pos, people=people, location=loc))
                last_group = people
                last_referents = people
                matched = True

        pickup = _PICKUP_RE.search(sent)
        if pickup:
            name = _canon_name(pickup.group("name"))
            obj = pickup.group("obj").lower()
            candidates.append(_event(len(candidates) + 1, "pickup", sent, position=pos, people=(name,), obj=obj))
            last_referents = (name,)

        drop = _DROP_RE.search(sent)
        if drop:
            name = _canon_name(drop.group("name"))
            obj = drop.group("obj").lower()
            candidates.append(_event(len(candidates) + 1, "drop", sent, position=pos, people=(name,), obj=obj))
            last_referents = (name,)

        transfer = _TRANSFER_RE.search(sent)
        if transfer:
            src = _canon_name(transfer.group("src"))
            dst = _canon_name(transfer.group("dst"))
            obj = transfer.group("obj").lower()
            candidates.append(_event(len(candidates) + 1, "transfer", sent, position=pos, people=(src, dst), obj=obj, source=src, target=dst))
            last_referents = (dst,)

    events = _renumber_events(_largest_dense_event_block(candidates))
    state = _apply_events(events)
    return events, state


def _babi_semantic_tier(state: BabiState, events: list[BabiEvent], question: str) -> MemoryTier:
    lines: list[str] = []
    if not events:
        lines.append("No BABI-style state events were detected in the source.")

    if state.person_locations:
        person_parts = "; ".join(f"{name}={loc}" for name, loc in sorted(state.person_locations.items()))
        lines.append("Current person locations: " + person_parts + ".")

    if state.object_holders or state.object_locations:
        obj_parts = []
        for obj in sorted(set(state.object_holders) | set(state.object_locations)):
            holder = state.object_holders.get(obj)
            loc = state.object_locations.get(obj)
            if holder:
                obj_parts.append(f"{obj}: held_by={holder}, location={loc or 'unknown'}")
            else:
                obj_parts.append(f"{obj}: held_by=none, location={loc or 'unknown'}")
        lines.append("Current object state: " + "; ".join(obj_parts) + ".")

    derived = _derived_query_facts(state, question)
    if derived:
        lines.extend(derived)

    return MemoryTier("L2", "L2 BABILONG STATE TABLE", tuple(lines))


def _babi_trace_tier(
    events: list[BabiEvent],
    question: str,
    cfg: HierarchicalMemoryConfig,
    *,
    query_names: set[str],
    query_objects: set[str],
) -> MemoryTier:
    if not events:
        return MemoryTier("L1", "L1 BABILONG EVENT TRACE", ("No extracted event trace.",))
    q_locs = _question_locations(question)
    selected: list[BabiEvent] = []
    for ev in events:
        if query_names and query_names & set(ev.people):
            selected.append(ev)
        elif query_objects and ev.obj in query_objects:
            selected.append(ev)
        elif q_locs and ev.location in q_locs:
            selected.append(ev)
    if not selected:
        selected = events[-cfg.max_items_per_tier :]
    else:
        selected = selected[-cfg.max_items_per_tier :]
    return MemoryTier("L1", "L1 BABILONG EVENT TRACE", tuple(ev.render() for ev in selected))


def _babi_archive_tier(events: list[BabiEvent]) -> MemoryTier:
    return MemoryTier(
        "L3",
        "L3 RAW ARCHIVE SUMMARY",
        (f"Extracted {len(events)} BABI-style events from the raw archive; carrier prose was ignored.",),
    )


def _derived_query_facts(state: BabiState, question: str) -> list[str]:
    q = question.lower()
    facts: list[str] = []
    for name in sorted(_question_names(question)):
        current = state.person_locations.get(name)
        if current:
            facts.append(f"Derived current location for {name}: {current}.")
        before_loc = _before_location_for_question(state, question, name)
        if before_loc:
            target, answer = before_loc
            facts.append(f"Derived before-location for {name}: before {target}, {name} was in the {answer}.")
    for obj in sorted(_question_objects(question)):
        holder = state.object_holders.get(obj)
        loc = state.object_locations.get(obj)
        if "who" in q and holder:
            facts.append(f"Derived holder for {obj}: {holder}.")
        if loc:
            facts.append(f"Derived current location for {obj}: {loc}.")
    return facts


def _before_location_for_question(state: BabiState, question: str, name: str) -> tuple[str, str] | None:
    match = re.search(rf"before\s+the\s+({_LOCS_RE})", question, re.I)
    if not match:
        return None
    target = match.group(1).lower()
    history = state.person_history.get(name, [])
    previous: str | None = None
    for _idx, loc in history:
        if loc == target and previous is not None:
            return target, previous
        previous = loc
    return None


def _move_person(state: BabiState, name: str, loc: str, event_index: int) -> None:
    state.person_locations[name] = loc
    state.person_history[name].append((event_index, loc))
    for obj, holder in list(state.object_holders.items()):
        if holder == name:
            state.object_locations[obj] = loc


def _apply_events(events: list[BabiEvent]) -> BabiState:
    state = BabiState()
    for ev in events:
        if ev.kind == "movement" and ev.location:
            for name in ev.people:
                _move_person(state, name, ev.location, ev.index)
        elif ev.kind == "pickup" and ev.obj and ev.people:
            holder = ev.people[0]
            state.object_holders[ev.obj] = holder
            state.object_locations[ev.obj] = state.person_locations.get(holder)
        elif ev.kind == "drop" and ev.obj and ev.people:
            actor = ev.people[0]
            state.object_holders[ev.obj] = None
            state.object_locations[ev.obj] = state.person_locations.get(actor)
        elif ev.kind == "transfer" and ev.obj and ev.target:
            state.object_holders[ev.obj] = ev.target
            state.object_locations[ev.obj] = state.person_locations.get(ev.target)
    return state


def _largest_dense_event_block(events: list[BabiEvent], *, max_gap_chars: int = 5000) -> list[BabiEvent]:
    """Drop isolated carrier-prose sentences that accidentally match BABI regexes."""

    if len(events) <= 2:
        return events
    blocks: list[list[BabiEvent]] = []
    current: list[BabiEvent] = []
    previous_pos: int | None = None
    for ev in sorted(events, key=lambda item: item.position):
        if previous_pos is None or ev.position - previous_pos <= max_gap_chars:
            current.append(ev)
        else:
            blocks.append(current)
            current = [ev]
        previous_pos = ev.position
    if current:
        blocks.append(current)
    return max(blocks, key=lambda block: (len(block), -block[0].position))


def _renumber_events(events: list[BabiEvent]) -> list[BabiEvent]:
    return [
        BabiEvent(
            index=idx,
            kind=ev.kind,
            text=ev.text,
            position=ev.position,
            people=ev.people,
            location=ev.location,
            obj=ev.obj,
            source=ev.source,
            target=ev.target,
        )
        for idx, ev in enumerate(events, start=1)
    ]


def _event(
    index: int,
    kind: str,
    text: str,
    *,
    position: int = 0,
    people: tuple[str, ...] = (),
    location: str | None = None,
    obj: str | None = None,
    source: str | None = None,
    target: str | None = None,
) -> BabiEvent:
    return BabiEvent(
        index=index,
        kind=kind,
        text=" ".join(text.split()),
        position=position,
        people=people,
        location=location,
        obj=obj,
        source=source,
        target=target,
    )


def _sentence_units(text: str) -> list[tuple[int, str]]:
    units: list[tuple[int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n+", text):
        unit = text[start : match.start()].strip()
        if unit:
            units.append((start, unit))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        units.append((start, tail))
    return units


def _canon_name(name: str) -> str:
    low = name.lower()
    for candidate in BABI_NAMES:
        if candidate.lower() == low:
            return candidate
    return name[:1].upper() + name[1:].lower()


def _question_names(question: str) -> set[str]:
    return {_canon_name(name) for name in BABI_NAMES if re.search(rf"\b{name}\b", question, re.I)}


def _question_objects(question: str) -> set[str]:
    return {obj for obj in BABI_OBJECTS if re.search(rf"\b{obj}\b", question, re.I)}


def _question_locations(question: str) -> set[str]:
    return {loc for loc in BABI_LOCS if re.search(rf"\b{loc}\b", question, re.I)}
