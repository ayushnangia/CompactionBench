#!/usr/bin/env python3
"""Run a PEEK-style context-map arm through Codex sequentially.

PEEK is meant for *recurring external contexts*: a sequence of questions over the
same long source.  This runner groups task rows by a stable context key, keeps a
small prompt-resident context map for each group, runs Codex with the current map
and a local ``context.txt`` file, then optionally updates the map using the
upstream ``peek-ai`` CachePolicy.

Typical canary:

    uv run python scripts/run/run_peek_codex_sequential.py \
      --tasks data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl \
      --root-dir artifacts/batches/peek_oolong_canary \
      --peek-updater codex --peek-evolve-steps 4 --max-tasks-per-group 2

Use ``--dry-run`` first to write the manifest without spending model calls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.core.chunking import estimate_tokens
from compactionbench.memory.paged_context import benchmark_hint
from compactionbench.runners.run import CODEX_BIN, _load_codex_session_compaction_events, parse_codex_jsonl, preview
from compactionbench.core.schema import AgentAnswer, RunRecord, TaskRow, TurnTrace, load_task_rows, parse_agent_answer
from compactionbench.core.score import score_one

Arm = Literal["peek_context_map"]
GroupBy = Literal["context_hash", "source_sample_id", "source_task", "all"]
PeekUpdater = Literal["none", "codex", "openai"]


@dataclass
class Job:
    job_id: str
    index: int
    task_id: str
    run_task_id: str
    group_key: str
    group_index: int
    group_task_index: int
    source_benchmark: str
    source_task: str
    model: str
    timeout_s: int
    reasoning_effort: str
    verbosity: str
    peek_token_budget: int
    peek_evolve_steps: int | None
    peek_updater: PeekUpdater
    peek_model: str
    max_trajectory_chars: int
    arm: Arm = "peek_context_map"


class NoopPeekClient:
    """Minimal upstream-PEEK LMClient that disables map edits.

    This keeps dry/smoke plumbing available without extra model calls.  The map
    still travels through the same CachePolicy and Evictor, but the Distiller and
    Cartographer return empty updates.
    """

    def __init__(self) -> None:
        self._last_usage = _peek_usage(0, 0)

    def completion(self, messages: list[dict[str, Any]]) -> str:
        prompt = "\n".join(str(m.get("content", "")) for m in messages)
        self._last_usage = _peek_usage(estimate_tokens(prompt), 40)
        if "cache_candidates" in prompt and "item_tags" in prompt:
            return json.dumps(
                {
                    "diagnosis": "PEEK updater disabled; no trajectory distillation was run.",
                    "item_tags": {},
                    "cache_candidates": [],
                }
            )
        return json.dumps({"reasoning": "PEEK updater disabled.", "operations": []})

    def last_usage(self):  # pragma: no cover - return type comes from optional peek package
        return self._last_usage


class CodexCliPeekClient:
    """Use Codex CLI as the Distiller/Cartographer LM for upstream PEEK."""

    def __init__(
        self,
        *,
        model: str,
        timeout_s: int,
        reasoning_effort: str,
        verbosity: str,
    ) -> None:
        if shutil.which(CODEX_BIN) is None:
            raise RuntimeError("`codex` binary not found in PATH")
        self.model = model
        self.timeout_s = timeout_s
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self._last_usage = _peek_usage(0, 0)

    def completion(self, messages: list[dict[str, Any]]) -> str:
        prompt = self._render_messages(messages)
        self._last_usage = _peek_usage(estimate_tokens(prompt), 0)
        with tempfile.TemporaryDirectory(prefix="peek-policy-codex-") as tmpdir:
            args = codex_exec_args(
                model=self.model,
                cwd=Path(tmpdir),
                timeout_s=self.timeout_s,
                reasoning_effort=self.reasoning_effort,
                verbosity=self.verbosity,
            )
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Codex PEEK policy call exited {proc.returncode}: "
                f"stderr_tail={proc.stderr[-500:]} stdout_tail={proc.stdout[-300:]}"
            )
        result = parse_codex_jsonl(proc.stdout, condition="off")
        out = result.text or proc.stdout.strip()
        self._last_usage = _peek_usage(estimate_tokens(prompt), estimate_tokens(out))
        return out

    def last_usage(self):  # pragma: no cover - return type comes from optional peek package
        return self._last_usage

    @staticmethod
    def _render_messages(messages: list[dict[str, Any]]) -> str:
        parts = [
            "You are the PEEK cache-policy language model. Return only the JSON object requested by the prompt. Do not use shell commands, files, tools, or the web."
        ]
        for msg in messages:
            role = str(msg.get("role", "user")).upper()
            parts.append(f"\n<{role}>\n{msg.get('content', '')}\n</{role}>")
        return "\n".join(parts)


def _peek_usage(input_tokens: int, output_tokens: int):
    try:
        from peek.core.types import Usage

        return Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:  # pragma: no cover - optional dependency absent
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True, help="Input task JSONL panel.")
    p.add_argument("--root-dir", required=True, help="Batch root directory.")
    p.add_argument("--model", default="gpt-5.4-mini", help="Codex model for benchmark answering.")
    p.add_argument("--timeout-s", type=int, default=600)
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--verbosity", default="low")
    p.add_argument("--group-by", choices=["context_hash", "source_sample_id", "source_task", "all"], default="context_hash")
    p.add_argument("--task-id", action="append", default=None, help="Optional task_id allowlist; repeatable.")
    p.add_argument("--max-tasks-per-group", type=int, default=None, help="Optional cap for cheap canaries.")
    p.add_argument("--peek-token-budget", type=int, default=2048, help="Hard token budget for the prompt-resident context map.")
    p.add_argument("--peek-evolve-steps", type=int, default=4, help="Number of tasks per group allowed to update the map; use -1 for unlimited.")
    p.add_argument("--peek-updater", choices=["none", "codex", "openai"], default="codex")
    p.add_argument("--peek-model", default=None, help="Model for Distiller/Cartographer updates. Defaults to --model.")
    p.add_argument("--peek-openai-base-url", default=None, help="Optional OpenAI-compatible base URL for --peek-updater openai.")
    p.add_argument("--max-trajectory-chars", type=int, default=80_000, help="Tail/head budget passed to PEEK Distiller.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    task_panel = Path(args.tasks)
    root = Path(args.root_dir)
    runs_dir = root / "runs"
    logs_dir = root / "job_logs"
    maps_dir = root / "maps"
    root.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    maps_dir.mkdir(parents=True, exist_ok=True)

    rows = load_task_rows(task_panel)
    if args.task_id:
        allowed = set(args.task_id)
        rows = [row for row in rows if row.task_id in allowed]
    if args.max_tasks_per_group is not None:
        rows = limit_tasks_per_group(rows, group_by=args.group_by, cap=args.max_tasks_per_group)
    if not rows:
        raise RuntimeError("No tasks selected")

    shutil.copy2(task_panel, root / "input_tasks.jsonl")
    evolve_steps = None if args.peek_evolve_steps < 0 else int(args.peek_evolve_steps)
    jobs = build_jobs(
        rows,
        group_by=args.group_by,
        model=args.model,
        timeout_s=args.timeout_s,
        reasoning_effort=args.reasoning_effort,
        verbosity=args.verbosity,
        peek_token_budget=args.peek_token_budget,
        peek_evolve_steps=evolve_steps,
        peek_updater=args.peek_updater,
        peek_model=args.peek_model or args.model,
        max_trajectory_chars=args.max_trajectory_chars,
    )
    write_manifest(root, rows, jobs)

    status_path = root / "status.json"
    status: dict[str, Any] = {
        "started_at": now_iso(),
        "completed_at": None,
        "root_dir": str(root),
        "runs_dir": str(runs_dir),
        "maps_dir": str(maps_dir),
        "task_count": len(rows),
        "job_count": len(jobs),
        "group_count": len({job.group_key for job in jobs}),
        "completed": 0,
        "skipped_existing": 0,
        "failed_subprocess": 0,
        "record_errors": 0,
        "dry_run": bool(args.dry_run),
        "group_by": args.group_by,
        "peek_updater": args.peek_updater,
        "peek_token_budget": args.peek_token_budget,
        "peek_evolve_steps": evolve_steps,
    }
    update_status(status_path, status)

    if args.dry_run:
        status["completed_at"] = now_iso()
        update_status(status_path, status)
        print(root)
        return 0

    by_task = {row.task_id: row for row in rows}
    policies: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    skip_existing = not args.no_skip_existing

    for job in jobs:
        expected = expected_run_path(runs_dir, job)
        if skip_existing and expected.exists():
            result = basic_result(job, log_path=logs_dir / f"{job.job_id}.log", expected=expected, returncode=0, skipped=True, duration_s=0.0)
        else:
            policy = policies.get(job.group_key)
            if policy is None:
                policy = make_peek_policy(
                    updater=job.peek_updater,
                    model=job.peek_model,
                    token_budget=job.peek_token_budget,
                    evolve_steps=job.peek_evolve_steps,
                    timeout_s=job.timeout_s,
                    reasoning_effort=job.reasoning_effort,
                    verbosity=job.verbosity,
                    openai_base_url=args.peek_openai_base_url,
                )
                policies[job.group_key] = policy
            result = run_and_update(
                job,
                by_task[job.task_id],
                policy=policy,
                runs_dir=runs_dir,
                logs_dir=logs_dir,
                maps_dir=maps_dir,
            )
        results.append(result)
        status["completed"] += 1
        if result.get("skipped_existing"):
            status["skipped_existing"] += 1
        if int(result.get("returncode") or 0) != 0:
            status["failed_subprocess"] += 1
        if result.get("record_error"):
            status["record_errors"] += 1
        update_status(status_path, status)

    write_results(root, results)
    status["completed_at"] = now_iso()
    update_status(status_path, status)
    print(root)
    return 1 if status["failed_subprocess"] else 0


def build_jobs(
    rows: list[TaskRow],
    *,
    group_by: GroupBy,
    model: str,
    timeout_s: int,
    reasoning_effort: str,
    verbosity: str,
    peek_token_budget: int,
    peek_evolve_steps: int | None,
    peek_updater: PeekUpdater,
    peek_model: str,
    max_trajectory_chars: int,
) -> list[Job]:
    jobs: list[Job] = []
    seen_by_group: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        group_key = group_key_for(row, group_by=group_by)
        seen_by_group[group_key] = seen_by_group.get(group_key, 0) + 1
        group_index = len(seen_by_group) if seen_by_group[group_key] == 1 else list(seen_by_group).index(group_key) + 1
        run_task_id = f"{row.task_id}--peek_context_map"
        jobs.append(
            Job(
                job_id=f"{index:04d}-peek-{safe_name(row.task_id)}",
                index=index,
                task_id=row.task_id,
                run_task_id=run_task_id,
                group_key=group_key,
                group_index=group_index,
                group_task_index=seen_by_group[group_key],
                source_benchmark=row.source_benchmark,
                source_task=row.source_task,
                model=model,
                timeout_s=timeout_s,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
                peek_token_budget=peek_token_budget,
                peek_evolve_steps=peek_evolve_steps,
                peek_updater=peek_updater,
                peek_model=peek_model,
                max_trajectory_chars=max_trajectory_chars,
            )
        )
    return jobs


def limit_tasks_per_group(rows: list[TaskRow], *, group_by: GroupBy, cap: int) -> list[TaskRow]:
    counts: dict[str, int] = {}
    out: list[TaskRow] = []
    for row in rows:
        key = group_key_for(row, group_by=group_by)
        if counts.get(key, 0) >= cap:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(row)
    return out


def group_key_for(row: TaskRow, *, group_by: GroupBy) -> str:
    if group_by == "context_hash":
        return hashlib.sha1(row.context.encode("utf-8")).hexdigest()[:16]
    if group_by == "source_sample_id":
        return f"{row.source_benchmark}:{row.source_sample_id}"
    if group_by == "source_task":
        return f"{row.source_benchmark}:{row.source_task}"
    if group_by == "all":
        return "all"
    raise ValueError(f"Unknown group_by={group_by}")


def make_peek_policy(
    *,
    updater: PeekUpdater,
    model: str,
    token_budget: int,
    evolve_steps: int | None,
    timeout_s: int,
    reasoning_effort: str,
    verbosity: str,
    openai_base_url: str | None,
):
    try:
        from peek import CachePolicy
    except Exception as e:
        raise RuntimeError(
            "The upstream PEEK package is not installed. Run `uv pip install -e artifacts/repos/peek` "
            "after cloning https://github.com/zhuohangu/peek, or install `peek-ai`."
        ) from e

    if updater == "none":
        client = NoopPeekClient()
    elif updater == "codex":
        client = CodexCliPeekClient(
            model=model,
            timeout_s=timeout_s,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
        )
    elif updater == "openai":
        try:
            from peek import OpenAIClient
        except Exception as e:
            raise RuntimeError("OpenAI PEEK updater requires `peek-ai[openai]` or an installed OpenAI client.") from e
        client = OpenAIClient(model=model, base_url=openai_base_url)
    else:
        raise ValueError(f"Unknown peek updater {updater}")

    return CachePolicy(
        client=client,
        token_budget=token_budget,
        evolve_steps=evolve_steps,
        token_counter=estimate_tokens,
    )


def run_and_update(
    job: Job,
    task: TaskRow,
    *,
    policy,
    runs_dir: Path,
    logs_dir: Path,
    maps_dir: Path,
) -> dict[str, Any]:
    expected = expected_run_path(runs_dir, job)
    log_path = logs_dir / f"{job.job_id}.log"
    started = now_iso()
    t0 = time.monotonic()
    try:
        map_before = policy.current_map_text
        record, stdout_tail = run_one(job, task, current_map=map_before, log_path=log_path)
        update_result = None
        update_error = None
        trajectory = build_trajectory(
            task=task,
            current_map=map_before,
            final_raw=record.final_answer_raw or "",
            parse_ok=record.parse_ok,
            stdout_tail=stdout_tail,
            max_chars=job.max_trajectory_chars,
        )
        try:
            update_result = policy.update(trajectory=trajectory, question=task.question)
        except Exception as e:  # PEEK update should not discard benchmark answer.
            update_error = f"{type(e).__name__}: {e}"

        map_after = policy.current_map_text
        save_map_snapshot(maps_dir, job, map_before=map_before, map_after=map_after, policy=policy)
        record.metadata["peek"].update(
            {
                "map_after_tokens_est": estimate_tokens(map_after),
                "policy_steps_after": getattr(policy, "steps", None),
                "update_error": update_error,
                "update_result": summarize_update_result(update_result),
            }
        )
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(record.model_dump_json(indent=2))
        return {
            **basic_result(job, log_path=log_path, expected=expected, returncode=0, skipped=False, duration_s=time.monotonic() - t0),
            "started_at": started,
            "record_error": bool(record.error) or bool(update_error),
            "parse_ok": record.parse_ok,
            "correct": bool(record.correct),
            "map_after_tokens_est": estimate_tokens(map_after),
            "update_error": update_error,
        }
    except Exception as e:
        with log_path.open("a") as log:
            log.write(f"\nRUNNER_EXCEPTION={type(e).__name__}: {e}\n")
        return {
            **basic_result(job, log_path=log_path, expected=expected, returncode=1, skipped=False, duration_s=time.monotonic() - t0),
            "started_at": started,
            "record_error": True,
            "exception": f"{type(e).__name__}: {e}",
        }


def run_one(job: Job, task: TaskRow, *, current_map: str, log_path: Path) -> tuple[RunRecord, str]:
    start = time.monotonic()
    context_tokens = estimate_tokens(task.context)
    prompt = build_peek_prompt(task, current_map=current_map)
    turns = [
        TurnTrace(
            index=1,
            role="user",
            kind="final_question",
            chars=len(prompt),
            tokens_est=estimate_tokens(prompt),
            content_preview=preview(prompt),
        )
    ]

    session_id = ""
    final_raw: str | None = None
    parsed: AgentAnswer | None = None
    parse_ok = False
    parse_mode = "none"
    error: str | None = None
    tool_events = []
    compaction_events = []
    stdout_tail = ""

    with tempfile.TemporaryDirectory(prefix="cbench-peek-") as tmpdir:
        cwd = Path(tmpdir)
        (cwd / "context.txt").write_text(task.context, encoding="utf-8")
        (cwd / "context_map.md").write_text(current_map, encoding="utf-8")
        args = codex_exec_args(
            model=job.model,
            cwd=cwd,
            timeout_s=job.timeout_s,
            reasoning_effort=job.reasoning_effort,
            verbosity=job.verbosity,
        )
        with log_path.open("w") as log:
            log.write(f"started_at={now_iso()}\n")
            log.write(f"arm={job.arm}\n")
            log.write(f"task_id={task.task_id}\n")
            log.write(f"group_key={job.group_key}\n")
            log.write(f"group_task_index={job.group_task_index}\n")
            log.write(f"context_tokens_est={context_tokens}\n")
            log.write(f"map_before_tokens_est={estimate_tokens(current_map)}\n")
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
                stdout_tail = proc.stdout[-12000:]
                log.write("returncode=" + str(proc.returncode) + "\n")
                if proc.stderr:
                    log.write("\nSTDERR_TAIL:\n" + proc.stderr[-4000:] + "\n")
                if proc.stdout:
                    log.write("\nSTDOUT_TAIL:\n" + stdout_tail + "\n")
                if proc.returncode != 0:
                    error = f"codex exited {proc.returncode}: stderr_tail={proc.stderr[-500:]} stdout_tail={proc.stdout[-300:]}"
                else:
                    result = parse_codex_jsonl(proc.stdout, condition="off")
                    session_id = result.session_id
                    final_raw = result.text
                    tool_events = result.tool_events
                    compaction_events = result.compaction_events
                    parsed, parse_ok, parse_mode = parse_answer_with_fallback(final_raw)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                log.write("\nEXCEPTION=" + error + "\n")

    if not session_id:
        session_id = f"error-{job.index}-peek-{safe_name(task.task_id)[:40]}"
    if not compaction_events:
        compaction_events = _load_codex_session_compaction_events(session_id, condition="off")

    turns.append(
        TurnTrace(
            index=2,
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
            "experiment": "peek_context_map",
            "arm": job.arm,
            "original_task_id": task.task_id,
            "context_tokens_est_for_prompt": context_tokens,
            "answer_parse_mode": parse_mode,
            "peek": {
                "paper": "PEEK: Context Map as an Orientation Cache for Long-Context LLM Agents (arXiv:2605.19932)",
                "upstream_repo": "https://github.com/zhuohangu/peek",
                "updater": job.peek_updater,
                "peek_model": job.peek_model,
                "token_budget": job.peek_token_budget,
                "evolve_steps": job.peek_evolve_steps,
                "group_key": job.group_key,
                "group_index": job.group_index,
                "group_task_index": job.group_task_index,
                "map_before_tokens_est": estimate_tokens(current_map),
                "map_before_preview": preview(current_map, limit=400),
            },
        }
    )
    correct = score_one(
        scorer=task.scorer,
        gold=task.gold_answer,
        gold_aliases=task.gold_answer_aliases,
        answer=parsed.answer if parsed is not None else None,
    )
    record = RunRecord(
        task_id=job.run_task_id,
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
    return record, stdout_tail


def parse_answer_with_fallback(raw: str | None) -> tuple[AgentAnswer | None, bool, str]:
    if not raw:
        return None, False, "empty"
    try:
        return parse_agent_answer(raw), True, "json"
    except Exception:
        pass

    cleaned = raw.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))
    # Codex sometimes obeys semantically but drops the required JSON wrapper.
    # Preserve a narrow fallback so scoring still sees the answer string while
    # metadata records that the answer was not strict JSON.
    nonempty_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    candidate = nonempty_lines[-1] if nonempty_lines else cleaned
    for prefix in ("Label:", "Answer:", "Final answer:", "Final Answer:"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip()
            break
    if 0 < len(candidate) <= 4000:
        return AgentAnswer(answer=candidate), True, "text_fallback"
    return None, False, "failed"


def codex_exec_args(
    *,
    model: str,
    cwd: Path,
    timeout_s: int,
    reasoning_effort: str,
    verbosity: str,
) -> list[str]:
    del timeout_s  # timeout is applied by subprocess.run; retained for call-site symmetry.
    return [
        CODEX_BIN,
        "-m",
        model,
        "-a",
        "never",
        "-s",
        "read-only",
        "-C",
        str(cwd),
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-c",
        f'model_verbosity="{verbosity}"',
        "-c",
        'web_search="disabled"',
        "-c",
        "model_auto_compact_token_limit=2000000000",
        "exec",
        "--skip-git-repo-check",
        "--json",
        "-",
    ]


def build_peek_prompt(task: TaskRow, *, current_map: str) -> str:
    return (
        "You are answering with a PEEK-style prompt-resident context map.\n"
        "The original long source is saved in ./context.txt. The current context map is also saved in ./context_map.md and copied below.\n"
        "Use the context map as orientation only: it may help you understand where useful evidence lives, but verify the final answer against ./context.txt.\n"
        "Use shell search tools such as grep, sed, awk, wc, or python only if helpful. Do not use the web.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        "<PEEK_CONTEXT_MAP>\n"
        f"{current_map.rstrip()}\n"
        "</PEEK_CONTEXT_MAP>\n\n"
        f"Benchmark: {task.source_benchmark} / {task.source_task}\n"
        f"Question:\n{task.question}\n"
    )


def build_trajectory(
    *,
    task: TaskRow,
    current_map: str,
    final_raw: str,
    parse_ok: bool,
    stdout_tail: str,
    max_chars: int,
) -> str:
    text = (
        f"Benchmark: {task.source_benchmark} / {task.source_task}\n"
        f"Question: {task.question}\n"
        f"Current context map before run:\n{current_map}\n\n"
        f"Agent final raw answer:\n{final_raw}\n"
        f"Parse OK: {parse_ok}\n\n"
        "Codex JSONL trajectory tail:\n"
        f"{stdout_tail}\n"
    )
    if len(text) <= max_chars:
        return text
    head = max_chars // 3
    tail = max_chars - head - 80
    return text[:head] + "\n... [trajectory truncated for PEEK distiller] ...\n" + text[-tail:]


def summarize_update_result(update_result) -> dict[str, Any] | None:
    if update_result is None:
        return None
    usage = getattr(update_result, "usage", None)
    distiller = getattr(update_result, "distiller", None)
    return {
        "operations_applied": getattr(update_result, "operations_applied", None),
        "map_tokens_est": estimate_tokens(getattr(update_result, "map_text", "")),
        "distiller_diagnosis": preview(getattr(distiller, "diagnosis", ""), limit=500) if distiller is not None else None,
        "cache_candidate_count": len(getattr(distiller, "cache_candidates", []) or []) if distiller is not None else None,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
        }
        if usage is not None
        else None,
    }


def save_map_snapshot(maps_dir: Path, job: Job, *, map_before: str, map_after: str, policy) -> None:
    group_dir = maps_dir / safe_name(job.group_key)
    group_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{job.group_task_index:03d}-{safe_name(job.task_id)}"
    (group_dir / f"{prefix}-before.md").write_text(map_before, encoding="utf-8")
    (group_dir / f"{prefix}-after.md").write_text(map_after, encoding="utf-8")
    try:
        policy.save(group_dir / "latest.peek.json")
    except Exception:
        (group_dir / "latest.md").write_text(map_after, encoding="utf-8")


def expected_run_path(runs_dir: Path, job: Job) -> Path:
    return runs_dir / job.arm / "codex" / job.model / "off" / f"{safe_name(job.run_task_id)}.json"


def basic_result(job: Job, *, log_path: Path, expected: Path, returncode: int, skipped: bool, duration_s: float) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "task_id": job.task_id,
        "run_task_id": job.run_task_id,
        "arm": job.arm,
        "group_key": job.group_key,
        "group_task_index": job.group_task_index,
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
            "context_hash": hashlib.sha1(row.context.encode("utf-8")).hexdigest()[:16],
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
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def update_status(path: Path, status: dict[str, Any]) -> None:
    path.write_text(json.dumps(status, indent=2))


def safe_name(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._:-" else "-" for ch in raw)[:180]


if __name__ == "__main__":
    raise SystemExit(main())
