from __future__ import annotations

import subprocess

from compactionbench.memory.paged_context import build_paged_prompt, write_paged_memory


def test_write_paged_memory_emits_pages_and_tool(tmp_path) -> None:
    context = (
        "Mary went to the kitchen.\n"
        "John moved the football to the garden.\n"
        + "Neutral filler sentence.\n" * 80
        + "Fred gave the apple to Mary.\n"
    )
    memory = write_paged_memory(context, tmp_path / "memory", page_tokens=40, overlap_tokens=5)

    assert memory.page_count > 1
    assert (tmp_path / "memory" / "manifest.json").exists()
    assert (tmp_path / "memory" / "page_index.jsonl").exists()
    assert (tmp_path / "memory" / "page_table.md").exists()
    assert (tmp_path / "memory" / "pager.py").exists()

    prompt = build_paged_prompt("Who received the apple?", memory=memory)
    assert "PAGED EXTERNAL MEMORY" in prompt
    assert "python memory/pager.py search" in prompt
    assert "Who received the apple?" in prompt


def test_pager_tool_search_and_show(tmp_path) -> None:
    context = (
        "Alpha setup line.\n"
        + "boring filler\n" * 100
        + "Needle fact: Fred handed the apple to Mary.\n"
        + "more filler\n" * 20
    )
    memory = write_paged_memory(context, tmp_path / "memory", page_tokens=45, overlap_tokens=5)

    search = subprocess.run(
        ["python", "memory/pager.py", "search", "apple Mary", "--top-k", "3"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Needle fact" in search.stdout
    assert "page" in search.stdout

    grep = subprocess.run(
        ["python", "memory/pager.py", "grep", "Needle fact", "--context", "0"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "apple" in grep.stdout
