from __future__ import annotations

from compactionbench.memory.hierarchical_memory import (
    build_flat_memory_packet,
    build_flat_memory_prompt,
    build_hierarchical_memory_packet,
    build_hierarchical_memory_prompt,
    parse_memory_events,
    route_question,
)
from compactionbench.taskgen.hierarchical import generate_hierarchical_memory_tasks


def _context() -> str:
    return generate_hierarchical_memory_tasks(streams=1, days=45, seed=0)[0].context


def test_parse_memory_events_reads_synthetic_lines() -> None:
    events = parse_memory_events(_context())

    assert events
    assert any(ev.kind == "meal" and ev.key == "dinner" for ev in events)
    assert any(ev.kind == "preference" and ev.key == "tea" for ev in events)


def test_route_question_selects_expected_tiers() -> None:
    assert route_question("What did I eat last night?")[0] == ("L0", "L1")
    assert route_question("What dinner do I usually eat?")[0] == ("L2",)
    assert route_question("How many times did I eat pasta?")[0] == ("L2",)
    assert route_question("Which dinner was least common?")[0] == ("L2",)
    assert route_question("What did I eat 30 days ago?")[0] == ("L1", "L3")
    assert route_question("What is my current favorite tea?")[0] == ("L2", "L1")


def test_hierarchical_packet_for_old_exact_uses_cold_archive() -> None:
    packet = build_hierarchical_memory_packet(_context(), "What did the user eat for dinner 30 days ago?")

    assert "L3" in packet.selected_tiers
    assert "30 days ago" in packet.evidence_text
    assert "dinner" in packet.evidence_text
    assert "stale imported note" not in packet.evidence_text
    assert packet.evidence_tokens_est > 0


def test_hierarchical_packet_for_pattern_uses_semantic_summary() -> None:
    packet = build_hierarchical_memory_packet(_context(), "What dinner does the user usually eat most often?")

    assert packet.selected_tiers == ("L2",)
    assert "Dinner counts across all meal events" in packet.evidence_text
    assert "Most common dinner pattern" in packet.evidence_text


def test_hierarchical_prompt_hides_tools_and_requires_json() -> None:
    packet = build_hierarchical_memory_packet(_context(), "What is the user's current favorite tea?")
    prompt = build_hierarchical_memory_prompt("What is the user's current favorite tea?", packet=packet)

    assert "HIERARCHICAL MEMORY PACKET" in prompt
    assert "Do not use tools" in prompt
    assert '{"answer": "..."}' in prompt


def test_flat_memory_packet_is_raw_non_hierarchical_baseline() -> None:
    packet = build_flat_memory_packet(_context(), "What is the user's current favorite tea?")
    prompt = build_flat_memory_prompt("What is the user's current favorite tea?", packet=packet)

    assert packet.selected_tiers == ("FLAT",)
    assert packet.strategy == "flat_query_term_retrieval_v1"
    assert "Most common dinner pattern" not in packet.evidence_text
    assert "FLAT RETRIEVAL MEMORY PACKET" in prompt
