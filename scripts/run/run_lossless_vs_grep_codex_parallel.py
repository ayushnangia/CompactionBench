#!/usr/bin/env python3
"""Run paired lossless-full-context vs grep-file Codex experiments.

For each input task, this creates two runs:
- full_context: one prompt with the original context included directly; no tools.
- grep_file: original context saved to full_context.txt; Codex may use shell search.
- paged_context: original context split into page files plus a pager.py search/show tool.
- virtual_context: system-managed evidence packet from paged source; model does not use pager tools.
- virtual_context_8k/24k/48k: same transparent system paging with different resident evidence budgets.
- raw_snippets_prompt/raw_snippets_file: deterministic query-term windows, either pasted or saved as notes.md.
- structured_notes_prompt/structured_notes_file: same virtual-context notes, either pasted or saved as notes.md.
- cli_notes_same_session: Codex itself searches full_context.txt, writes notes.md, then answers in the same session.
- cli_notes_two_stage: Codex itself writes notes.md from full_context.txt; a fresh Codex session answers from notes.md only.
- virtual_context_rlm: transparent RLM/RM3-style pseudo-relevance-feedback retrieval. (Deprecated: not Recursive Language Models.)
- flat_memory_packet: equal-budget flat raw-event retrieval packet with no hierarchy/consolidation.
- rlm_repl_depth0: Recursive Language Model style REPL/code scaffold with context externalized; no sub-LM calls.
- bidirectional_proof: generic model-driven query-contract/proof induction over context.txt with cited proof packet; no benchmark-specific semantic hints.
- bidirectional_proof_repair: same generic proof induction plus an independent model-driven verifier/repair pass; no benchmark-specific semantic hints.

Prompts are passed on stdin to avoid OS command-line length limits.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.core.chunking import estimate_tokens
from compactionbench.memory.babilong_hierarchy import build_babilong_state_packet, build_babilong_state_prompt
from compactionbench.memory.hierarchical_memory import HierarchicalMemoryConfig, build_flat_memory_packet, build_flat_memory_prompt, build_hierarchical_memory_packet, build_hierarchical_memory_prompt, build_oracle_memory_prompt
from compactionbench.memory.paged_context import benchmark_hint, build_paged_prompt, write_paged_memory
from compactionbench.memory.virtual_context import RlmContextConfig, VirtualContextConfig, build_rlm_context_packet, build_virtual_context_packet, build_virtual_context_prompt
from compactionbench.runners.run import CODEX_BIN, _load_codex_session_compaction_events, parse_codex_jsonl, preview
from compactionbench.core.schema import AgentAnswer, RunRecord, TaskRow, TurnTrace, load_task_rows, parse_agent_answer
from compactionbench.core.score import score_one

Arm = Literal[
    "full_context",
    "grep_file",
    "paged_context",
    "virtual_context",
    "virtual_context_8k",
    "virtual_context_24k",
    "virtual_context_48k",
    "virtual_context_rlm",
    "raw_snippets_prompt",
    "raw_snippets_file",
    "structured_notes_prompt",
    "structured_notes_file",
    "cli_notes_same_session",
    "cli_notes_two_stage",
    "hierarchy_packet",
    "hierarchy_oracle",
    "flat_memory_packet",
    "babilong_state_packet",
    "bidirectional_proof",
    "bidirectional_proof_repair",
    "rlm_repl_depth0",
]


@dataclass
class Job:
    job_id: str
    index: int
    arm: Arm
    task_id: str
    source_benchmark: str
    source_task: str
    model: str
    timeout_s: int
    reasoning_effort: str
    verbosity: str
    paged_page_tokens: int = 1200
    paged_overlap_tokens: int = 120
    virtual_page_tokens: int = 800
    virtual_overlap_tokens: int = 100
    virtual_budget_tokens: int = 24000
    hierarchy_budget_tokens: int = 4000
    hierarchy_max_items: int = 24


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--root-dir", required=True)
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--timeout-s", type=int, default=480)
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--verbosity", default="low")
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument(
        "--arm",
        choices=["full_context", "grep_file", "paged_context", "virtual_context", "virtual_context_8k", "virtual_context_24k", "virtual_context_48k", "virtual_context_rlm", "raw_snippets_prompt", "raw_snippets_file", "structured_notes_prompt", "structured_notes_file", "cli_notes_same_session", "cli_notes_two_stage", "hierarchy_packet", "hierarchy_oracle", "flat_memory_packet", "babilong_state_packet", "bidirectional_proof", "bidirectional_proof_repair", "rlm_repl_depth0"],
        action="append",
        default=None,
        help="Optional arm allowlist; default runs full_context and grep_file.",
    )
    p.add_argument("--paged-page-tokens", type=int, default=1200, help="Approximate tokens per page for paged_context arm.")
    p.add_argument("--paged-overlap-tokens", type=int, default=120, help="Approximate page overlap tokens for paged_context arm.")
    p.add_argument("--virtual-page-tokens", type=int, default=800, help="Approximate source-page tokens for virtual_context retrieval.")
    p.add_argument("--virtual-overlap-tokens", type=int, default=100, help="Approximate source-page overlap tokens for virtual_context retrieval.")
    p.add_argument("--virtual-budget-tokens", type=int, default=24000, help="Evidence-packet budget for virtual_context arm.")
    p.add_argument("--hierarchy-budget-tokens", type=int, default=4000, help="Evidence-packet budget for hierarchy_packet and flat_memory_packet arms.")
    p.add_argument("--hierarchy-max-items", type=int, default=24, help="Maximum raw/summary items per hierarchy or flat-memory tier.")
    p.add_argument("--task-id", action="append", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    task_panel = Path(args.tasks)
    root = Path(args.root_dir)
    runs_dir = root / "runs"
    logs_dir = root / "job_logs"
    root.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    rows = load_task_rows(task_panel)
    if args.task_id:
        allowed = set(args.task_id)
        rows = [row for row in rows if row.task_id in allowed]
    if not rows:
        raise RuntimeError("No tasks selected")

    arms: list[Arm] = args.arm or ["full_context", "grep_file"]
    shutil.copy2(task_panel, root / "input_tasks.jsonl")
    jobs = build_jobs(
        rows,
        arms=arms,
        model=args.model,
        timeout_s=args.timeout_s,
        reasoning_effort=args.reasoning_effort,
        verbosity=args.verbosity,
        paged_page_tokens=args.paged_page_tokens,
        paged_overlap_tokens=args.paged_overlap_tokens,
        virtual_page_tokens=args.virtual_page_tokens,
        virtual_overlap_tokens=args.virtual_overlap_tokens,
        virtual_budget_tokens=args.virtual_budget_tokens,
        hierarchy_budget_tokens=args.hierarchy_budget_tokens,
        hierarchy_max_items=args.hierarchy_max_items,
    )
    write_manifest(root, rows, jobs)

    status_path = root / "status.json"
    status: dict[str, Any] = {
        "started_at": now_iso(),
        "completed_at": None,
        "root_dir": str(root),
        "runs_dir": str(runs_dir),
        "task_count": len(rows),
        "job_count": len(jobs),
        "arms": arms,
        "completed": 0,
        "skipped_existing": 0,
        "failed_subprocess": 0,
        "record_errors": 0,
        "running": [],
        "dry_run": bool(args.dry_run),
        "max_workers": args.max_workers,
    }
    update_status(status_path, status)

    if args.dry_run:
        status["completed_at"] = now_iso()
        update_status(status_path, status)
        print(root)
        return 0

    by_task = {row.task_id: row for row in rows}
    lock = threading.Lock()
    results: list[dict[str, Any]] = []
    skip_existing = not args.no_skip_existing

    def run_and_record(job: Job) -> dict[str, Any]:
        with lock:
            status["running"] = sorted(set(status["running"] + [job.job_id]))
            update_status(status_path, status)
        result = run_job(job, by_task[job.task_id], runs_dir=runs_dir, logs_dir=logs_dir, skip_existing=skip_existing)
        with lock:
            results.append(result)
            status["completed"] += 1
            if result.get("skipped_existing"):
                status["skipped_existing"] += 1
            if int(result.get("returncode") or 0) != 0:
                status["failed_subprocess"] += 1
            if result.get("record_error"):
                status["record_errors"] += 1
            status["running"] = [jid for jid in status["running"] if jid != job.job_id]
            update_status(status_path, status)
        return result

    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = [ex.submit(run_and_record, job) for job in jobs]
        for fut in as_completed(futures):
            fut.result()

    write_results(root, results)
    status["completed_at"] = now_iso()
    update_status(status_path, status)
    print(root)
    return 1 if status["failed_subprocess"] else 0


def build_jobs(
    rows: list[TaskRow],
    *,
    arms: list[Arm],
    model: str,
    timeout_s: int,
    reasoning_effort: str,
    verbosity: str,
    paged_page_tokens: int = 1200,
    paged_overlap_tokens: int = 120,
    virtual_page_tokens: int = 800,
    virtual_overlap_tokens: int = 100,
    virtual_budget_tokens: int = 24000,
    hierarchy_budget_tokens: int = 4000,
    hierarchy_max_items: int = 24,
) -> list[Job]:
    jobs: list[Job] = []
    idx = 1
    for row in rows:
        for arm in arms:
            jobs.append(
                Job(
                    job_id=f"{idx:04d}-{arm}-{safe_name(row.task_id)}",
                    index=idx,
                    arm=arm,
                    task_id=row.task_id,
                    source_benchmark=row.source_benchmark,
                    source_task=row.source_task,
                    model=model,
                    timeout_s=timeout_s,
                    reasoning_effort=reasoning_effort,
                    verbosity=verbosity,
                    paged_page_tokens=paged_page_tokens,
                    paged_overlap_tokens=paged_overlap_tokens,
                    virtual_page_tokens=virtual_page_tokens,
                    virtual_overlap_tokens=virtual_overlap_tokens,
                    virtual_budget_tokens=virtual_budget_tokens,
                    hierarchy_budget_tokens=hierarchy_budget_tokens,
                    hierarchy_max_items=hierarchy_max_items,
                )
            )
            idx += 1
    return jobs


def is_virtual_context_arm(arm: str) -> bool:
    return arm == "virtual_context" or arm.startswith("virtual_context_") or arm.startswith("structured_notes_")


def virtual_budget_for_arm(arm: str, *, default_budget: int) -> int:
    if arm == "virtual_context_8k":
        return 8000
    if arm == "virtual_context_24k":
        return 24000
    if arm == "virtual_context_48k":
        return 48000
    if arm in {"structured_notes_prompt", "structured_notes_file"}:
        return 24000
    return default_budget


def run_job(job: Job, task: TaskRow, *, runs_dir: Path, logs_dir: Path, skip_existing: bool) -> dict[str, Any]:
    run_task_id = f"{task.task_id}--{job.arm}"
    expected = runs_dir / job.arm / "codex" / job.model / "off" / f"{safe_name(run_task_id)}.json"
    log_path = logs_dir / f"{job.job_id}.log"
    if skip_existing and expected.exists():
        return basic_result(job, log_path=log_path, expected=expected, returncode=0, skipped=True, duration_s=0.0)

    started = now_iso()
    t0 = time.monotonic()
    try:
        record = run_one(job, task, run_task_id=run_task_id, log_path=log_path)
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(record.model_dump_json(indent=2))
        duration_s = time.monotonic() - t0
        return {
            **basic_result(job, log_path=log_path, expected=expected, returncode=0, skipped=False, duration_s=duration_s),
            "started_at": started,
            "record_error": bool(record.error),
            "parse_ok": record.parse_ok,
            "correct": bool(record.correct),
        }
    except Exception as e:
        duration_s = time.monotonic() - t0
        with log_path.open("a") as log:
            log.write(f"\nRUNNER_EXCEPTION={type(e).__name__}: {e}\n")
        return {
            **basic_result(job, log_path=log_path, expected=expected, returncode=1, skipped=False, duration_s=duration_s),
            "started_at": started,
            "record_error": True,
            "exception": f"{type(e).__name__}: {e}",
        }


def run_one(job: Job, task: TaskRow, *, run_task_id: str, log_path: Path) -> RunRecord:
    if job.arm == "cli_notes_two_stage":
        return run_cli_notes_two_stage(job, task, run_task_id=run_task_id, log_path=log_path)

    start = time.monotonic()
    context_tokens = estimate_tokens(task.context)
    prompt = build_full_context_prompt(task) if job.arm == "full_context" else build_grep_prompt(task) if job.arm == "grep_file" else ""
    turns: list[TurnTrace] = []
    virtual_context_metadata: dict[str, Any] | None = None
    cli_notes_metadata: dict[str, Any] | None = None
    hierarchical_memory_metadata: dict[str, Any] | None = None
    bidirectional_proof_metadata: dict[str, Any] | None = None

    session_id = ""
    final_raw: str | None = None
    parsed: AgentAnswer | None = None
    parse_ok = False
    error: str | None = None
    tool_events = []
    compaction_events = []

    with tempfile.TemporaryDirectory(prefix=f"cbench-{job.arm}-") as tmpdir:
        cwd = Path(tmpdir)
        if job.arm == "grep_file":
            (cwd / "full_context.txt").write_text(task.context)
        elif job.arm in {"bidirectional_proof", "bidirectional_proof_repair"}:
            (cwd / "context.txt").write_text(task.context)
            prompt = build_bidirectional_proof_prompt(task)
        elif job.arm == "cli_notes_same_session":
            (cwd / "full_context.txt").write_text(task.context)
            prompt = build_cli_notes_same_session_prompt(task)
        elif job.arm == "hierarchy_packet":
            hierarchy_config = HierarchicalMemoryConfig(
                budget_tokens=job.hierarchy_budget_tokens,
                max_items_per_tier=job.hierarchy_max_items,
            )
            packet = build_hierarchical_memory_packet(task.context, task.question, config=hierarchy_config)
            hierarchical_memory_metadata = packet.metadata()
            prompt = build_hierarchical_memory_prompt(task.question, packet=packet)
        elif job.arm == "flat_memory_packet":
            hierarchy_config = HierarchicalMemoryConfig(
                budget_tokens=job.hierarchy_budget_tokens,
                max_items_per_tier=job.hierarchy_max_items,
            )
            packet = build_flat_memory_packet(task.context, task.question, config=hierarchy_config)
            hierarchical_memory_metadata = packet.metadata()
            prompt = build_flat_memory_prompt(task.question, packet=packet)
        elif job.arm == "babilong_state_packet":
            hierarchy_config = HierarchicalMemoryConfig(
                budget_tokens=job.hierarchy_budget_tokens,
                max_items_per_tier=job.hierarchy_max_items,
            )
            packet = build_babilong_state_packet(task.context, task.question, config=hierarchy_config)
            hierarchical_memory_metadata = packet.metadata()
            prompt = build_babilong_state_prompt(task.question, packet=packet)
        elif job.arm == "hierarchy_oracle":
            oracle_evidence = str(task.metadata.get("oracle_evidence") or task.gold_answer)
            hierarchical_memory_metadata = {
                "strategy": "oracle_memory_evidence",
                "evidence_tokens_est": estimate_tokens(oracle_evidence),
                "oracle_evidence_preview": preview(oracle_evidence, 400),
            }
            prompt = build_oracle_memory_prompt(task.question, oracle_evidence=oracle_evidence)
        elif job.arm == "paged_context":
            memory = write_paged_memory(
                task.context,
                cwd / "memory",
                page_tokens=job.paged_page_tokens,
                overlap_tokens=job.paged_overlap_tokens,
            )
            prompt = build_paged_prompt(
                task.question,
                memory=memory,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
            )
        elif job.arm == "rlm_repl_depth0":
            (cwd / "context.txt").write_text(task.context)
            (cwd / "rlm_env.py").write_text(build_rlm_env_py())
            prompt = build_rlm_depth0_prompt(task)
        elif job.arm == "virtual_context_rlm":
            virtual_budget_tokens = virtual_budget_for_arm(job.arm, default_budget=job.virtual_budget_tokens)
            memory = write_paged_memory(
                task.context,
                cwd / "virtual_memory",
                page_tokens=job.virtual_page_tokens,
                overlap_tokens=job.virtual_overlap_tokens,
                write_tool=False,
            )
            packet = build_rlm_context_packet(
                memory,
                task.question,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
                config=RlmContextConfig(budget_tokens=virtual_budget_tokens),
            )
            virtual_context_metadata = packet.metadata()
            prompt = build_virtual_context_prompt(
                task.question,
                packet=packet,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
            )
        elif job.arm in {"raw_snippets_prompt", "raw_snippets_file"}:
            notes_text, notes_meta = build_raw_snippets_notes(task)
            virtual_context_metadata = notes_meta
            if job.arm == "raw_snippets_file":
                (cwd / "notes.md").write_text(notes_text)
                prompt = build_notes_file_prompt(
                    task.question,
                    source_benchmark=task.source_benchmark,
                    source_task=task.source_task,
                    notes_kind="RAW GREP SNIPPETS",
                )
            else:
                prompt = build_notes_prompt(
                    task.question,
                    notes_text=notes_text,
                    source_benchmark=task.source_benchmark,
                    source_task=task.source_task,
                    notes_kind="RAW GREP SNIPPETS",
                )
        elif job.arm in {"structured_notes_prompt", "structured_notes_file"}:
            virtual_budget_tokens = virtual_budget_for_arm(job.arm, default_budget=job.virtual_budget_tokens)
            memory = write_paged_memory(
                task.context,
                cwd / "virtual_memory",
                page_tokens=job.virtual_page_tokens,
                overlap_tokens=job.virtual_overlap_tokens,
                write_tool=False,
            )
            packet = build_virtual_context_packet(
                memory,
                task.question,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
                config=VirtualContextConfig(budget_tokens=virtual_budget_tokens),
            )
            virtual_context_metadata = packet.metadata()
            if job.arm == "structured_notes_file":
                (cwd / "notes.md").write_text(packet.evidence_text)
                prompt = build_notes_file_prompt(
                    task.question,
                    source_benchmark=task.source_benchmark,
                    source_task=task.source_task,
                    notes_kind="STRUCTURED NOTES",
                )
            else:
                prompt = build_notes_prompt(
                    task.question,
                    notes_text=packet.evidence_text,
                    source_benchmark=task.source_benchmark,
                    source_task=task.source_task,
                    notes_kind="STRUCTURED NOTES",
                )
        elif is_virtual_context_arm(job.arm):
            virtual_budget_tokens = virtual_budget_for_arm(job.arm, default_budget=job.virtual_budget_tokens)
            memory = write_paged_memory(
                task.context,
                cwd / "virtual_memory",
                page_tokens=job.virtual_page_tokens,
                overlap_tokens=job.virtual_overlap_tokens,
                write_tool=False,
            )
            packet = build_virtual_context_packet(
                memory,
                task.question,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
                config=VirtualContextConfig(budget_tokens=virtual_budget_tokens),
            )
            virtual_context_metadata = packet.metadata()
            prompt = build_virtual_context_prompt(
                task.question,
                packet=packet,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
            )
        turns.append(
            TurnTrace(
                index=1,
                role="user",
                kind="final_question",
                chars=len(prompt),
                tokens_est=estimate_tokens(prompt),
                content_preview=preview(prompt),
            )
        )
        args = codex_args(job, cwd)
        with log_path.open("w") as log:
            log.write(f"started_at={now_iso()}\n")
            log.write(f"arm={job.arm}\n")
            log.write(f"task_id={task.task_id}\n")
            log.write(f"context_tokens_est={context_tokens}\n")
            log.write("cmd=" + json.dumps(args) + "\n\n")
            try:
                proc = subprocess.run(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_s,
                    check=False,
                )
                log.write("returncode=" + str(proc.returncode) + "\n")
                if proc.stderr:
                    log.write("\nSTDERR_TAIL:\n" + proc.stderr[-4000:] + "\n")
                if proc.stdout:
                    log.write("\nSTDOUT_TAIL:\n" + proc.stdout[-8000:] + "\n")
                if proc.returncode != 0:
                    error = f"codex exited {proc.returncode}: stderr_tail={proc.stderr[-500:]} stdout_tail={proc.stdout[-300:]}"
                else:
                    result = parse_codex_jsonl(proc.stdout, condition="off")
                    session_id = result.session_id
                    final_raw = result.text
                    tool_events = result.tool_events
                    compaction_events = result.compaction_events
                    try:
                        parsed = parse_agent_answer(final_raw)
                        parse_ok = True
                    except Exception:
                        parse_ok = False
                    if job.arm == "bidirectional_proof_repair":
                        repair_prompt = build_bidirectional_repair_prompt(task)
                        turns.append(
                            TurnTrace(
                                index=len(turns) + 1,
                                role="user",
                                kind="final_question",
                                chars=len(repair_prompt),
                                tokens_est=estimate_tokens(repair_prompt),
                                content_preview=preview(repair_prompt),
                            )
                        )
                        repair_args = codex_args(job, cwd)
                        log.write("\nREPAIR_CMD=" + json.dumps(repair_args) + "\n")
                        repair_proc = subprocess.run(
                            repair_args,
                            input=repair_prompt,
                            capture_output=True,
                            text=True,
                            timeout=job.timeout_s,
                            check=False,
                        )
                        log.write("repair_returncode=" + str(repair_proc.returncode) + "\n")
                        if repair_proc.stderr:
                            log.write("\nREPAIR_STDERR_TAIL:\n" + repair_proc.stderr[-4000:] + "\n")
                        if repair_proc.stdout:
                            log.write("\nREPAIR_STDOUT_TAIL:\n" + repair_proc.stdout[-8000:] + "\n")
                        if repair_proc.returncode != 0:
                            error = f"repair codex exited {repair_proc.returncode}: stderr_tail={repair_proc.stderr[-500:]} stdout_tail={repair_proc.stdout[-300:]}"
                        else:
                            repair_result = parse_codex_jsonl(repair_proc.stdout, condition="off")
                            session_id = repair_result.session_id or session_id
                            final_raw = repair_result.text
                            tool_events.extend(repair_result.tool_events)
                            compaction_events.extend(repair_result.compaction_events)
                            try:
                                parsed = parse_agent_answer(final_raw)
                                parse_ok = True
                            except Exception:
                                parse_ok = False
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                log.write("\nEXCEPTION=" + error + "\n")

        if job.arm == "cli_notes_same_session":
            cli_notes_metadata = read_notes_metadata(cwd / "notes.md")
        if job.arm in {"bidirectional_proof", "bidirectional_proof_repair"}:
            bidirectional_proof_metadata = read_bidirectional_proof_metadata(cwd, context=task.context)

    if not session_id:
        session_id = f"error-{job.index}-{job.arm}-{safe_name(task.task_id)[:40]}"
    if not compaction_events:
        compaction_events = _load_codex_session_compaction_events(session_id, condition="off")

    turns.append(
        TurnTrace(
            index=len(turns) + 1,
            role="assistant",
            kind="final_question",
            chars=len(final_raw or ""),
            tokens_est=estimate_tokens(final_raw or "") if final_raw else 0,
            content_preview=preview(final_raw or ""),
        )
    )

    metadata = dict(task.metadata)
    metadata.update(
        {
            "experiment": "context_access_strategies",
            "arm": job.arm,
            "original_task_id": task.task_id,
            "context_tokens_est_for_prompt": context_tokens,
            "paged_page_tokens": job.paged_page_tokens if job.arm == "paged_context" else None,
            "paged_overlap_tokens": job.paged_overlap_tokens if job.arm == "paged_context" else None,
            "virtual_page_tokens": job.virtual_page_tokens if is_virtual_context_arm(job.arm) else None,
            "virtual_overlap_tokens": job.virtual_overlap_tokens if is_virtual_context_arm(job.arm) else None,
            "virtual_budget_tokens": virtual_budget_for_arm(job.arm, default_budget=job.virtual_budget_tokens) if is_virtual_context_arm(job.arm) else None,
            "hierarchy_budget_tokens": job.hierarchy_budget_tokens if job.arm in {"hierarchy_packet", "flat_memory_packet", "babilong_state_packet"} else None,
            "hierarchy_max_items": job.hierarchy_max_items if job.arm in {"hierarchy_packet", "flat_memory_packet", "babilong_state_packet"} else None,
            "virtual_context": virtual_context_metadata,
            "cli_notes": cli_notes_metadata,
            "hierarchical_memory": hierarchical_memory_metadata,
            "bidirectional_proof": bidirectional_proof_metadata,
            "rlm": {
                "mode": "repl_depth0",
                "context_file": "context.txt",
                "helper_file": "rlm_env.py",
                "sub_lm_calls": False,
            } if job.arm == "rlm_repl_depth0" else None,
        }
    )
    correct = score_one(
        scorer=task.scorer,
        gold=task.gold_answer,
        gold_aliases=task.gold_answer_aliases,
        answer=parsed.answer if parsed is not None else None,
    )
    return RunRecord(
        task_id=run_task_id,
        source_benchmark=task.source_benchmark,
        source_task=task.source_task,
        source_sample_id=task.source_sample_id,
        harness="codex",
        model=job.model,
        condition="off",
        session_id=session_id,
        chunk_tokens=context_tokens,
        chunk_count=1,
        context_tokens_est=context_tokens,
        scorer=task.scorer,
        gold_answer=task.gold_answer,
        gold_answer_aliases=task.gold_answer_aliases,
        metadata=metadata,
        turns=turns,
        tool_events=tool_events,
        compaction_events=compaction_events,
        final_answer_raw=final_raw,
        final_answer_parsed=parsed,
        parse_ok=parse_ok,
        correct=correct,
        contaminated_by_tools=bool(tool_events),
        error=error,
        duration_s=time.monotonic() - start,
    )


def run_cli_notes_two_stage(job: Job, task: TaskRow, *, run_task_id: str, log_path: Path) -> RunRecord:
    """Two-stage arm: Codex writes notes, then a fresh Codex answers from notes only.

    This directly tests Paras's concern: if grep output is summarized into a
    separate file, does the answer survive once the original grep/results are no
    longer in the model's conversation context?
    """

    start = time.monotonic()
    context_tokens = estimate_tokens(task.context)
    turns: list[TurnTrace] = []
    tool_events = []
    compaction_events = []
    session_id = ""
    final_raw: str | None = None
    parsed: AgentAnswer | None = None
    parse_ok = False
    error: str | None = None
    notes_text = ""
    cli_notes_metadata: dict[str, Any] = {"mode": "two_stage", "notes_exists": False}
    stage1_session = ""
    stage2_session = ""
    stage1_returncode: int | None = None
    stage2_returncode: int | None = None

    stage1_prompt = build_cli_notes_stage1_prompt(task)
    turns.append(
        TurnTrace(
            index=1,
            role="user",
            kind="other",
            chars=len(stage1_prompt),
            tokens_est=estimate_tokens(stage1_prompt),
            content_preview=preview(stage1_prompt),
        )
    )

    with log_path.open("w") as log:
        log.write(f"started_at={now_iso()}\n")
        log.write(f"arm={job.arm}\n")
        log.write(f"task_id={task.task_id}\n")
        log.write(f"context_tokens_est={context_tokens}\n")

        with tempfile.TemporaryDirectory(prefix="cbench-cli-notes-stage1-") as tmp1:
            cwd1 = Path(tmp1)
            (cwd1 / "full_context.txt").write_text(task.context)
            args1 = codex_args(job, cwd1, sandbox="workspace-write")
            log.write("stage1_cmd=" + json.dumps(args1) + "\n\n")
            try:
                proc1 = subprocess.run(
                    args1,
                    input=stage1_prompt,
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_s,
                    check=False,
                )
                stage1_returncode = proc1.returncode
                log.write("stage1_returncode=" + str(proc1.returncode) + "\n")
                if proc1.stderr:
                    log.write("\nSTAGE1_STDERR_TAIL:\n" + proc1.stderr[-4000:] + "\n")
                if proc1.stdout:
                    log.write("\nSTAGE1_STDOUT_TAIL:\n" + proc1.stdout[-8000:] + "\n")
                if proc1.returncode != 0:
                    error = f"stage1 codex exited {proc1.returncode}: stderr_tail={proc1.stderr[-500:]} stdout_tail={proc1.stdout[-300:]}"
                else:
                    result1 = parse_codex_jsonl(proc1.stdout, condition="off")
                    stage1_session = result1.session_id
                    for event in result1.tool_events:
                        event.turn_index = 2
                    tool_events.extend(result1.tool_events)
                    compaction_events.extend(result1.compaction_events)
                    turns.append(
                        TurnTrace(
                            index=2,
                            role="assistant",
                            kind="other",
                            chars=len(result1.text),
                            tokens_est=estimate_tokens(result1.text) if result1.text else 0,
                            content_preview=preview(result1.text),
                        )
                    )
                notes_path = cwd1 / "notes.md"
                cli_notes_metadata = read_notes_metadata(notes_path)
                cli_notes_metadata["mode"] = "two_stage"
                if notes_path.exists():
                    notes_text = notes_path.read_text(errors="replace")
                elif proc1.returncode == 0:
                    # If the agent printed notes instead of writing them, still
                    # test the isolated-note hypothesis while recording fallback.
                    result1 = parse_codex_jsonl(proc1.stdout, condition="off")
                    notes_text = result1.text
                    cli_notes_metadata.update(
                        {
                            "notes_exists": False,
                            "used_stdout_as_notes": True,
                            "notes_tokens_est": estimate_tokens(notes_text),
                            "notes_preview": preview(notes_text, 500),
                        }
                    )
            except Exception as e:
                error = f"stage1 {type(e).__name__}: {e}"
                log.write("\nSTAGE1_EXCEPTION=" + error + "\n")

        if notes_text:
            stage2_prompt = build_cli_notes_stage2_prompt(
                task.question,
                source_benchmark=task.source_benchmark,
                source_task=task.source_task,
            )
            turns.append(
                TurnTrace(
                    index=3,
                    role="user",
                    kind="final_question",
                    chars=len(stage2_prompt),
                    tokens_est=estimate_tokens(stage2_prompt),
                    content_preview=preview(stage2_prompt),
                )
            )
            with tempfile.TemporaryDirectory(prefix="cbench-cli-notes-stage2-") as tmp2:
                cwd2 = Path(tmp2)
                (cwd2 / "notes.md").write_text(notes_text)
                args2 = codex_args(job, cwd2, sandbox="read-only")
                log.write("\nstage2_cmd=" + json.dumps(args2) + "\n\n")
                try:
                    proc2 = subprocess.run(
                        args2,
                        input=stage2_prompt,
                        capture_output=True,
                        text=True,
                        timeout=job.timeout_s,
                        check=False,
                    )
                    stage2_returncode = proc2.returncode
                    log.write("stage2_returncode=" + str(proc2.returncode) + "\n")
                    if proc2.stderr:
                        log.write("\nSTAGE2_STDERR_TAIL:\n" + proc2.stderr[-4000:] + "\n")
                    if proc2.stdout:
                        log.write("\nSTAGE2_STDOUT_TAIL:\n" + proc2.stdout[-8000:] + "\n")
                    if proc2.returncode != 0:
                        error = (error + "; " if error else "") + f"stage2 codex exited {proc2.returncode}: stderr_tail={proc2.stderr[-500:]} stdout_tail={proc2.stdout[-300:]}"
                    else:
                        result2 = parse_codex_jsonl(proc2.stdout, condition="off")
                        stage2_session = result2.session_id
                        session_id = stage2_session
                        final_raw = result2.text
                        for event in result2.tool_events:
                            event.turn_index = 4
                        tool_events.extend(result2.tool_events)
                        compaction_events.extend(result2.compaction_events)
                        try:
                            parsed = parse_agent_answer(final_raw)
                            parse_ok = True
                        except Exception:
                            parse_ok = False
                except Exception as e:
                    error = (error + "; " if error else "") + f"stage2 {type(e).__name__}: {e}"
                    log.write("\nSTAGE2_EXCEPTION=" + error + "\n")
        else:
            error = (error + "; " if error else "") + "stage1 produced no notes_text"

    if not session_id:
        session_id = stage2_session or stage1_session or f"error-{job.index}-{job.arm}-{safe_name(task.task_id)[:40]}"
    if not compaction_events:
        compaction_events = _load_codex_session_compaction_events(session_id, condition="off")

    turns.append(
        TurnTrace(
            index=4,
            role="assistant",
            kind="final_question",
            chars=len(final_raw or ""),
            tokens_est=estimate_tokens(final_raw or "") if final_raw else 0,
            content_preview=preview(final_raw or ""),
        )
    )

    cli_notes_metadata.update(
        {
            "stage1_session_id": stage1_session,
            "stage2_session_id": stage2_session,
            "stage1_returncode": stage1_returncode,
            "stage2_returncode": stage2_returncode,
        }
    )
    metadata = dict(task.metadata)
    metadata.update(
        {
            "experiment": "context_access_strategies",
            "arm": job.arm,
            "original_task_id": task.task_id,
            "context_tokens_est_for_prompt": context_tokens,
            "cli_notes": cli_notes_metadata,
            "virtual_context": None,
            "rlm": None,
        }
    )
    correct = score_one(
        scorer=task.scorer,
        gold=task.gold_answer,
        gold_aliases=task.gold_answer_aliases,
        answer=parsed.answer if parsed is not None else None,
    )
    return RunRecord(
        task_id=run_task_id,
        source_benchmark=task.source_benchmark,
        source_task=task.source_task,
        source_sample_id=task.source_sample_id,
        harness="codex",
        model=job.model,
        condition="off",
        session_id=session_id,
        chunk_tokens=context_tokens,
        chunk_count=1,
        context_tokens_est=context_tokens,
        scorer=task.scorer,
        gold_answer=task.gold_answer,
        gold_answer_aliases=task.gold_answer_aliases,
        metadata=metadata,
        turns=turns,
        tool_events=tool_events,
        compaction_events=compaction_events,
        final_answer_raw=final_raw,
        final_answer_parsed=parsed,
        parse_ok=parse_ok,
        correct=correct,
        contaminated_by_tools=bool(tool_events),
        error=error,
        duration_s=time.monotonic() - start,
    )


def read_notes_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"notes_exists": False}
    text = path.read_text(errors="replace")
    return {
        "notes_exists": True,
        "notes_chars": len(text),
        "notes_tokens_est": estimate_tokens(text),
        "notes_preview": preview(text, 500),
    }


def codex_args(job: Job, cwd: Path, *, sandbox: str | None = None) -> list[str]:
    sandbox = sandbox or ("workspace-write" if job.arm in {"cli_notes_same_session", "cli_notes_two_stage", "bidirectional_proof", "bidirectional_proof_repair"} else "read-only")
    return [
        CODEX_BIN,
        "-m",
        job.model,
        "-a",
        "never",
        "-s",
        sandbox,
        "-C",
        str(cwd),
        "-c",
        f'model_reasoning_effort="{job.reasoning_effort}"',
        "-c",
        f'model_verbosity="{job.verbosity}"',
        "-c",
        'web_search="disabled"',
        "-c",
        "model_auto_compact_token_limit=2000000000",
        "exec",
        "--skip-git-repo-check",
        "--json",
        "-",
    ]


RAW_SNIPPET_STOPWORDS = {
    "about", "after", "again", "against", "answer", "asked", "before", "being", "between",
    "context", "count", "does", "during", "each", "from", "have", "many", "more", "most",
    "question", "should", "source", "than", "that", "their", "there", "these", "this", "times",
    "what", "when", "where", "which", "while", "with", "would", "your",
}


def build_raw_snippets_notes(task: TaskRow, *, max_terms: int = 12, max_snippets: int = 80, window: int = 260) -> tuple[str, dict[str, Any]]:
    """Deterministic query-term windows for the raw-snippet ablation.

    This intentionally does little cleanup: it is the harness retrieving raw grep-like
    windows, not the structured virtual-context/note pipeline.  The paired
    prompt/file arms use this exact same text so storage can be isolated.
    """

    terms = _raw_query_terms(task.question, max_terms=max_terms)
    snippets: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()
    per_term_limit = max(3, max_snippets // max(1, len(terms)))
    for term in terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        count = 0
        for match in pattern.finditer(task.context):
            start = max(0, match.start() - window)
            end = min(len(task.context), match.end() + window)
            # Coarsen spans so nearby term hits do not flood the note sheet.
            span_key = (start // 200, end // 200)
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)
            line_no = task.context.count("\n", 0, match.start()) + 1
            snippets.append(
                {
                    "term": term,
                    "char_start": match.start(),
                    "line": line_no,
                    "text": task.context[start:end].strip(),
                }
            )
            count += 1
            if count >= per_term_limit or len(snippets) >= max_snippets:
                break
        if len(snippets) >= max_snippets:
            break
    snippets.sort(key=lambda item: int(item["char_start"]))

    lines = [
        f"# RAW GREP SNIPPETS for {task.source_benchmark}/{task.source_task}",
        "",
        "These are deterministic grep-style windows selected from question terms.",
        "They are intentionally raw and may include irrelevant or duplicate-looking evidence.",
        "",
        f"Question: {task.question}",
        f"Search terms: {', '.join(terms) if terms else '(none)'}",
        f"Snippet count: {len(snippets)}",
        "",
    ]
    if not snippets:
        lines.append("No snippets found.")
    for idx, item in enumerate(snippets, start=1):
        text = " ".join(str(item["text"]).split())
        lines.append(f"## Snippet {idx}: term `{item['term']}` near line {item['line']} char {item['char_start']}")
        lines.append(text)
        lines.append("")
    notes_text = "\n".join(lines).rstrip() + "\n"
    return notes_text, {
        "strategy": "raw_query_term_snippets",
        "terms": terms,
        "snippet_count": len(snippets),
        "notes_tokens_est": estimate_tokens(notes_text),
        "max_terms": max_terms,
        "max_snippets": max_snippets,
        "window_chars": window,
    }


def _raw_query_terms(question: str, *, max_terms: int) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_'-]*|\d+", question)
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for pos, word in enumerate(words):
        cleaned = word.strip("'\"").lower()
        if len(cleaned) < 3 or cleaned in RAW_SNIPPET_STOPWORDS or cleaned in seen:
            continue
        seen.add(cleaned)
        score = len(cleaned)
        if word[:1].isupper():
            score += 4
        if any(ch.isdigit() for ch in cleaned):
            score += 3
        scored.append((score, -pos, cleaned))
    scored.sort(reverse=True)
    return [term for _score, _neg_pos, term in scored[:max_terms]]


def build_notes_prompt(
    question: str,
    *,
    notes_text: str,
    source_benchmark: str,
    source_task: str,
    notes_kind: str,
) -> str:
    return (
        f"You are answering from {notes_kind} pasted below.\n"
        "Do not use shell commands, files, search tools, or the web.\n"
        "Answer only from the notes. If the notes are insufficient, make the best answer supported by them.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(source_benchmark, source_task)}\n"
        f"<{notes_kind.replace(' ', '_')}>\n"
        f"{notes_text}\n"
        f"</{notes_kind.replace(' ', '_')}>\n\n"
        f"Question:\n{question}\n"
    )


def build_notes_file_prompt(
    question: str,
    *,
    source_benchmark: str,
    source_task: str,
    notes_kind: str,
) -> str:
    return (
        f"You are answering from {notes_kind} saved in ./notes.md.\n"
        "Read/search ./notes.md if helpful. The original full source is NOT available in this arm.\n"
        "Do not use the web. Answer only from notes.md.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(source_benchmark, source_task)}\n"
        f"Question:\n{question}\n"
    )


def build_bidirectional_proof_prompt(task: TaskRow) -> str:
    """Generic proof-induction prompt with no benchmark-specific semantic categories."""

    return (
        "You are running the BIDIRECTIONAL PROOF MEMORY arm.\n"
        "The full source is saved in ./context.txt. Do not use the web.\n"
        "No domain or benchmark categories are provided. Do not assume any fixed ontology or task-specific labels beyond what the question/source reveal.\n"
        "Induce the temporary schema/contract needed for this question only from the question and the source evidence you inspect.\n"
        "Work as a meet-in-the-middle proof search:\n"
        "1. Write a task-local query contract: answer shape, variables, constraints, and what evidence would prove or refute candidate answers.\n"
        "2. Search ./context.txt using shell/python as needed. For whole-context totals, frequencies, ordering, or extrema, do not rely on sampled snippets: write and run an exhaustive source-derived extraction/check script over context.txt.\n"
        "3. From the context side, discover cited evidence handles: exact quotes/spans and any source-derived computation logs that support or refute candidate answers.\n"
        "4. Build a minimal proof path from the query contract to the evidence. Run an independent audit with different search terms or a second script when feasible.\n"
        "5. Write ./proof_packet.json. Use only generic fields; do not rely on predefined semantic categories.\n"
        "6. Write ./proof_audit.json with generic checks: files/commands used, whether evidence was exhaustive or sampled, quote/provenance checks, unresolved risks, and whether the answer is proven/refuted/unknown.\n"
        "The proof packet should be a JSON object with keys like query_contract, induced_schema, search_trace, claims, proof_steps, contradiction_checks, answer.\n"
        "Every claim should include an exact source_quote copied from context.txt when possible; computed claims should include the command/script and source-derived intermediate counts or rows.\n"
        "Only answer with a non-unknown value if the proof and audit support it. Otherwise answer unknown.\n"
        "After writing proof_packet.json and proof_audit.json, return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"Question:\n{task.question}\n"
    )


def build_bidirectional_repair_prompt(task: TaskRow) -> str:
    return (
        "You are the independent verifier/repair pass for the BIDIRECTIONAL PROOF MEMORY arm.\n"
        "The full source is in ./context.txt. The first-pass proof files, if present, are ./proof_packet.json and ./proof_audit.json.\n"
        "Do not use the web. Do not assume benchmark/domain categories or fixed ontology.\n"
        "Your job is generic proof repair:\n"
        "1. Read the first-pass proof and audit. Identify unsupported claims, sampled evidence passed off as exhaustive evidence, arithmetic/counting errors, and answer-format risks.\n"
        "2. Re-search ./context.txt and rerun source-derived scripts as needed. For totals/frequencies/order/extrema, prefer exhaustive scripts over snippets.\n"
        "3. If the first answer is wrong or unsupported, repair it. If no proof is possible, answer unknown.\n"
        "4. Write ./proof_packet_repaired.json and ./proof_repair_audit.json using generic fields only. Include commands/scripts, evidence coverage, source_quote fields when available, and unresolved risks.\n"
        "5. Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"Question:\n{task.question}\n"
    )


def read_bidirectional_proof_metadata(cwd: Path, *, context: str) -> dict[str, Any]:
    json_path = cwd / "proof_packet.json"
    audit_path = cwd / "proof_audit.json"
    repaired_path = cwd / "proof_packet_repaired.json"
    repair_audit_path = cwd / "proof_repair_audit.json"
    md_path = cwd / "proof_packet.md"
    metadata: dict[str, Any] = {
        "proof_json_exists": json_path.exists(),
        "proof_audit_exists": audit_path.exists(),
        "proof_packet_repaired_exists": repaired_path.exists(),
        "proof_repair_audit_exists": repair_audit_path.exists(),
        "proof_md_exists": md_path.exists(),
    }
    packet: Any = None
    if json_path.exists():
        text = json_path.read_text(errors="replace")
        metadata.update(
            {
                "proof_json_chars": len(text),
                "proof_json_tokens_est": estimate_tokens(text),
                "proof_json_preview": preview(text, 700),
            }
        )
        try:
            packet = json.loads(text)
            metadata["proof_json_parse_ok"] = True
        except Exception as e:
            metadata["proof_json_parse_ok"] = False
            metadata["proof_json_error"] = f"{type(e).__name__}: {e}"
    else:
        metadata["proof_json_parse_ok"] = False
    audit: Any = None
    if audit_path.exists():
        audit_text = audit_path.read_text(errors="replace")
        metadata.update(
            {
                "proof_audit_chars": len(audit_text),
                "proof_audit_tokens_est": estimate_tokens(audit_text),
                "proof_audit_preview": preview(audit_text, 700),
            }
        )
        try:
            audit = json.loads(audit_text)
            metadata["proof_audit_parse_ok"] = True
        except Exception as e:
            metadata["proof_audit_parse_ok"] = False
            metadata["proof_audit_error"] = f"{type(e).__name__}: {e}"
    else:
        metadata["proof_audit_parse_ok"] = False
    repaired: Any = None
    if repaired_path.exists():
        repaired_text = repaired_path.read_text(errors="replace")
        metadata.update(
            {
                "proof_packet_repaired_chars": len(repaired_text),
                "proof_packet_repaired_tokens_est": estimate_tokens(repaired_text),
                "proof_packet_repaired_preview": preview(repaired_text, 700),
            }
        )
        try:
            repaired = json.loads(repaired_text)
            metadata["proof_packet_repaired_parse_ok"] = True
        except Exception as e:
            metadata["proof_packet_repaired_parse_ok"] = False
            metadata["proof_packet_repaired_error"] = f"{type(e).__name__}: {e}"
    else:
        metadata["proof_packet_repaired_parse_ok"] = False
    repair_audit: Any = None
    if repair_audit_path.exists():
        repair_audit_text = repair_audit_path.read_text(errors="replace")
        metadata.update(
            {
                "proof_repair_audit_chars": len(repair_audit_text),
                "proof_repair_audit_tokens_est": estimate_tokens(repair_audit_text),
                "proof_repair_audit_preview": preview(repair_audit_text, 700),
            }
        )
        try:
            repair_audit = json.loads(repair_audit_text)
            metadata["proof_repair_audit_parse_ok"] = True
        except Exception as e:
            metadata["proof_repair_audit_parse_ok"] = False
            metadata["proof_repair_audit_error"] = f"{type(e).__name__}: {e}"
    else:
        metadata["proof_repair_audit_parse_ok"] = False
    if md_path.exists():
        md_text = md_path.read_text(errors="replace")
        metadata.update(
            {
                "proof_md_chars": len(md_text),
                "proof_md_tokens_est": estimate_tokens(md_text),
                "proof_md_preview": preview(md_text, 700),
            }
        )
    quotes = _extract_generic_source_quotes(packet) + _extract_generic_source_quotes(audit) + _extract_generic_source_quotes(repaired) + _extract_generic_source_quotes(repair_audit)
    checked = []
    for quote in quotes[:80]:
        normalized = " ".join(quote.split())
        checked.append(
            {
                "quote_preview": preview(normalized, 180),
                "chars": len(quote),
                "present_exact": quote in context,
                "present_normalized": normalized in " ".join(context.split()),
            }
        )
    metadata["source_quote_count"] = len(quotes)
    metadata["source_quotes_checked"] = checked
    metadata["source_quotes_present_exact"] = sum(1 for item in checked if item["present_exact"])
    metadata["source_quotes_present_normalized"] = sum(1 for item in checked if item["present_normalized"])
    return metadata


def _extract_generic_source_quotes(value: Any) -> list[str]:
    quotes: list[str] = []
    quote_key_re = re.compile(r"(^|_)(source_)?quote(s)?$|citation|evidence", re.IGNORECASE)

    def walk(node: Any, *, key_hint: str = "") -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, key_hint=str(key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key_hint=key_hint)
        elif isinstance(node, str):
            if quote_key_re.search(key_hint) and 8 <= len(node.strip()) <= 2000:
                quotes.append(node.strip())

    walk(value)
    seen: set[str] = set()
    deduped: list[str] = []
    for quote in quotes:
        if quote not in seen:
            seen.add(quote)
            deduped.append(quote)
    return deduped


def build_cli_notes_same_session_prompt(task: TaskRow) -> str:
    return (
        "You are running the CLI-NOTES SAME-SESSION arm.\n"
        "The original source text is saved in ./full_context.txt.\n"
        "First, use grep/sed/awk/python as needed to create a question-conditioned evidence note file at ./notes.md.\n"
        "The notes should contain the question, search strategy/commands, exact evidence snippets with line numbers when possible, and any counts/orderings/calculations needed.\n"
        "After writing notes.md, answer the question. You may verify against full_context.txt, but the point is to externalize your intermediate evidence in notes.md before answering.\n"
        "Do not use the web. Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        f"Question:\n{task.question}\n"
    )


def build_cli_notes_stage1_prompt(task: TaskRow) -> str:
    return (
        "You are stage 1 of the CLI-NOTES TWO-STAGE arm.\n"
        "The original source text is saved in ./full_context.txt. The final-answer agent will NOT have access to this file or your grep outputs.\n"
        "Use grep/sed/awk/python as needed, with the question available, to create a self-contained question-conditioned evidence note file at ./notes.md.\n"
        "notes.md must include: the question, search strategy/commands, exact evidence snippets with line numbers when possible, relevant counts/orderings/calculations, and a short candidate-answer section if supported.\n"
        "Make notes.md sufficient for a fresh agent to answer without seeing full_context.txt.\n"
        "Do not use the web. After writing notes.md, return exactly: {\"notes_path\": \"notes.md\", \"status\": \"done\"}.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        f"Question:\n{task.question}\n"
    )


def build_cli_notes_stage2_prompt(question: str, *, source_benchmark: str, source_task: str) -> str:
    return (
        "You are stage 2 of the CLI-NOTES TWO-STAGE arm.\n"
        "A previous CLI agent made question-conditioned notes in ./notes.md. The original full source is NOT available.\n"
        "Read/search notes.md if helpful, then answer only from those notes. Do not use the web.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(source_benchmark, source_task)}\n"
        f"Question:\n{question}\n"
    )


def build_full_context_prompt(task: TaskRow) -> str:
    return (
        "You will answer using the original source text below.\n"
        "The source text is provided directly in this prompt, word for word.\n"
        "Do not use shell commands, files, search tools, or the web.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}.\n"
        "Do not include any extra text.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        "<SOURCE_TEXT>\n"
        f"{task.context}\n"
        "</SOURCE_TEXT>\n\n"
        f"Question:\n{task.question}\n"
    )


def build_grep_prompt(task: TaskRow) -> str:
    return (
        "The original source text is saved in the file ./full_context.txt.\n"
        "Use shell search tools such as grep, sed, awk, wc, or python only if helpful.\n"
        "Do not use the web. Do not rely on memory. Answer from the file.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}.\n"
        "Do not include any extra text.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        f"Question:\n{task.question}\n"
    )


def build_rlm_env_py() -> str:
    """Helper module for the lightweight RLM-depth0 Codex arm.

    This is not the official upstream RLM loop; it keeps the older combined
    runner usable by giving Codex an RLM-style REPL/code workspace. The official
    upstream-RLM runner lives in scripts/run/run_rlm_codex_parallel.py.
    """

    return r'''"""Depth-0 Recursive-Language-Model helper functions.

