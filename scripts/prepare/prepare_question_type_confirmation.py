#!/usr/bin/env python3
"""Prepare small question-type confirmation panels.

Outputs are intended as reproducible canaries before spending a larger Codex
budget. The main panel is exactly 20 BABILong rows: one row for each qa1-qa20
question type. Companion panels cover all locally available LongMemEval question
types plus OOLONG and synthetic task groups.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.datasets.lme_loader import load_lme_questions, prepare_lme_tasks
from compactionbench.datasets.loaders import BABILONG_TASK_INFO
from compactionbench.core.schema import TaskRow, load_task_rows, write_task_rows

BABILONG_QA1_TO_10_DIR = Path("data/benchmarks/babilong_codex_128k_to_1m")
BABILONG_QA11_TO_20_DIR = Path("data/benchmarks/babilong_codex_qa11_to_20_128k_to_1m_s3")
OOLONG_SYNTH_DIR = Path("data/benchmarks/oolong_synth_codex_128k_to_1m_s3")
OOLONG_REAL_DIR = Path("data/benchmarks/oolong_real_codex_3ep_to_16ep_s3")
SYNTHETIC_PATH = Path("data/benchmarks/synthetic_tasks_v1.jsonl")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/benchmarks/confirmation", help="Directory for prepared confirmation panels.")
    p.add_argument("--report-dir", default="artifacts/analysis/question_type_confirmation", help="Directory for CSV/Markdown coverage reports.")
    p.add_argument("--babilong-length", default="256k", choices=["128k", "256k", "512k", "1M"], help="BABILong length for the 20-type panel.")
    p.add_argument("--oolong-synth-length", default="256k", choices=["128k", "256k", "512k", "1M"], help="OOLONG-synth length for the companion panel.")
    p.add_argument("--oolong-real-length", default="6ep", choices=["3ep", "6ep", "10ep", "16ep"], help="OOLONG-real episode bucket for the companion panel.")
    p.add_argument("--lme-snapshot", default="auto", help="LongMemEval-V2 HF snapshot directory, or 'auto' to use the newest local cache.")
    p.add_argument("--lme-haystack-name", default="lme_v2_medium.json", help="Haystack filename under the LME snapshot haystacks/ directory.")
    p.add_argument("--lme-target-tokens", type=int, default=160_000, help="Minimum approximate context tokens for generated LME rows.")
    p.add_argument("--lme-max-trajectories", type=int, default=120, help="Maximum trajectories rendered per generated LME task.")
    p.add_argument("--cross-max", type=int, default=20, help="Maximum rows in the balanced cross-benchmark panel.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    report_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    panels: dict[str, list[TaskRow]] = {}
    notes: list[str] = []

    babilong_rows = build_babilong_20(args.babilong_length)
    panels[f"babilong_20_question_types_{args.babilong_length}"] = babilong_rows

    lme_rows = build_lme_all_types(
        snapshot_arg=args.lme_snapshot,
        haystack_name=args.lme_haystack_name,
        target_tokens=args.lme_target_tokens,
        max_trajectories=args.lme_max_trajectories,
        notes=notes,
    )
    if lme_rows:
        panels["lme_all_question_types"] = lme_rows

    oolong_rows = build_oolong_companion(args.oolong_synth_length, args.oolong_real_length, notes=notes)
    if oolong_rows:
        panels[f"oolong_question_types_synth-{args.oolong_synth_length}_real-{args.oolong_real_length}"] = oolong_rows

    synthetic_rows = build_synthetic_companion(notes=notes)
    if synthetic_rows:
        panels["synthetic_question_types"] = synthetic_rows

    cross_rows = build_cross_panel(
        babilong_rows=babilong_rows,
        lme_rows=lme_rows,
        oolong_rows=oolong_rows,
        synthetic_rows=synthetic_rows,
        max_rows=args.cross_max,
    )
    if cross_rows:
        panels[f"cross_benchmark_{len(cross_rows)}_question_types"] = cross_rows

    manifest_rows: list[dict[str, str]] = []
    for panel_name, rows in panels.items():
        out_path = out_dir / f"{panel_name}.jsonl"
        write_task_rows(rows, out_path)
        manifest_rows.extend(row_to_manifest(panel_name, out_path, row) for row in rows)

    write_manifest(report_dir / "manifest.csv", manifest_rows)
    write_report(report_dir / "report.md", panels, manifest_rows, notes)

    print(f"Wrote {len(panels)} confirmation panels under {out_dir}")
    print(f"Wrote coverage report under {report_dir}")
    for panel_name, rows in panels.items():
        print(f"- {panel_name}: {len(rows)} rows")
    if notes:
        print("Notes:")
        for note in notes:
            print(f"- {note}")
    return 0


def build_babilong_20(length: str) -> list[TaskRow]:
    rows: list[TaskRow] = []
    for i in range(1, 21):
        task = f"qa{i}"
        if i <= 10:
            path = BABILONG_QA1_TO_10_DIR / f"babilong_{task}_{length}.jsonl"
        else:
            path = BABILONG_QA11_TO_20_DIR / f"babilong_{task}_{length}_000.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"Missing BABILong confirmation source file: {path}")
        row = load_task_rows(path)[0]
        metadata = dict(row.metadata)
        metadata["confirmation_panel"] = "babilong_20_question_types"
        metadata["question_type_label"] = BABILONG_TASK_INFO.get(task, {}).get("name", task)
        rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def build_lme_all_types(
    *,
    snapshot_arg: str,
    haystack_name: str,
    target_tokens: int,
    max_trajectories: int,
    notes: list[str],
) -> list[TaskRow]:
    snapshot = resolve_lme_snapshot(snapshot_arg)
    if snapshot is None:
        notes.append("LongMemEval-V2 local HF cache not found; skipped LME companion panel.")
        return []

    haystack_path = snapshot / "haystacks" / haystack_name
    if not haystack_path.exists() and haystack_name == "lme_v2_medium.json":
        fallback = snapshot / "haystacks" / "lme_v2_small.json"
        if fallback.exists():
            haystack_path = fallback
    trajectories_path = snapshot / "trajectories.jsonl"
    questions_path = snapshot / "questions.jsonl"
    missing = [p for p in (haystack_path, trajectories_path, questions_path) if not p.exists()]
    if missing:
        notes.append("LongMemEval-V2 cache is incomplete; skipped LME companion panel. Missing: " + ", ".join(str(p) for p in missing))
        return []

    qtypes = sorted({str(q.get("question_type") or "unknown") for q in load_lme_questions(questions_path)})
    rows = prepare_lme_tasks(
        haystack_path,
        trajectories_path,
        questions_path,
        count=len(qtypes),
        target_tokens=target_tokens,
        question_types=set(qtypes),
        count_per_type=1,
        max_trajectories=max_trajectories,
    )
    seen = {str(row.metadata.get("question_type")) for row in rows}
    missing_types = sorted(set(qtypes) - seen)
    if missing_types:
        notes.append("LME panel missed question types: " + ", ".join(missing_types))
    return rows


def build_oolong_companion(synth_length: str, real_length: str, *, notes: list[str]) -> list[TaskRow]:
    rows: list[TaskRow] = []
    if OOLONG_SYNTH_DIR.exists():
        rows.extend(one_per_source_task(OOLONG_SYNTH_DIR.glob(f"oolong_synth_*_{synth_length}_000.jsonl")))
    else:
        notes.append(f"Missing OOLONG-synth directory: {OOLONG_SYNTH_DIR}")

    if OOLONG_REAL_DIR.exists():
        rows.extend(one_per_source_task(OOLONG_REAL_DIR.glob(f"oolong_real_*_{real_length}_000.jsonl")))
    else:
        notes.append(f"Missing OOLONG-real directory: {OOLONG_REAL_DIR}")

    return rows


def build_synthetic_companion(*, notes: list[str]) -> list[TaskRow]:
    if not SYNTHETIC_PATH.exists():
        notes.append(f"Missing synthetic task file: {SYNTHETIC_PATH}")
        return []
    rows = one_per_source_task([SYNTHETIC_PATH])
    return [row.model_copy(update={"source_benchmark": "synthetic"}) for row in rows]


def build_cross_panel(
    *,
    babilong_rows: list[TaskRow],
    lme_rows: list[TaskRow],
    oolong_rows: list[TaskRow],
    synthetic_rows: list[TaskRow],
    max_rows: int,
) -> list[TaskRow]:
    rows: list[TaskRow] = []

    # Put non-BABILong benchmarks first so LME/OOLONG/Synthetic are represented
    # even when max_rows is only 20. Fill remaining slots with diverse BABILong
    # reasoning families.
    for group in (lme_rows, oolong_rows, synthetic_rows):
        for row in group:
            if len(rows) < max_rows:
                rows.append(row)

    preferred_babilong = ["qa1", "qa2", "qa3", "qa6", "qa7", "qa8", "qa11", "qa14", "qa15", "qa16", "qa17", "qa18", "qa19", "qa20"]
    by_task = {row.source_task: row for row in babilong_rows}
    for task in preferred_babilong:
        if len(rows) >= max_rows:
            break
        row = by_task.get(task)
        if row is not None:
            rows.append(row)
    for row in babilong_rows:
        if len(rows) >= max_rows:
            break
        if row not in rows:
            rows.append(row)
    return rows[:max_rows]


def one_per_source_task(paths: Iterable[Path]) -> list[TaskRow]:
    by_task: dict[str, TaskRow] = {}
    for path in sorted(paths):
        if not path.exists():
            continue
        for row in load_task_rows(path):
            by_task.setdefault(row.source_task, row)
    return [by_task[key] for key in sorted(by_task)]


def resolve_lme_snapshot(raw: str) -> Path | None:
    if raw != "auto":
        return Path(raw)
    root = Path.home() / ".cache/huggingface/hub/datasets--xiaowu0162--longmemeval-v2/snapshots"
    if not root.exists():
        root = Path.home() / ".cache/huggingface/hub/datasets--xiaowu0162--LongMemEval-V2/snapshots"
    if not root.exists():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def row_to_manifest(panel_name: str, panel_path: Path, row: TaskRow) -> dict[str, str]:
    length = str(row.metadata.get("length_label") or row.metadata.get("target_tokens") or row.metadata.get("context_len") or "")
    question_type = str(row.metadata.get("question_type") or row.metadata.get("question_type_label") or row.source_task)
    return {
        "panel": panel_name,
        "panel_path": str(panel_path),
        "task_id": row.task_id,
        "benchmark": row.source_benchmark,
        "source_task": row.source_task,
        "question_type": question_type,
        "length_or_size": length,
        "scorer": row.scorer,
        "gold_answer": row.gold_answer,
        "question_preview": compact(row.question, 180),
    }


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "panel",
        "panel_path",
        "task_id",
        "benchmark",
        "source_task",
        "question_type",
        "length_or_size",
        "scorer",
        "gold_answer",
        "question_preview",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, panels: dict[str, list[TaskRow]], manifest_rows: list[dict[str, str]], notes: list[str]) -> None:
    lines = ["# Question-type confirmation panels", ""]
    lines.append("Prepared local canary panels for question-type coverage before larger Codex runs.")
    lines.append("")
    lines.append("## Panels")
    lines.append("")
    for name, rows in panels.items():
        by_benchmark = Counter(row.source_benchmark for row in rows)
        type_count = len({row.metadata.get("question_type") or row.metadata.get("question_type_label") or row.source_task for row in rows})
        lines.append(f"- `{name}`: `{len(rows)}` rows, `{type_count}` question/task-type labels, benchmarks `{dict(by_benchmark)}`")
    lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Run commands")
    lines.append("")
    lines.append("Example BABILong 20-type confirmation run (sequential, one model):")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run cbench run codex --tasks data/benchmarks/confirmation/babilong_20_question_types_256k.jsonl \\")
    lines.append("  --model gpt-5.4-mini --condition auto --chunk-tokens 32000 \\")
    lines.append("  --auto-compact-limit 150000 --reasoning-effort high --verbosity low \\")
    lines.append("  --timeout-s 240 --out artifacts/runs_confirmation/babilong_20_256k")
    lines.append("uv run cbench score --runs artifacts/runs_confirmation/babilong_20_256k \\")
    lines.append("  --out artifacts/results_confirmation/babilong_20_256k")
    lines.append("```")
    lines.append("")
    lines.append("Example balanced cross-benchmark confirmation run:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run cbench run codex --tasks data/benchmarks/confirmation/cross_benchmark_20_question_types.jsonl \\")
    lines.append("  --model gpt-5.4-mini --condition auto --chunk-tokens 32000 \\")
    lines.append("  --auto-compact-limit 150000 --reasoning-effort high --verbosity low \\")
    lines.append("  --timeout-s 240 --out artifacts/runs_confirmation/cross_benchmark_20")
    lines.append("```")
    lines.append("")

    lines.append("## Manifest preview")
    lines.append("")
    lines.append("| Panel | Benchmark | Source task | Question type | Length/size | Scorer | Task id |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in manifest_rows[:80]:
        lines.append(
            f"| `{row['panel']}` | `{row['benchmark']}` | `{row['source_task']}` | "
            f"`{row['question_type']}` | `{row['length_or_size']}` | `{row['scorer']}` | `{row['task_id']}` |"
        )
    if len(manifest_rows) > 80:
        lines.append(f"| ... | ... | ... | ... | ... | ... | `{len(manifest_rows) - 80}` more rows in manifest.csv |")
    lines.append("")
    lines.append(f"Full manifest: `{path.parent / 'manifest.csv'}`")
    path.write_text("\n".join(lines))


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
