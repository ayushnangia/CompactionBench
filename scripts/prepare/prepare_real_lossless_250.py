#!/usr/bin/env python3
"""Prepare 250 real-dataset tasks for the full-context-vs-grep test.

No local synthetic generator tasks are included. The panel is designed for a
paired 2-arm run: 250 tasks x {lossless_full_context, grep_file} = 500 runs.

Composition:
- BABILong 128k: qa1-qa10 x 10 samples = 100 tasks
- OOLONG-real: 6 real D&D transcript buckets x 25 samples = 150 tasks
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.core.chunking import estimate_tokens
from compactionbench.datasets.loaders import (
    BABILONG_TASK_INFO,
    OOLONG_REAL_CONFIG,
    OOLONG_REAL_DATASET,
    _episode_count,
    _prepare_oolong_real_records,
    _read_hf_rows_page_resilient,
    prepare_babilong_tasks_from_hf,
)
from compactionbench.core.schema import TaskRow, write_task_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/benchmarks/confirmation/real_lossless_250.jsonl")
    p.add_argument("--report-dir", default="artifacts/analysis/real_lossless_250")
    p.add_argument("--babilong-count-per-task", type=int, default=10)
    p.add_argument("--oolong-count-per-bucket", type=int, default=25)
    p.add_argument("--max-context-tokens", type=int, default=180_000, help="Fail if any prepared context exceeds this estimate.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: list[TaskRow] = []
    rows.extend(build_babilong(args.babilong_count_per_task))
    rows.extend(build_oolong_real(args.oolong_count_per_bucket))

    if len(rows) != 250:
        raise RuntimeError(f"Expected 250 rows, got {len(rows)}")

    too_long = [(row.task_id, estimate_tokens(row.context)) for row in rows if estimate_tokens(row.context) > args.max_context_tokens]
    if too_long:
        preview = too_long[:10]
        raise RuntimeError(f"Some contexts exceed max-context-tokens={args.max_context_tokens}: {preview}")

    write_task_rows(rows, out)
    manifest = [row_to_manifest(row, out) for row in rows]
    write_manifest(report_dir / "manifest.csv", manifest)
    write_report(report_dir / "report.md", rows, manifest, out)

    print(f"Wrote {len(rows)} real-dataset rows to {out}")
    print(f"Wrote report to {report_dir / 'report.md'}")
    return 0


def build_babilong(count_per_task: int) -> list[TaskRow]:
    rows: list[TaskRow] = []
    for i in range(1, 11):
        task = f"qa{i}"
        task_rows = prepare_babilong_tasks_from_hf(config="128k", split=task, count=count_per_task)
        if len(task_rows) != count_per_task:
            raise RuntimeError(f"Expected {count_per_task} BABILong rows for {task}, got {len(task_rows)}")
        for row in task_rows:
            metadata = dict(row.metadata)
            metadata.update(
                {
                    "panel": "real_lossless_250",
                    "panel_family": "babilong_128k",
                    "question_type_label": BABILONG_TASK_INFO.get(task, {}).get("name", task),
                }
            )
            rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def build_oolong_real(count_per_bucket: int) -> list[TaskRow]:
    desired: dict[tuple[str, int], int] = {
        ("singledoc_rolls", 1): count_per_bucket,
        ("singledoc_spells", 1): count_per_bucket,
        ("multidoc_rolls", 2): count_per_bucket,
        ("multidoc_spells", 2): count_per_bucket,
        ("multidoc_rolls", 3): count_per_bucket,
        ("multidoc_spells", 3): count_per_bucket,
    }
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = {key: [] for key in desired}

    offset = 0
    total: int | None = None
    page_size = 100
    while total is None or offset < total:
        page_rows, total = _read_hf_rows_page_resilient(
            dataset_name=OOLONG_REAL_DATASET,
            config=OOLONG_REAL_CONFIG,
            split="test",
            offset=offset,
            length=page_size,
        )
        if not page_rows:
            break
        for row in page_rows:
            key = (str(row.get("question_type") or "unknown"), _episode_count(row.get("episodes")))
            if key not in buckets:
                continue
            if len(buckets[key]) >= desired[key]:
                continue
            copied = dict(row)
            copied["length_label"] = f"{key[1]}ep"
            copied["estimated_context_tokens"] = estimate_tokens(str(row.get("context_window_text") or ""))
            buckets[key].append(copied)
        if all(len(buckets[key]) >= desired[key] for key in desired):
            break
        offset += len(page_rows)
        time.sleep(0.1)

    missing = {key: len(buckets[key]) for key in desired if len(buckets[key]) < desired[key]}
    if missing:
        raise RuntimeError(f"Could not fill OOLONG-real buckets: {missing}")

    rows: list[TaskRow] = []
    for key in sorted(buckets):
        qtype, ep_count = key
        task_rows = _prepare_oolong_real_records(
            buckets[key],
            count=desired[key],
            split="test",
            config=OOLONG_REAL_CONFIG,
            scorer_override=None,
            dataset_name=OOLONG_REAL_DATASET,
        )
        for row in task_rows:
            metadata = dict(row.metadata)
            metadata.update(
                {
                    "panel": "real_lossless_250",
                    "panel_family": "oolong_real",
                    "episode_count": ep_count,
                }
            )
            rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def row_to_manifest(row: TaskRow, panel_path: Path) -> dict[str, str]:
    return {
        "panel_path": str(panel_path),
        "task_id": row.task_id,
        "benchmark": row.source_benchmark,
        "panel_family": str(row.metadata.get("panel_family", "")),
        "source_task": row.source_task,
        "question_type": str(row.metadata.get("question_type") or row.metadata.get("question_type_label") or row.source_task),
        "length_or_size": str(row.metadata.get("length_label") or ""),
        "scorer": row.scorer,
        "context_tokens_est": str(estimate_tokens(row.context)),
        "gold_answer": row.gold_answer,
        "question_preview": compact(row.question, 180),
    }


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[TaskRow], manifest: list[dict[str, str]], panel_path: Path) -> None:
    by_benchmark = Counter(row.source_benchmark for row in rows)
    by_family = Counter(str(row.metadata.get("panel_family")) for row in rows)
    by_task = Counter(row.source_task for row in rows)
    token_est = [estimate_tokens(row.context) for row in rows]
    lines = ["# Real lossless 250 task panel", ""]
    lines.append(f"Task file: `{panel_path}`")
    lines.append("")
    lines.append("This panel excludes the local synthetic task generator. It is for the paired full-context-vs-grep test: 250 real benchmark tasks x 2 arms = 500 Codex runs.")
    lines.append("")
    lines.append("## Composition")
    lines.append("")
    lines.append(f"- total rows: `{len(rows)}`")
    lines.append(f"- by benchmark: `{dict(by_benchmark)}`")
    lines.append(f"- by family: `{dict(by_family)}`")
    lines.append(f"- by source task: `{dict(sorted(by_task.items()))}`")
    lines.append(f"- context token estimate: min `{min(token_est)}`, max `{max(token_est)}`, avg `{sum(token_est)/len(token_est):.0f}`")
    lines.append("")
    lines.append("## Arms to run")
    lines.append("")
    lines.append("- `full_context`: one prompt containing the original context and the question; no tools requested.")
    lines.append("- `grep_file`: original context written to `full_context.txt`; Codex is asked to use shell search and answer from the file.")
    lines.append("")
    lines.append("## Manifest preview")
    lines.append("")
    lines.append("| Benchmark | Family | Source task | Question type | Length | Tokens est | Task id |")
    lines.append("|---|---|---|---|---|---:|---|")
    for row in manifest[:80]:
        lines.append(
            f"| `{row['benchmark']}` | `{row['panel_family']}` | `{row['source_task']}` | "
            f"`{row['question_type']}` | `{row['length_or_size']}` | {row['context_tokens_est']} | `{row['task_id']}` |"
        )
    if len(manifest) > 80:
        lines.append(f"| ... | ... | ... | ... | ... | ... | `{len(manifest) - 80}` more rows in manifest.csv |")
    path.write_text("\n".join(lines) + "\n")


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
