#!/usr/bin/env python3
"""Run the official Recursive Language Model scaffold on CompactionBench tasks.

This runner is intentionally a *new-arm only* runner.  It should be merged with
already-completed full_context / grep_file / paged_context / virtual_context
baselines offline; do not rerun those baselines unless the panel/model/settings
change.

Arms emitted by this script:
- rlm_repl_depth0: upstream RLM loop + LocalREPL.  The long source is
  externalized into the REPL as `context` and `context.txt`; the root model sees
  only metadata plus the question and writes Python over the external state.  The
  prompt forbids llm_query/rlm_query subcalls so this is the depth-0/no-sub-LM
  comparison arm.
- rlm_repl_depth1: RLM scaffold with one recursive layer enabled. The root REPL
  must use at least one sub-LM/sub-RLM helper call, then aggregate evidence in Python.
- rlm_repl_depth1_recursive: stricter depth-1 arm that must use at least one
  child RLM call through rlm_query/rlm_query_batched.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
RLM_REPO = ROOT / "artifacts" / "repos" / "rlm"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RLM_REPO) not in sys.path:
    sys.path.insert(0, str(RLM_REPO))

from compactionbench.core.chunking import estimate_tokens
from compactionbench.memory.paged_context import benchmark_hint
from compactionbench.runners.run import CODEX_BIN, parse_codex_jsonl, preview
from compactionbench.core.schema import (
    AgentAnswer,
    RunRecord,
    TaskRow,
    ToolEvent,
    TurnTrace,
    load_task_rows,
    parse_agent_answer,
)
from compactionbench.core.score import score_one

try:
    import rlm.core.rlm as rlm_core
    from rlm import RLM
    from rlm.clients.base_lm import BaseLM
    from rlm.core.types import ModelUsageSummary, UsageSummary
    from rlm.logger import RLMLogger
except Exception as e:  # pragma: no cover - gives clear setup error
    raise RuntimeError(
        "Could not import upstream RLM package. Run: uv pip install -e artifacts/repos/rlm"
    ) from e

Arm = Literal["rlm_repl_depth0", "rlm_repl_depth1", "rlm_repl_depth1_recursive"]
ARMS: tuple[Arm, ...] = ("rlm_repl_depth0", "rlm_repl_depth1", "rlm_repl_depth1_recursive")
DEFAULT_ARM: Arm = "rlm_repl_depth0"


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
    per_call_timeout_s: int
    max_iterations: int
    max_depth: int
    reasoning_effort: str
    verbosity: str


_ORIGINAL_RLM_GET_CLIENT = rlm_core.get_client
_RLM_CLIENT_CONTEXT = threading.local()


class CodexCliLM(BaseLM):
    """Minimal upstream-RLM BaseLM adapter backed by Codex CLI."""

    def __init__(
        self,
        *,
        model_name: str,
        reasoning_effort: str,
        verbosity: str,
        timeout_s: int,
    ) -> None:
        super().__init__(model_name=model_name, timeout=timeout_s)
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.call_logs: list[dict[str, Any]] = []
        self.tool_events: list[ToolEvent] = []
        self._lock = threading.Lock()

    def completion(self, prompt: str | list[dict[str, Any]], model: str | None = None) -> str:
        controller_mode = isinstance(prompt, list)
        if controller_mode:
            prompt_text = "\n\n".join(
                f"[{msg.get('role', 'user').upper()}]\n{msg.get('content', '')}" for msg in prompt
            )
            wrapped_prompt = (
                "You are the neural controller inside an official Recursive Language Model (RLM) scaffold.\n"
                "TEXT-ONLY COMPLETION RULE: do not call command_execution, shell, file, web, patch, or any Codex tool.\n"
                "Do not run even harmless commands such as true, pwd, ls, cat, or echo. Tool use contaminates the benchmark.\n"
                "The RLM scaffold, not Codex, will execute any ```repl code blocks you emit.\n"
                "Your only valid output is assistant text plus ```repl blocks for the RLM REPL when useful.\n"
                "When done, set answer['content'] and answer['ready'] inside a ```repl block as required by the RLM system prompt.\n\n"
                + prompt_text
            )
        else:
            prompt_text = str(prompt)
            wrapped_prompt = (
                "You are a plain one-shot sub-LM called from inside a Recursive Language Model program.\n"
                "TEXT-ONLY COMPLETION RULE: do not call command_execution, shell, file, web, patch, or any Codex tool.\n"
                "Do not emit ```repl blocks unless the prompt explicitly asks for code as text.\n"
                "Answer the subtask directly, concisely, and from the provided chunk/evidence only.\n\n"
                + prompt_text
            )
        prompt_tokens = estimate_tokens(wrapped_prompt)

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="cbench-rlm-lm-") as tmpdir:
            cwd = Path(tmpdir)
            args = self._codex_args(cwd)
            proc = subprocess.run(
                args,
                input=wrapped_prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        duration_s = time.monotonic() - t0

        if proc.returncode != 0:
            response_text = (
                "I could not complete this RLM step because the Codex subprocess failed.\n"
                f"stderr tail: {proc.stderr[-1000:]}\nstdout tail: {proc.stdout[-1000:]}"
            )
            session_id = ""
            parsed_tool_events: list[ToolEvent] = []
        else:
            result = parse_codex_jsonl(proc.stdout, condition="off")
            response_text = result.text.strip()
            session_id = result.session_id
            parsed_tool_events = result.tool_events
            if not response_text:
                response_text = proc.stdout[-4000:].strip()

        completion_tokens = estimate_tokens(response_text)
        with self._lock:
            self.total_calls += 1
            call_index = self.total_calls
            self.last_prompt_tokens = prompt_tokens
            self.last_completion_tokens = completion_tokens
            self.total_input_tokens += prompt_tokens
            self.total_output_tokens += completion_tokens
            for event in parsed_tool_events:
                self.tool_events.append(
                    ToolEvent(
                        turn_index=None,
                        tool_name=event.tool_name,
                        raw={**event.raw, "rlm_lm_call_index": call_index},
                    )
                )
            self.call_logs.append(
                {
                    "call_index": call_index,
                    "model": model or self.model_name,
                    "session_id": session_id,
                    "returncode": proc.returncode,
                    "duration_s": duration_s,
                    "prompt_tokens_est": prompt_tokens,
                    "completion_tokens_est": completion_tokens,
                    "tool_event_count": len(parsed_tool_events),
                    "call_kind": "rlm_controller" if controller_mode else "plain_sub_lm",
                    "response_preview": preview(response_text, 320),
                    "stderr_tail": proc.stderr[-1000:],
                }
            )
        return response_text

    async def acompletion(
        self, prompt: str | list[dict[str, Any]], model: str | None = None
    ) -> str:
        return await asyncio.to_thread(self.completion, prompt, model)

    def get_usage_summary(self) -> UsageSummary:
        return UsageSummary(
            model_usage_summaries={
                self.model_name: ModelUsageSummary(
                    total_calls=self.total_calls,
                    total_input_tokens=self.total_input_tokens,
                    total_output_tokens=self.total_output_tokens,
                    total_cost=None,
                )
            }
        )

    def get_last_usage(self) -> ModelUsageSummary:
        return ModelUsageSummary(
            total_calls=1,
            total_input_tokens=self.last_prompt_tokens,
            total_output_tokens=self.last_completion_tokens,
            total_cost=None,
        )

    def _codex_args(self, cwd: Path) -> list[str]:
        return [
            CODEX_BIN,
            "-m",
            self.model_name,
            "-a",
            "never",
            "-s",
            "read-only",
            "-C",
            str(cwd),
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-c",
            f'model_verbosity="{self.verbosity}"',
            "-c",
            'web_search="disabled"',
            "-c",
            "model_auto_compact_token_limit=2000000000",
            "exec",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--json",
            "-",
        ]


def patched_rlm_get_client(backend: str, backend_kwargs: dict[str, Any]) -> BaseLM:
    """Thread-safe get_client hook for the synthetic `codex_cli` backend."""

    if backend != "codex_cli":
        return _ORIGINAL_RLM_GET_CLIENT(backend, backend_kwargs)
    clients = getattr(_RLM_CLIENT_CONTEXT, "clients", None)
    if clients is None:
        raise RuntimeError("codex_cli RLM backend used without thread-local client context")
    client = CodexCliLM(
        model_name=backend_kwargs.get("model_name") or "gpt-5.4-mini",
        reasoning_effort=backend_kwargs.get("reasoning_effort") or "high",
        verbosity=backend_kwargs.get("verbosity") or "low",
        timeout_s=int(backend_kwargs.get("timeout_s") or 300),
    )
    clients.append(client)
    return client


# RLM imports get_client into rlm.core.rlm as a module global. Patch once at
# script startup; per-job state is carried by _RLM_CLIENT_CONTEXT so parallel
# jobs do not stomp each other's backend factories.
rlm_core.get_client = patched_rlm_get_client


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--root-dir", required=True)
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--arm", choices=list(ARMS), default=DEFAULT_ARM)
    p.add_argument("--timeout-s", type=int, default=900, help="Whole RLM task timeout.")
    p.add_argument("--per-call-timeout-s", type=int, default=300, help="Timeout for each Codex-backed LM step inside RLM.")
    p.add_argument("--max-iterations", type=int, default=8)
    p.add_argument("--max-depth", type=int, default=None, help="Override recursion cap. Defaults: depth0=1, depth1=2.")
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--verbosity", default="low")
    p.add_argument("--max-workers", type=int, default=4)
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

    shutil.copy2(task_panel, root / "input_tasks.jsonl")
    jobs = build_jobs(
        rows,
        arm=args.arm,
        model=args.model,
        timeout_s=args.timeout_s,
        per_call_timeout_s=args.per_call_timeout_s,
        max_iterations=args.max_iterations,
        max_depth=args.max_depth if args.max_depth is not None else default_max_depth(args.arm),
        reasoning_effort=args.reasoning_effort,
        verbosity=args.verbosity,
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
        "arms": [args.arm],
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
    results: list[dict[str, Any]] = []
    skip_existing = not args.no_skip_existing

    def record_result(job: Job, result: dict[str, Any]) -> None:
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

    if args.max_workers <= 1:
        # Upstream LocalREPL temporarily changes process-wide cwd/stdout. Keep
        # max_workers=1 in-process; use processes for true parallelism below.
        for job in jobs:
            status["running"] = [job.job_id]
            update_status(status_path, status)
            result = run_job(
                job,
                by_task[job.task_id],
                runs_dir=runs_dir,
                logs_dir=logs_dir,
                skip_existing=skip_existing,
            )
            record_result(job, result)
    else:
        # Process-level isolation is important: upstream LocalREPL is not
        # thread-safe because it captures stdout/stderr and chdirs while running
        # model code. A process pool preserves parallel throughput without
        # sharing that global interpreter state.
        status["running"] = [job.job_id for job in jobs]
        update_status(status_path, status)
        with ProcessPoolExecutor(max_workers=args.max_workers) as ex:
            future_to_job = {
                ex.submit(
                    run_job,
                    job,
                    by_task[job.task_id],
                    runs_dir=runs_dir,
                    logs_dir=logs_dir,
                    skip_existing=skip_existing,
                ): job
                for job in jobs
            }
            for fut in as_completed(future_to_job):
                job = future_to_job[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    task = by_task[job.task_id]
                    run_task_id = f"{task.task_id}--{job.arm}"
                    expected = runs_dir / job.arm / "codex" / job.model / "off" / f"{safe_name(run_task_id)}.json"
                    log_path = logs_dir / f"{job.job_id}.log"
                    result = {
                        **basic_result(job, log_path=log_path, expected=expected, returncode=1, skipped=False, duration_s=0.0),
                        "record_error": True,
                        "exception": f"{type(e).__name__}: {e}",
                    }
                record_result(job, result)

    write_results(root, results)
    status["completed_at"] = now_iso()
    update_status(status_path, status)
    print(root)
    return 1 if status["failed_subprocess"] else 0


def build_jobs(
    rows: list[TaskRow],
    *,
    arm: Arm,
    model: str,
    timeout_s: int,
    per_call_timeout_s: int,
    max_iterations: int,
    max_depth: int,
    reasoning_effort: str,
    verbosity: str,
) -> list[Job]:
    jobs: list[Job] = []
    for idx, row in enumerate(rows, start=1):
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
                per_call_timeout_s=per_call_timeout_s,
                max_iterations=max_iterations,
                max_depth=max_depth,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
            )
        )
    return jobs


def run_job(
    job: Job, task: TaskRow, *, runs_dir: Path, logs_dir: Path, skip_existing: bool
) -> dict[str, Any]:
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
    start = time.monotonic()
    context_tokens = estimate_tokens(task.context)
    root_prompt = build_root_prompt(task, job.arm)
    payload = build_context_payload(task)
    logger = RLMLogger()
    clients: list[CodexCliLM] = []
    final_raw: str | None = None
    parsed: AgentAnswer | None = None
    parse_ok = False
    error: str | None = None
    completion: Any = None
    recursive_child_events: list[dict[str, Any]] = []

    def on_subcall_start(depth: int, model: str, prompt_preview: str) -> None:
        recursive_child_events.append(
            {
                "event": "start",
                "depth": depth,
                "model": model,
                "prompt_preview": preview(prompt_preview, 240),
                "time": now_iso(),
            }
        )

    def on_subcall_complete(depth: int, model: str, duration: float, error_or_none: str | None) -> None:
        recursive_child_events.append(
            {
                "event": "complete",
                "depth": depth,
                "model": model,
                "duration_s": duration,
                "error": error_or_none,
                "time": now_iso(),
            }
        )

    with log_path.open("w") as log:
        log.write(f"started_at={now_iso()}\n")
        log.write(f"arm={job.arm}\n")
        log.write(f"task_id={task.task_id}\n")
        log.write(f"source_benchmark={task.source_benchmark}\n")
        log.write(f"source_task={task.source_task}\n")
        log.write(f"context_tokens_est={context_tokens}\n")
        log.write(f"root_prompt_tokens_est={estimate_tokens(root_prompt)}\n")
        log.write(f"official_rlm_repo={RLM_REPO}\n\n")
        try:
            _RLM_CLIENT_CONTEXT.clients = clients
            rlm = RLM(
                backend="codex_cli",  # runtime-patched above
                backend_kwargs={
                    "model_name": job.model,
                    "reasoning_effort": job.reasoning_effort,
                    "verbosity": job.verbosity,
                    "timeout_s": job.per_call_timeout_s,
                },
                environment="local",
                environment_kwargs={"setup_code": build_setup_code(job.arm)},
                max_depth=job.max_depth,
                max_iterations=job.max_iterations,
                max_timeout=job.timeout_s,
                custom_system_prompt=build_system_prompt(job.arm),
                logger=logger,
                verbose=False,
                compaction=False,
                on_subcall_start=on_subcall_start,
                on_subcall_complete=on_subcall_complete,
            )
            completion = rlm.completion(payload, root_prompt=root_prompt)
            final_raw = str(completion.response or "")
            try:
                parsed = parse_rlm_agent_answer(final_raw)
                parse_ok = True
            except Exception as e:
                parse_ok = False
                log.write(f"parse_error={type(e).__name__}: {e}\n")
            log.write("\nRLM_FINAL_RAW_PREVIEW:\n" + preview(final_raw or "", 4000) + "\n")
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            log.write("\nEXCEPTION=" + error + "\n")
        finally:
            if hasattr(_RLM_CLIENT_CONTEXT, "clients"):
                delattr(_RLM_CLIENT_CONTEXT, "clients")

        for client in clients:
            log.write("\nCODEX_LM_CALLS:\n")
            for call in client.call_logs:
                log.write(json.dumps(call, sort_keys=True) + "\n")

    trajectory = scrub_trajectory(getattr(completion, "metadata", None))
    sub_lm_calls = count_repl_sub_lm_calls(trajectory)
    lm_call_count = sum(client.total_calls for client in clients)
    tool_events = [event for client in clients for event in client.tool_events]
    session_id = build_session_id(job, task, clients)

    turns = [
        TurnTrace(
            index=1,
            role="user",
            kind="final_question",
            chars=len(root_prompt),
            tokens_est=estimate_tokens(root_prompt),
            content_preview=preview(root_prompt),
        ),
        TurnTrace(
            index=2,
            role="assistant",
            kind="final_question",
            chars=len(final_raw or ""),
            tokens_est=estimate_tokens(final_raw or "") if final_raw else 0,
            content_preview=preview(final_raw or ""),
        ),
    ]

    metadata = dict(task.metadata)
    metadata.update(
        {
            "experiment": "recursive_language_models_official",
            "arm": job.arm,
            "original_task_id": task.task_id,
            "context_tokens_est_for_prompt": context_tokens,
            "rlm": {
                "paper_meaning": "Recursive Language Model, not relevance/RM3 retrieval",
                "source_repo": str(RLM_REPO.relative_to(ROOT)) if RLM_REPO.exists() else str(RLM_REPO),
                "repo_url": "https://github.com/alexzhang13/rlm",
                "mode": rlm_mode(job.arm),
                "max_depth": job.max_depth,
                "max_iterations": job.max_iterations,
                "root_prompt_tokens_est": estimate_tokens(root_prompt),
                "context_externalization": "source text stored in upstream LocalREPL context variable and context.txt, not in root model prompt",
                "sub_lm_calls_allowed": job.arm == "rlm_repl_depth1",
                "sub_lm_or_rlm_calls_observed": sub_lm_calls,
                "sub_lm_calls_observed": sub_lm_calls,
                "depth0_violation": job.arm == "rlm_repl_depth0" and sub_lm_calls > 0,
                "root_lm_calls": lm_call_count,
                "iteration_count": len(trajectory.get("iterations", [])) if trajectory else 0,
                "recursive_child_call_events": recursive_child_events,
                "recursive_child_call_count": sum(1 for event in recursive_child_events if event.get("event") == "start"),
                "codex_lm_call_logs": [call for client in clients for call in client.call_logs],
            },
            "rlm_trajectory_preview": trajectory,
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
        compaction_events=[],
        final_answer_raw=final_raw,
        final_answer_parsed=parsed,
        parse_ok=parse_ok,
        correct=correct,
        contaminated_by_tools=bool(tool_events),
        error=error,
        duration_s=time.monotonic() - start,
    )


def parse_rlm_agent_answer(raw: str | None) -> AgentAnswer:
    """Parse normal JSON answers plus common RLM code-block finalization text."""

    text = raw or ""
    try:
        return parse_agent_answer(text)
    except Exception as first_error:
        candidates: list[str] = []
        # Common exhausted-iteration fallback: the model's last message is a
        # code block like: answer["content"] = "{\"answer\": \"37\"}".
        for match in re.finditer(
            r"answer\s*\[\s*['\"]content['\"]\s*\]\s*=\s*\"((?:\\.|[^\"\\])*)\"",
            text,
            flags=re.S,
        ):
            try:
                candidates.append(bytes(match.group(1), "utf-8").decode("unicode_escape"))
            except Exception:
                candidates.append(match.group(1))
        for match in re.finditer(
            r"answer\s*\[\s*['\"]content['\"]\s*\]\s*=\s*'((?:\\.|[^'\\])*)'",
            text,
            flags=re.S,
        ):
            try:
                candidates.append(bytes(match.group(1), "utf-8").decode("unicode_escape"))
            except Exception:
                candidates.append(match.group(1))
        for match in re.finditer(r"submit_answer\s*\((.*?)\)", text, flags=re.S):
            literal = match.group(1).strip()
            try:
                value = ast.literal_eval(literal)
            except Exception:
                value = literal.strip("'\"")
            if isinstance(value, dict):
                candidates.append(json.dumps(value))
            else:
                candidates.append(str(value))
        for candidate in candidates:
            try:
                return parse_agent_answer(candidate)
            except Exception:
                # If submit_answer("bathroom") was captured, wrap it.
                if candidate and "{" not in candidate:
                    try:
                        return AgentAnswer(answer=candidate)
                    except Exception:
                        pass
        raise first_error


def re_finditer_dotall(pattern: str, text: str):
    import re

    return re.finditer(pattern, text, flags=re.S)


def build_context_payload(task: TaskRow) -> dict[str, Any]:
    return {
        "source_text": task.context,
        "question": task.question,
        "source_benchmark": task.source_benchmark,
        "source_task": task.source_task,
        "scorer": task.scorer,
        "gold_visible": False,
    }


def default_max_depth(arm: Arm) -> int:
    return 2 if arm in {"rlm_repl_depth1", "rlm_repl_depth1_recursive"} else 1


def rlm_mode(arm: Arm) -> str:
    if arm == "rlm_repl_depth1_recursive":
        return "official_local_repl_depth1_recursive_child_rlm_required"
    if arm == "rlm_repl_depth1":
        return "official_local_repl_depth1_sub_lm_or_rlm_enabled"
    return "official_local_repl_depth0_no_sub_lm_calls"


def build_root_prompt(task: TaskRow, arm: Arm) -> str:
    common = (
        "Answer this long-context benchmark question using the RLM REPL.\n"
        "The full source text is NOT in this chat prompt; it is externalized in the REPL as context['source_text'] and as ./context.txt.\n"
        "When finished, call submit_answer(value) in a repl block. It will produce the required JSON object.\n"
        f"{benchmark_hint(task.source_benchmark, task.source_task)}\n"
        f"Benchmark: {task.source_benchmark} / {task.source_task}\n"
        f"Question:\n{task.question}\n"
    )
    if arm in {"rlm_repl_depth1", "rlm_repl_depth1_recursive"}:
        required = (
            "Depth-1 full-recursive rule: you MUST make at least one child RLM call through ask_rlm_one or ask_rlm_chunks before submit_answer.\n"
            if arm == "rlm_repl_depth1_recursive"
            else "Depth-1 recursive rule: you MUST make at least one focused subcall through ask_one, ask_chunks, ask_rlm_one, or ask_rlm_chunks before submit_answer.\n"
        )
        return (
            common
            + required
            + "Use llm_query/llm_query_batched for semantic extraction from chunks, and rlm_query/rlm_query_batched for harder chunk subtasks that need their own REPL.\n"
            + "Keep subcalls bounded and evidence-based. For OOLONG counting tasks, split by episode/chunk, ask subcalls to return small JSON counts/evidence, then aggregate in Python before submit_answer.\n"
            + "For BABILong, first use deterministic code over the source, then make one focused subcall over the best candidate snippet to verify the answer.\n"
        )
    return (
        common
        + "Depth-0 rule: do not call llm_query, llm_query_batched, rlm_query, or rlm_query_batched. Use Python over the external source instead.\n"
    )


def build_setup_code(arm: Arm) -> str:
    if arm == "rlm_repl_depth1_recursive":
        return build_depth1_recursive_setup_code()
    if arm == "rlm_repl_depth1":
        return build_depth1_setup_code()
    return build_depth0_setup_code()


def build_system_prompt(arm: Arm) -> str:
    if arm == "rlm_repl_depth1_recursive":
        return build_depth1_recursive_system_prompt()
    if arm == "rlm_repl_depth1":
        return build_depth1_system_prompt()
    return build_depth0_system_prompt()


def build_depth0_setup_code() -> str:
    return r'''
import json, re, math, statistics

def source_text():
    if isinstance(context, dict):
        return str(context.get("source_text", ""))
    return str(context)

def question_text():
    if isinstance(context, dict):
        return str(context.get("question", ""))
    return ""

# External prompt handle used by the depth-0 RLM arm.
with open("context.txt", "w", encoding="utf-8") as _context_file:
    _context_file.write(source_text())

def iter_chunks(text=None, chars=12000, overlap=600):
    text = source_text() if text is None else str(text)
    if chars <= 0:
        raise ValueError("chars must be positive")
    step = max(1, chars - max(0, overlap))
    for start in range(0, len(text), step):
        yield start, text[start:start + chars]

def grep(pattern, text=None, flags=re.IGNORECASE, window=220, limit=50):
    text = source_text() if text is None else str(text)
    out = []
    for m in re.finditer(pattern, text, flags):
        lo = max(0, m.start() - window)
        hi = min(len(text), m.end() + window)
        out.append({"start": m.start(), "end": m.end(), "match": m.group(0), "window": text[lo:hi]})
        if len(out) >= limit:
            break
    return out

def submit_answer(value):
    answer["content"] = json.dumps({"answer": str(value)})
    answer["ready"] = True
'''


def build_depth1_setup_code() -> str:
    return build_depth0_setup_code() + r'''

# Depth-1 helper utilities. These are deterministic wrappers around the
# official RLM-provided llm_query / llm_query_batched / rlm_query functions.
_depth1_subcalls = {"count": 0}
_depth1_recursive_subcalls = {"count": 0}

def chunk_source(chars=18000, overlap=1200, max_chunks=None):
    chunks = []
    for start, chunk in iter_chunks(chars=chars, overlap=overlap):
        chunks.append({"index": len(chunks), "start": start, "text": chunk})
        if max_chunks is not None and len(chunks) >= max_chunks:
            break
    return chunks


def episode_chunks():
    text = source_text()
    parts = re.split(r"(\[START OF EPISODE\])", text)
    if len(parts) <= 1:
        return chunk_source(chars=22000, overlap=1200)
    chunks = []
    current = ""
    for part in parts:
        if part == "[START OF EPISODE]":
            if current.strip():
                chunks.append({"index": len(chunks), "start": text.find(current[:80]) if current else -1, "text": current})
            current = part
        else:
            current += part
    if current.strip():
        chunks.append({"index": len(chunks), "start": text.find(current[:80]) if current else -1, "text": current})
    return chunks


def ask_chunks(instruction, chunks, *, batch_size=4, max_chars_per_chunk=22000):
    prompts = []
    for c in chunks:
        chunk_text = c["text"][:max_chars_per_chunk]
        prompts.append(
            instruction
            + "\n\nReturn a concise answer. If counting, return JSON with keys count and evidence."
            + f"\n\nChunk index: {c['index']} start: {c.get('start', -1)}\n<CHUNK>\n{chunk_text}\n</CHUNK>"
        )
    outputs = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i + batch_size]
        _depth1_subcalls["count"] += len(batch)
        outputs.extend(llm_query_batched(batch))
    return outputs


def ask_one(instruction, chunk_text):
    _depth1_subcalls["count"] += 1
    return llm_query(instruction + "\n\n<CHUNK>\n" + str(chunk_text) + "\n</CHUNK>")


def ask_rlm_one(instruction, chunk_text):
    _depth1_subcalls["count"] += 1
    _depth1_recursive_subcalls["count"] += 1
    return rlm_query(instruction + "\n\n<CHUNK>\n" + str(chunk_text) + "\n</CHUNK>")


def ask_rlm_chunks(instruction, chunks, *, batch_size=2, max_chars_per_chunk=18000):
    prompts = []
    for c in chunks:
        prompts.append(
            instruction
            + "\n\nReturn a concise answer. If counting, return JSON with keys count and evidence."
            + f"\n\nChunk index: {c['index']} start: {c.get('start', -1)}\n<CHUNK>\n{c['text'][:max_chars_per_chunk]}\n</CHUNK>"
        )
    outputs = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i + batch_size]
        _depth1_subcalls["count"] += len(batch)
        _depth1_recursive_subcalls["count"] += len(batch)
        outputs.extend(rlm_query_batched(batch))
    return outputs


def depth1_subcall_count():
    return _depth1_subcalls["count"]


def depth1_recursive_subcall_count():
    return _depth1_recursive_subcalls["count"]


def is_root_benchmark_task():
    return isinstance(context, dict) and "source_text" in context and "question" in context


def submit_answer(value):
    if is_root_benchmark_task() and _depth1_subcalls["count"] <= 0:
        print("Depth-1 requires at least one subcall through ask_one/ask_chunks/ask_rlm_one/ask_rlm_chunks before submit_answer. Make a focused subcall, then submit again.")
        answer["content"] = json.dumps({"answer": str(value)})
        answer["ready"] = False
        return
    answer["content"] = json.dumps({"answer": str(value)})
    answer["ready"] = True


def extract_json_objects(text):
    out = []
    for m in re.finditer(r"\{[^{}]*\}", str(text), flags=re.S):
        try:
            out.append(json.loads(m.group(0)))
        except Exception:
            pass
    return out


def helper_namespace():
    return {
        "context": context,
        "context_0": context,
        "source_text": source_text,
        "question_text": question_text,
        "iter_chunks": iter_chunks,
        "grep": grep,
        "chunk_source": chunk_source,
        "episode_chunks": episode_chunks,
        "ask_chunks": ask_chunks,
        "ask_one": ask_one,
        "ask_rlm_one": ask_rlm_one,
        "ask_rlm_chunks": ask_rlm_chunks,
        "depth1_subcall_count": depth1_subcall_count,
        "depth1_recursive_subcall_count": depth1_recursive_subcall_count,
        "is_root_benchmark_task": is_root_benchmark_task,
        "extract_json_objects": extract_json_objects,
        "submit_answer": submit_answer,
    }

# The upstream sandbox blocks Python's built-in globals()/locals(). Models often
# try to inspect helper availability that way, so provide a safe replacement
# containing only benchmark helpers and context handles.
def globals():
    return helper_namespace()

def locals():
    return helper_namespace()
'''


def build_depth1_recursive_setup_code() -> str:
    return build_depth1_setup_code() + r'''

# Stricter full-recursive arm: at least one child RLM call is required.
def submit_answer(value):
    if is_root_benchmark_task() and _depth1_recursive_subcalls["count"] <= 0:
        print("Full recursive depth-1 requires at least one child RLM subcall through ask_rlm_one or ask_rlm_chunks before submit_answer. Make a focused child-RLM subcall, then submit again.")
        answer["content"] = json.dumps({"answer": str(value)})
        answer["ready"] = False
        return
    answer["content"] = json.dumps({"answer": str(value)})
    answer["ready"] = True
'''


def build_depth0_system_prompt() -> str:
    # All literal braces are doubled because upstream build_rlm_system_prompt
    # calls .format(custom_tools_section=...).
    return """You are solving a long-context benchmark using the official Recursive Language Model scaffold.

