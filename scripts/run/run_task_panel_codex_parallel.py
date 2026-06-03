#!/usr/bin/env python3
"""Run an arbitrary task JSONL panel through Codex in parallel.

Each task is materialized into a one-row JSONL file and executed via the public
`compactionbench.cli run codex` command, preserving the same benchmark path as
single-task runs while adding manifest/status/logging for larger panels.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.core.schema import TaskRow, load_task_rows, write_task_rows


@dataclass
class Job:
    job_id: str
    index: int
    task_id: str
    source_benchmark: str
    source_task: str
    task_path: str
    model: str
    condition: str
    chunk_tokens: int
    timeout_s: int
    auto_compact_limit: int | None
    reasoning_effort: str
    verbosity: str


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True, help="Input task JSONL panel.")
    p.add_argument("--root-dir", required=True, help="Batch root directory.")
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--condition", default="auto", choices=["auto", "off"])
    p.add_argument("--chunk-tokens", type=int, default=32_000)
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--auto-compact-limit", type=int, default=150_000)
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--verbosity", default="low")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--task-id", action="append", default=None, help="Optional task_id allowlist; repeatable.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-skip-existing", action="store_true", help="Re-run even if the expected output JSON already exists.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    task_panel = Path(args.tasks)
    root = Path(args.root_dir)
    runs_dir = root / "runs"
    task_files_dir = root / "task_files"
    logs_dir = root / "job_logs"
    root.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    task_files_dir.mkdir(parents=True, exist_ok=True)
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
        task_files_dir=task_files_dir,
        model=args.model,
        condition=args.condition,
        chunk_tokens=args.chunk_tokens,
        timeout_s=args.timeout_s,
        auto_compact_limit=args.auto_compact_limit if args.condition == "auto" else None,
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
        "completed": 0,
        "skipped_existing": 0,
        "failed_subprocess": 0,
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

    lock = threading.Lock()
    results: list[dict[str, Any]] = []
    skip_existing = not args.no_skip_existing

    def run_and_record(job: Job) -> dict[str, Any]:
        with lock:
            status["running"] = sorted(set(status["running"] + [job.job_id]))
            update_status(status_path, status)
        result = run_job(job, runs_dir=runs_dir, logs_dir=logs_dir, skip_existing=skip_existing)
        with lock:
            results.append(result)
            status["completed"] += 1
            if result.get("skipped_existing"):
                status["skipped_existing"] += 1
            if int(result.get("returncode") or 0) != 0:
                status["failed_subprocess"] += 1
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
    task_files_dir: Path,
    model: str,
    condition: str,
    chunk_tokens: int,
    timeout_s: int,
    auto_compact_limit: int | None,
    reasoning_effort: str,
    verbosity: str,
) -> list[Job]:
    jobs: list[Job] = []
    for index, row in enumerate(rows, start=1):
        task_path = task_files_dir / f"{index:03d}-{safe_name(row.task_id)}.jsonl"
        write_task_rows([row], task_path)
        jobs.append(
            Job(
                job_id=f"{index:03d}-{safe_name(row.task_id)}",
                index=index,
                task_id=row.task_id,
                source_benchmark=row.source_benchmark,
                source_task=row.source_task,
                task_path=str(task_path),
                model=model,
                condition=condition,
                chunk_tokens=chunk_tokens,
                timeout_s=timeout_s,
                auto_compact_limit=auto_compact_limit,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
            )
        )
    return jobs


def run_job(job: Job, *, runs_dir: Path, logs_dir: Path, skip_existing: bool) -> dict[str, Any]:
    expected = runs_dir / "codex" / job.model / job.condition / f"{job.task_id}.json"
    log_path = logs_dir / f"{job.job_id}.log"
    if skip_existing and expected.exists():
        return {
            "job_id": job.job_id,
            "task_id": job.task_id,
            "returncode": 0,
            "skipped_existing": True,
            "started_at": now_iso(),
            "completed_at": now_iso(),
            "duration_s": 0.0,
            "log_path": str(log_path),
            "expected_run_path": str(expected),
        }

    cmd = [
        sys.executable,
        "-m",
        "compactionbench.cli",
        "run",
        "codex",
        "--tasks",
        job.task_path,
        "--model",
        job.model,
        "--condition",
        job.condition,
        "--chunk-tokens",
        str(job.chunk_tokens),
        "--out",
        str(runs_dir),
        "--timeout-s",
        str(job.timeout_s),
        "--reasoning-effort",
        job.reasoning_effort,
        "--verbosity",
        job.verbosity,
    ]
    if job.auto_compact_limit is not None and job.condition == "auto":
        cmd += ["--auto-compact-limit", str(job.auto_compact_limit)]

    started = now_iso()
    t0 = time.monotonic()
    with log_path.open("w") as log:
        log.write(f"started_at={started}\n")
        log.write("cmd=" + json.dumps(cmd) + "\n\n")
        proc = subprocess.run(cmd, stdout=log, stderr=log, text=True)
    duration_s = time.monotonic() - t0
    return {
        "job_id": job.job_id,
        "task_id": job.task_id,
        "source_benchmark": job.source_benchmark,
        "source_task": job.source_task,
        "returncode": proc.returncode,
        "skipped_existing": False,
        "started_at": started,
        "completed_at": now_iso(),
        "duration_s": duration_s,
        "log_path": str(log_path),
        "expected_run_path": str(expected),
    }


def write_manifest(root: Path, rows: list[TaskRow], jobs: list[Job]) -> None:
    task_payload = []
    for row in rows:
        task_payload.append(
            {
                "task_id": row.task_id,
                "source_benchmark": row.source_benchmark,
                "source_task": row.source_task,
                "source_sample_id": row.source_sample_id,
                "scorer": row.scorer,
                "gold_answer": row.gold_answer,
                "metadata_json": json.dumps(row.metadata, sort_keys=True),
            }
        )
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
