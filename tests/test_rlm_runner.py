from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from compactionbench.core.schema import TaskRow


def load_runner_module():
    path = Path("scripts/run/run_rlm_codex_parallel.py")
    spec = importlib.util.spec_from_file_location("run_rlm_codex_parallel", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tiny_task() -> TaskRow:
    return TaskRow(
        task_id="babilong-test-1",
        source_benchmark="babilong",
        source_task="qa1",
        source_sample_id="1",
        context="Mary went to the bathroom.",
        question="Where is Mary?",
        gold_answer="bathroom",
        scorer="exact_ci",
    )


def test_depth1_defaults_to_one_recursive_layer() -> None:
    runner = load_runner_module()
    assert runner.default_max_depth("rlm_repl_depth0") == 1
    assert runner.default_max_depth("rlm_repl_depth1") == 2
    assert runner.default_max_depth("rlm_repl_depth1_recursive") == 2


def test_depth1_prompt_allows_sub_lm_calls_and_depth0_forbids_them() -> None:
    runner = load_runner_module()
    task = tiny_task()
    depth0 = runner.build_root_prompt(task, "rlm_repl_depth0")
    depth1 = runner.build_root_prompt(task, "rlm_repl_depth1")
    assert "do not call llm_query" in depth0
    assert "MUST make at least one focused subcall" in depth1
    assert "rlm_query" in depth1
    recursive = runner.build_root_prompt(task, "rlm_repl_depth1_recursive")
    assert "MUST make at least one child RLM call" in recursive


def test_depth1_system_prompt_format_and_helpers() -> None:
    runner = load_runner_module()
    prompt = runner.build_depth1_system_prompt().format(custom_tools_section="")
    setup = runner.build_depth1_setup_code()
    assert "Depth-1 policy" in prompt
    assert "llm_query_batched" in prompt
    assert "ask_rlm_one" in prompt
    assert "def ask_chunks" in setup
    assert "def ask_rlm_chunks" in setup
    assert "def episode_chunks" in setup
    recursive_prompt = runner.build_depth1_recursive_system_prompt().format(custom_tools_section="")
    recursive_setup = runner.build_depth1_recursive_setup_code()
    assert "child RLM subcall" in recursive_prompt
    assert "_depth1_recursive_subcalls" in recursive_setup


def test_parse_rlm_code_block_finalization() -> None:
    runner = load_runner_module()
    raw = '```repl answer["content"] = "{\\"answer\\": \\"37\\"}" answer["ready"] = True ```'
    assert runner.parse_rlm_agent_answer(raw).answer == "37"
    assert runner.parse_rlm_agent_answer('```repl submit_answer("bathroom") ```').answer == "bathroom"