The REPL is initialized with:
1. a `context` variable. For these tasks it is a dictionary with `source_text`, `question`, `source_benchmark`, and `source_task`.
2. a file `context.txt` in the REPL working directory containing the full source text.
3. helper functions: `source_text()`, `question_text()`, `iter_chunks(...)`, `grep(...)`, and `submit_answer(value)`.
4. an `answer` dict. The run ends when `answer["ready"] = True`.
{custom_tools_section}

Depth-0 restriction: do NOT call `llm_query`, `llm_query_batched`, `rlm_query`, or `rlm_query_batched`. This benchmark arm tests the non-recursive RLM loop: inspect external state, write Python, parse/search/count, then answer.

Use the REPL by emitting Python in fenced code blocks tagged `repl`. Prefer deterministic code: regexes, scans, counters, state tracking, and small printed summaries. The full source is not in your chat prompt; inspect `context`, `context.txt`, and the helper functions.

Final answer format: call `submit_answer(value)` from a `repl` block. That helper stores exactly one JSON object string like {{"answer": "..."}} in `answer["content"]` and sets `answer["ready"] = True`.

Example final step:
```repl
submit_answer("bathroom")
```

Think carefully, execute code immediately, and answer only from the external source text.
"""


def build_depth1_system_prompt() -> str:
    # All literal braces are doubled because upstream build_rlm_system_prompt
    # calls .format(custom_tools_section=...).
    return """You are solving a long-context benchmark using the official Recursive Language Model scaffold with one recursive/sub-LM layer enabled.

