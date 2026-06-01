from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from compactionbench.schema import TaskRow


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_peek_codex_sequential.py"
_spec = importlib.util.spec_from_file_location("run_peek_codex_sequential", SCRIPT)
assert _spec is not None and _spec.loader is not None
peek_runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = peek_runner
_spec.loader.exec_module(peek_runner)


def _task(task_id: str, context: str = "alpha beta") -> TaskRow:
    return TaskRow(
        task_id=task_id,
        source_benchmark="synthetic",
        source_task="toy",
        source_sample_id="sample-1",
        context=context,
        question="What is the answer?",
        gold_answer="beta",
        scorer="exact_ci",
    )


def test_group_key_context_hash_is_stable_for_same_context() -> None:
    a = _task("a", context="same context")
    b = _task("b", context="same context")
    c = _task("c", context="different context")

    assert peek_runner.group_key_for(a, group_by="context_hash") == peek_runner.group_key_for(b, group_by="context_hash")
    assert peek_runner.group_key_for(a, group_by="context_hash") != peek_runner.group_key_for(c, group_by="context_hash")


def test_limit_tasks_per_group_keeps_input_order() -> None:
    rows = [_task("a", "g1"), _task("b", "g1"), _task("c", "g2"), _task("d", "g2")]

    limited = peek_runner.limit_tasks_per_group(rows, group_by="context_hash", cap=1)

    assert [row.task_id for row in limited] == ["a", "c"]


def test_build_peek_prompt_contains_map_context_file_and_json_contract() -> None:
    task = _task("a")
    prompt = peek_runner.build_peek_prompt(task, current_map="## CONTEXT ROADMAP\n[cr-00001] Toy map")

    assert "./context.txt" in prompt
    assert "<PEEK_CONTEXT_MAP>" in prompt
    assert "[cr-00001] Toy map" in prompt
    assert '{"answer": "..."}' in prompt
    assert task.question in prompt


def test_parse_answer_with_fallback_accepts_label_prefix() -> None:
    parsed, ok, mode = peek_runner.parse_answer_with_fallback("Label: False")

    assert ok is True
    assert mode == "text_fallback"
    assert parsed is not None
    assert parsed.answer == "False"
