from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from compactionbench.schema import TaskRow


def load_runner_module():
    path = Path("scripts/run_lossless_vs_grep_codex_parallel.py")
    spec = importlib.util.spec_from_file_location("run_lossless_vs_grep_codex_parallel", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tiny_task() -> TaskRow:
    return TaskRow(
        task_id="generic-proof-test",
        source_benchmark="synthetic",
        source_task="toy",
        source_sample_id="s1",
        context="alpha beta gamma",
        question="Which token follows alpha?",
        gold_answer="beta",
        scorer="exact_ci",
    )


def test_bidirectional_prompt_has_no_benchmark_semantic_hint() -> None:
    runner = load_runner_module()
    prompt = runner.build_bidirectional_proof_prompt(tiny_task())
    repair_prompt = runner.build_bidirectional_repair_prompt(tiny_task())

    for text in (prompt, repair_prompt):
        assert "BIDIRECTIONAL PROOF MEMORY" in text
        assert "BABILong" not in text
        assert "OOLONG" not in text
        assert "roll" not in text.lower()
        assert "spell" not in text.lower()
        assert "location" not in text.lower()
        assert "dinner" not in text.lower()
        assert '{"answer": "..."}' in text
    assert "No domain or benchmark categories are provided" in prompt
    assert "independent verifier/repair pass" in repair_prompt


def test_bidirectional_quote_metadata_validates_only_presence(tmp_path: Path) -> None:
    runner = load_runner_module()
    (tmp_path / "proof_packet.json").write_text(
        '{"claims":[{"claim":"a","source_quote":"alpha beta"},{"claim":"b","source_quote":"missing quote"}]}'
    )
    (tmp_path / "proof_audit.json").write_text(
        '{"checks":[{"evidence":"beta gamma"}],"status":"checked"}'
    )
    (tmp_path / "proof_packet_repaired.json").write_text(
        '{"claims":[{"source_quote":"alpha beta gamma"}],"answer":"gamma"}'
    )

    meta = runner.read_bidirectional_proof_metadata(tmp_path, context="alpha beta gamma")

    assert meta["proof_json_exists"] is True
    assert meta["proof_json_parse_ok"] is True
    assert meta["proof_audit_exists"] is True
    assert meta["proof_audit_parse_ok"] is True
    assert meta["proof_packet_repaired_exists"] is True
    assert meta["proof_packet_repaired_parse_ok"] is True
    assert meta["source_quote_count"] == 4
    assert meta["source_quotes_present_exact"] == 3
    assert meta["source_quotes_present_normalized"] == 3


def test_build_jobs_accepts_bidirectional_proof_arm() -> None:
    runner = load_runner_module()
    jobs = runner.build_jobs(
        [tiny_task()],
        arms=["bidirectional_proof_repair"],
        model="gpt-test",
        timeout_s=10,
        reasoning_effort="low",
        verbosity="low",
    )

    assert len(jobs) == 1
    assert jobs[0].arm == "bidirectional_proof_repair"