The full source text is stored in ./context.txt.  These helpers are deterministic
Python utilities only; they do not call another language model.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

CONTEXT_PATH = Path("context.txt")


def read_context() -> str:
    return CONTEXT_PATH.read_text(encoding="utf-8")


def iter_chunks(text: str | None = None, *, chars: int = 12000, overlap: int = 600):
    text = read_context() if text is None else str(text)
    step = max(1, chars - max(0, overlap))
    for start in range(0, len(text), step):
        yield start, text[start:start + chars]


def grep(pattern: str, text: str | None = None, *, flags: int = re.IGNORECASE, window: int = 220, limit: int = 100):
    text = read_context() if text is None else str(text)
    out = []
    for match in re.finditer(pattern, text, flags):
        lo = max(0, match.start() - window)
        hi = min(len(text), match.end() + window)
        out.append({
            "start": match.start(),
            "end": match.end(),
            "match": match.group(0),
            "window": text[lo:hi],
        })
        if len(out) >= limit:
            break
    return out


def count_regex(pattern: str, text: str | None = None, *, flags: int = re.IGNORECASE) -> int:
    text = read_context() if text is None else str(text)
    return sum(1 for _ in re.finditer(pattern, text, flags))


def json_answer(value) -> str:
    return json.dumps({"answer": str(value)}, ensure_ascii=False)