The REPL is initialized with:
1. a `context` variable. For root tasks it is a dictionary with `source_text`, `question`, `source_benchmark`, and `source_task`; for child RLM subtasks it may be a plain string prompt.
2. a file `context.txt` in the REPL working directory containing the full source text or child prompt.
3. helper functions: `source_text()`, `question_text()`, `iter_chunks(...)`, `grep(...)`, `chunk_source(...)`, `episode_chunks()`, `ask_chunks(...)`, `ask_one(...)`, `ask_rlm_one(...)`, `ask_rlm_chunks(...)`, `depth1_subcall_count()`, `extract_json_objects(...)`, and `submit_answer(value)`.
4. official RLM functions: `llm_query`, `llm_query_batched`, `rlm_query`, and `rlm_query_batched`.
5. an `answer` dict. The run ends when `answer["ready"] = True`.
{custom_tools_section}

Depth-1 policy: you MUST make at least one focused subcall via `ask_one`, `ask_chunks`, `ask_rlm_one`, or `ask_rlm_chunks` before `submit_answer`. Use `llm_query` or `llm_query_batched` for simple extraction/classification over chunks. Use `rlm_query` or `rlm_query_batched` for subtasks that need a child REPL or multi-step reasoning. Keep calls bounded; do not query every tiny sentence one by one.

