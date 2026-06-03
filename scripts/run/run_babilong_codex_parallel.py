#!/usr/bin/env python3
"""Parallel batch runner for the reviewed Codex × BABILong auto sweep.

This runner is intentionally orchestration-only. Each job is still executed via
`python -m compactionbench.cli run codex ...` so the core benchmark path stays
single-source-of-truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from compactionbench.core.schema import load_task_rows


@dataclass
class Job:
    job_id: str
    model: str
    length: str
    task: str
    task_path: str
    chunk_tokens: int
    condition: str
    timeout_s: int
    auto_compact_limit: int | None
    reasoning_effort: str
    verbosity: str


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spec",
        default="specs/babilong_codex_auto_high_models.yaml",
        help="Path to reviewed YAML spec.",
    )
    parser.add_argument(
        "--root-dir",
        default=None,
        help="Output root directory. Defaults to a timestamped batch dir.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Override max_parallel_jobs from the spec.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only materialize manifests; do not execute jobs.",
    )
    return parser.parse_args()


def load_spec(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def build_jobs(spec: dict[str, Any]) -> tuple[list[Job], list[dict[str, Any]]]:
    bench = spec["benchmark"]
    runner = spec["runner"]
    task_dir = Path(bench["prepared_tasks_dir"])
    inventory: list[dict[str, Any]] = []
    jobs: list[Job] = []
    samples_per_split = int(bench.get("samples_per_split", 1))

    file_template = bench.get("prepared_file_template")
    sample_glob_template = bench.get("prepared_file_sample_glob")

    for length in bench["lengths"]:
        for task in bench["tasks"]:
            paths = _resolve_task_files(
                task_dir,
                task=task,
                length=length,
                samples_per_split=samples_per_split,
                file_template=file_template,
                sample_glob_template=sample_glob_template,
            )
            chunk_tokens = int(runner["chunk_tokens_by_length"][length])

            for path in paths:
                row = load_task_rows(path)[0]
                inventory.append(
                    {
                        "file": path.name,
                        "task_id": row.task_id,
                        "source_task": row.source_task,
                        "length": row.metadata.get("length_label"),
                        "question": row.question,
                        "gold_answer": row.gold_answer,
                        "scorer": row.scorer,
                    }
                )

                for model in runner["models"]:
                    for condition in runner["conditions"]:
                        jobs.append(
                            Job(
                                job_id=f"{model}__{length}__{path.stem}__{condition}",
                                model=model,
                                length=length,
                                task=task,
                                task_path=str(path),
                                chunk_tokens=chunk_tokens,
                                condition=condition,
                                timeout_s=int(runner["timeout_s"]),
                                auto_compact_limit=runner["codex"].get("auto_compact_limit"),
                                reasoning_effort=str(runner["codex"]["reasoning_effort"]),
                                verbosity=str(runner["codex"]["verbosity"]),
                            )
                        )

    return jobs, inventory


def _resolve_task_files(
    task_dir: Path,
    *,
    task: str,
    length: str,
    samples_per_split: int,
    file_template: str | None = None,
    sample_glob_template: str | None = None,
) -> list[Path]:
    exact_name = (file_template or "babilong_{task}_{length}.jsonl").format(task=task, length=length)
    sample_glob = (sample_glob_template or "babilong_{task}_{length}_*.jsonl").format(task=task, length=length)
    exact = task_dir / exact_name
    sampled = sorted(task_dir.glob(sample_glob))

    if sampled:
        if len(sampled) < samples_per_split:
            raise FileNotFoundError(
                f"Need {samples_per_split} prepared task files for {task} {length}, found {len(sampled)} under {task_dir}"
            )
        return sampled[:samples_per_split]

    if exact.exists():
        if samples_per_split != 1:
            raise FileNotFoundError(
                f"Only one prepared task file exists for {task} {length}, but samples_per_split={samples_per_split}"
            )
        return [exact]

    raise FileNotFoundError(f"Missing prepared task file(s) for {task} {length} under {task_dir}")


def write_inventory(root: Path, inventory: list[dict[str, Any]], jobs: list[Job]) -> None:
    (root / "task_inventory.json").write_text(json.dumps(inventory, indent=2))
    with (root / "task_inventory.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["file", "task_id", "source_task", "length", "question", "gold_answer", "scorer"],
        )
        writer.writeheader()
        writer.writerows(inventory)

    jobs_payload = [asdict(job) for job in jobs]
    (root / "job_manifest.json").write_text(json.dumps(jobs_payload, indent=2))
    with (root / "job_manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(jobs_payload[0].keys()))
        writer.writeheader()
        writer.writerows(jobs_payload)


def update_status(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2))


def run_job(job: Job, *, runs_dir: Path, logs_dir: Path) -> dict[str, Any]:
    log_path = logs_dir / f"{job.job_id}.log"
    started_at = now_iso()
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

    t0 = time.monotonic()
    with log_path.open("w") as log:
        log.write(f"started_at={started_at}\n")
        log.write("cmd=" + json.dumps(cmd) + "\n\n")
        proc = subprocess.run(cmd, stdout=log, stderr=log, text=True)
    duration_s = time.monotonic() - t0
    return {
        "job_id": job.job_id,
        "model": job.model,
        "length": job.length,
        "task": job.task,
        "condition": job.condition,
        "returncode": proc.returncode,
        "started_at": started_at,
        "completed_at": now_iso(),
        "duration_s": duration_s,
        "log_path": str(log_path),
    }


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    root = Path(args.root_dir) if args.root_dir else Path(spec["outputs"]["root_dir"]) / datetime.now().strftime("%Y%m%d-%H%M%S")
    runs_dir = root / "runs"
    results_dir = root / "results"
    logs_dir = root / "job_logs"
    root.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(spec_path, root / "spec.yaml")

    jobs, inventory = build_jobs(spec)
    write_inventory(root, inventory, jobs)

    status_path = root / "status.json"
    status = {
        "started_at": now_iso(),
        "root_dir": str(root),
        "spec": str(spec_path),
        "total_jobs": len(jobs),
        "completed_jobs": 0,
        "failed_jobs": 0,
        "running_jobs": 0,
        "max_parallel_jobs": args.max_workers or int(spec["runner"].get("max_parallel_jobs", 1)),
        "dry_run": bool(args.dry_run),
    }
    update_status(status_path, status)

    if args.dry_run:
        return 0

    max_workers = status["max_parallel_jobs"]
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def wrapped(job: Job) -> dict[str, Any]:
        with lock:
            status["running_jobs"] += 1
            update_status(status_path, status)
        try:
            return run_job(job, runs_dir=runs_dir, logs_dir=logs_dir)
        finally:
            with lock:
                status["running_jobs"] -= 1
                update_status(status_path, status)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(wrapped, job): job for job in jobs}
        for future in as_completed(future_map):
            job = future_map[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "job_id": job.job_id,
                    "model": job.model,
                    "length": job.length,
                    "task": job.task,
                    "condition": job.condition,
                    "returncode": -1,
                    "started_at": None,
                    "completed_at": now_iso(),
                    "duration_s": None,
                    "log_path": str(logs_dir / f"{job.job_id}.log"),
                    "exception": f"{type(e).__name__}: {e}",
                }
            results.append(result)
            with lock:
                status["completed_jobs"] += 1
                if result.get("returncode") != 0:
                    status["failed_jobs"] += 1
                update_status(status_path, status)
            (root / "job_results.json").write_text(json.dumps(results, indent=2))

    with (root / "job_results.csv").open("w", newline="") as f:
        fieldnames = sorted({key for row in results for key in row.keys()})
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    score_cmd = [
        sys.executable,
        "-m",
        "compactionbench.cli",
        "score",
        "--runs",
        str(runs_dir),
        "--out",
        str(results_dir),
    ]
    subprocess.run(score_cmd, check=False)

    report_cmd = [
        sys.executable,
        "-m",
        "compactionbench.cli",
        "report",
        "--results",
        str(results_dir),
    ]
    report_proc = subprocess.run(report_cmd, check=False, capture_output=True, text=True)
    (root / "report.txt").write_text(report_proc.stdout + ("\nSTDERR:\n" + report_proc.stderr if report_proc.stderr else ""))

    status["completed_at"] = now_iso()
    update_status(status_path, status)
    return 1 if status["failed_jobs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
