from __future__ import annotations

from compactionbench.babilong_hierarchy import build_babilong_state_packet, build_babilong_state_prompt, extract_babi_state


def test_extract_babi_state_handles_pair_and_they_coreference() -> None:
    context = (
        "Mary and Daniel went back to the garden. "
        "Then they travelled to the bathroom. "
        "Daniel and John journeyed to the hallway. "
        "Afterwards they moved to the kitchen."
    )

    events, state = extract_babi_state(context)

    assert len(events) == 4
    assert state.person_locations["Mary"] == "bathroom"
    assert state.person_locations["Daniel"] == "kitchen"
    assert state.person_locations["John"] == "kitchen"


def test_babilong_state_packet_derives_before_location() -> None:
    context = (
        "Bill went to the school. "
        "Fred went to the office. "
        "Julie journeyed to the park. "
        "Fred went to the cinema."
    )

    packet = build_babilong_state_packet(context, "Where was Fred before the cinema?")

    assert packet.strategy == "babilong_state_table_hierarchy_v1"
    assert "Derived before-location for Fred: before cinema, Fred was in the office." in packet.evidence_text
    assert "L2" in packet.selected_tiers


def test_babilong_state_prompt_hides_tools() -> None:
    packet = build_babilong_state_packet("Mary went to the hallway.", "Where is Mary?")
    prompt = build_babilong_state_prompt("Where is Mary?", packet=packet)

    assert "BABILONG STATE-TABLE MEMORY PACKET" in prompt
    assert "Do not use tools" in prompt
    assert '{"answer": "..."}' in prompt