Recommended strategy:
- Inspect the question and source format with Python first.
- For exact BABILong facts, deterministic code/search/state tracking is often enough, but still verify the best candidate with one small `ask_one` subcall before final.
- For OOLONG transcript counting, split by episode or by large chunks, ask sub-LMs for JSON counts plus short evidence, then aggregate and sanity-check in Python.
- If subcall answers disagree, inspect the relevant chunk directly before submitting.

Final answer format: call `submit_answer(value)` from a `repl` block. That helper stores exactly one JSON object string like {{"answer": "..."}} in `answer["content"]` and sets `answer["ready"] = True`.

Example depth-1 pattern:
```repl
chunks = episode_chunks()
outs = ask_chunks("Count Keyleth spell casts in this episode. Return JSON {{\"count\": integer, \"evidence\": [short quotes]}}.", chunks)
print(outs)
# parse/aggregate, then:
submit_answer(total)
```

Think carefully, execute code immediately, and answer only from the external source text and subcall evidence.
"""


def build_depth1_recursive_system_prompt() -> str:
    base = build_depth1_system_prompt()
    return base.replace(
        "Depth-1 policy: you MUST make at least one focused subcall via `ask_one`, `ask_chunks`, `ask_rlm_one`, or `ask_rlm_chunks` before `submit_answer`.",
        "Full recursive depth-1 policy: you MUST make at least one child RLM subcall via `ask_rlm_one` or `ask_rlm_chunks` before `submit_answer`. You may also use `ask_one`/`ask_chunks`, but those plain sub-LM calls alone are not enough for this stricter arm.",
    ).replace(
        "- For exact BABILong facts, deterministic code/search/state tracking is often enough, but still verify the best candidate with one small `ask_one` subcall before final.",
        "- For exact BABILong facts, deterministic code/search/state tracking is often enough, but still verify the best candidate with one small `ask_rlm_one` child-RLM subcall before final.",
    )


def scrub_trajectory(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    if metadata.get("run_metadata"):
        run_meta = dict(metadata["run_metadata"])
        # backend kwargs may contain timeouts/settings but no secrets in this runner.
        out["run_metadata"] = run_meta
    iterations = []
    for item in metadata.get("iterations", []) or []:
        clean_blocks = []
        for block in item.get("code_blocks", []) or []:
            result = block.get("result", {}) or {}
            clean_blocks.append(
                {
                    "code_preview": preview(str(block.get("code") or ""), 1400),
                    "stdout_preview": preview(str(result.get("stdout") or ""), 1400),
                    "stderr_preview": preview(str(result.get("stderr") or ""), 1000),
                    "execution_time": result.get("execution_time"),
                    "rlm_call_count": len(result.get("rlm_calls", []) or []),
                    "final_answer_preview": preview(str(result.get("final_answer") or ""), 400),
                }
            )
        iterations.append(
            {
                "iteration": item.get("iteration"),
                "response_preview": preview(str(item.get("response") or ""), 1800),
                "final_answer_preview": preview(str(item.get("final_answer") or ""), 400),
                "iteration_time": item.get("iteration_time"),
                "code_blocks": clean_blocks,
            }
        )
    out["iterations"] = iterations
    return out


def count_repl_sub_lm_calls(trajectory: dict[str, Any]) -> int:
    total = 0
    for item in trajectory.get("iterations", []) or []:
        for block in item.get("code_blocks", []) or []:
            total += int(block.get("rlm_call_count") or 0)
    return total


def build_session_id(job: Job, task: TaskRow, clients: list[CodexCliLM]) -> str:
    first_session = ""
    for client in clients:
        for call in client.call_logs:
            if call.get("session_id"):
                first_session = str(call["session_id"])
                break
        if first_session:
            break
    base = f"rlm-{job.index}-{safe_name(task.task_id)[:60]}"
    if first_session:
        base += f"-{first_session[:24]}"
    return base[:190]


def basic_result(
    job: Job, *, log_path: Path, expected: Path, returncode: int, skipped: bool, duration_s: float
) -> dict[str, Any]:
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