'''


def build_rlm_depth0_prompt(task: TaskRow) -> str:
    return (
        "You are running the rlm_repl_depth0 arm: Recursive Language Model style, depth 0.\n"
        "The full source text is externalized in ./context.txt and helper functions are in ./rlm_env.py.\n"
        "Use deterministic Python/search/counting over the external source. This depth-0 arm must NOT call other LLMs, the web, or hidden knowledge.\n"
        "You may run Python code such as `from rlm_env import read_context, grep, iter_chunks, json_answer`.\n"
        "When done, return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        f"Benchmark: {task.source_benchmark} / {task.source_task}\n"
        f"Question:\n{task.question}\n"
    )


def basic_result(job: Job, *, log_path: Path, expected: Path, returncode: int, skipped: bool, duration_s: float) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "task_id": job.task_id,
        "arm": job.arm,
        "source_benchmark": job.source_benchmark,
        "source_task": job.source_task,
        "returncode": returncode,
        "skipped_existing": skipped,
        "completed_at": now_iso(),
        "duration_s": duration_s,
        "log_path": str(log_path),
        "expected_run_path": str(expected),
    }


def write_manifest(root: Path, rows: list[TaskRow], jobs: list[Job]) -> None:
    task_payload = [
        {
            "task_id": row.task_id,
            "source_benchmark": row.source_benchmark,
            "source_task": row.source_task,
            "source_sample_id": row.source_sample_id,
            "scorer": row.scorer,
            "gold_answer": row.gold_answer,
            "context_tokens_est": estimate_tokens(row.context),
            "metadata_json": json.dumps(row.metadata, sort_keys=True),
        }
        for row in rows
    ]
    (root / "task_inventory.json").write_text(json.dumps(task_payload, indent=2))
    write_csv(root / "task_inventory.csv", task_payload)

    job_payload = [asdict(job) for job in jobs]
    (root / "job_manifest.json").write_text(json.dumps(job_payload, indent=2))
    write_csv(root / "job_manifest.csv", job_payload)


def write_results(root: Path, results: list[dict[str, Any]]) -> None:
    results_sorted = sorted(results, key=lambda r: r["job_id"])
    (root / "job_results.json").write_text(json.dumps(results_sorted, indent=2))
    write_csv(root / "job_results.csv", results_sorted)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def update_status(path: Path, status: dict[str, Any]) -> None:
    path.write_text(json.dumps(status, indent=2))


def safe_name(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._:-" else "-" for ch in raw)[:210]


if __name__ == "__main__":
    raise SystemExit(main())
