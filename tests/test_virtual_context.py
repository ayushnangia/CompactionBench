from __future__ import annotations

from compactionbench.memory.paged_context import write_paged_memory
from compactionbench.memory.virtual_context import (
    VirtualContextConfig,
    build_virtual_context_packet,
    build_virtual_context_prompt,
)


def test_virtual_context_extracts_babilong_event_trace_and_hides_pager(tmp_path) -> None:
    context = (
        "Novel prose: Mary went to Didlum's shop and sold a clock.\n"
        "More carrier prose about Mary Linden.\n"
        "Sandra moved to the hallway. Mary journeyed to the bathroom.\n"
        "John picked up the football. John travelled to the kitchen.\n"
    )
    memory = write_paged_memory(context, tmp_path / "vmem", page_tokens=30, overlap_tokens=4, write_tool=False)
    packet = build_virtual_context_packet(
        memory,
        "Where is Mary?",
        source_benchmark="babilong",
        source_task="qa1",
        config=VirtualContextConfig(budget_tokens=4000),
    )
    prompt = build_virtual_context_prompt(
        "Where is Mary?",
        packet=packet,
        source_benchmark="babilong",
        source_task="qa1",
    )

    assert "Mary journeyed to the bathroom" in packet.evidence_text
    assert "Didlum" not in packet.evidence_text
    assert "pager.py" not in prompt
    assert "python memory" not in prompt
    assert "system memory kernel" in prompt
    assert packet.selected_page_ids


def test_virtual_context_oolong_retrieves_question_windows(tmp_path) -> None:
    context = (
        "[START OF EPISODE]\n"
        "Laura: I cast Protection from Poison on Keyleth.\n"
        "Matt: The spell takes effect.\n"
        "Marisha: I cast Call Lightning.\n"
        "[END OF EPISODE]\n"
    )
    memory = write_paged_memory(context, tmp_path / "vmem", page_tokens=40, overlap_tokens=5, write_tool=False)
    packet = build_virtual_context_packet(
        memory,
        "What is the first spell cast in the episode?",
        source_benchmark="oolong",
        source_task="singledoc_spells",
        config=VirtualContextConfig(budget_tokens=4000),
    )

    assert "Protection from Poison" in packet.evidence_text
    assert packet.metadata()["strategy"].startswith("transparent_virtual_context")
