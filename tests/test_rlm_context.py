from __future__ import annotations

from compactionbench.memory.paged_context import write_paged_memory
from compactionbench.memory.virtual_context import RlmContextConfig, build_rlm_context_packet, build_virtual_context_prompt


def test_rlm_context_builds_expanded_query_packet_without_pager(tmp_path) -> None:
    context = (
        "Alpha unrelated setup text about gardens.\n" * 20
        + "Combat log: Vex rolls an Attack with natural 20.\n"
        + "Combat log: Keyleth rolls an Attack with natural 13.\n"
        + "Spell log: Keyleth casts Call Lightning.\n"
        + "More unrelated filler about shops and travel.\n" * 20
    )
    memory = write_paged_memory(context, tmp_path / "vmem", page_tokens=35, overlap_tokens=5, write_tool=False)
    packet = build_rlm_context_packet(
        memory,
        "What is the most common roll type?",
        source_benchmark="oolong",
        source_task="singledoc_rolls",
        config=RlmContextConfig(budget_tokens=3000, final_top_k=4, expansion_terms=8),
    )
    prompt = build_virtual_context_prompt(
        "What is the most common roll type?",
        packet=packet,
        source_benchmark="oolong",
        source_task="singledoc_rolls",
    )

    assert "RLM/RM3 expanded query model" in packet.evidence_text
    assert "Attack" in packet.evidence_text or "attack" in packet.evidence_text
    assert packet.metadata()["strategy"] == "transparent_virtual_context+rlm_rm3"
    assert "pager.py" not in prompt
    assert "python memory" not in prompt
