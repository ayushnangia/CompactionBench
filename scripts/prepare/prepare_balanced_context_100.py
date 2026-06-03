#!/usr/bin/env python3
"""Prepare a balanced ~100-task mixed-context confirmation panel.

Panel composition is intentionally explicit and reproducible:
- BABILong: 20 qa types at 128k and 512k (40 rows)
- OOLONG-synth: 3 groups x 4 context lengths x 2 samples (24 rows)
- OOLONG-real: 2 question types x 4 episode buckets x 2 samples (16 rows)
- LongMemEval-V2: 7 question types x 2 samples (14 rows)
- Synthetic: 3 controlled task types x 2 samples (6 rows)
Total: 100 rows.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

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
    p.add_argument("--out", default="data/benchmarks/confirmation/balanced_context_100.jsonl")
    p.add_argument("--report-dir", default="artifacts/analysis/balanced_context_100")
    p.add_argument("--lme-snapshot", default="auto")
    p.add_argument("--lme-haystack-name", default="lme_v2_medium.json")
    p.add_argument("--lme-target-tokens", type=int, default=160_000)
    p.add_argument("--lme-max-trajectories", type=int, default=120)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: list[TaskRow] = []
    rows.extend(build_babilong())
    rows.extend(build_oolong_synth())
    rows.extend(build_oolong_real())
    rows.extend(
        build_lme(
            snapshot_arg=args.lme_snapshot,
            haystack_name=args.lme_haystack_name,
            target_tokens=args.lme_target_tokens,
            max_trajectories=args.lme_max_trajectories,
        )
    )
    rows.extend(build_synthetic())

    if len(rows) != 100:
        raise RuntimeError(f"Expected exactly 100 rows, got {len(rows)}")

    write_task_rows(rows, out)
    manifest = [row_to_manifest(row, out) for row in rows]
    write_manifest(report_dir / "manifest.csv", manifest)
    write_report(report_dir / "report.md", rows, manifest, out)

    print(f"Wrote {len(rows)} rows to {out}")
    print(f"Wrote report to {report_dir / 'report.md'}")
    return 0


def build_babilong() -> list[TaskRow]:
    rows: list[TaskRow] = []
    for length in ("128k", "512k"):
        for i in range(1, 21):
            task = f"qa{i}"
            if i <= 10:
                path = BABILONG_QA1_TO_10_DIR / f"babilong_{task}_{length}.jsonl"
            else:
                path = BABILONG_QA11_TO_20_DIR / f"babilong_{task}_{length}_000.jsonl"
            row = load_task_rows(path)[0]
            metadata = dict(row.metadata)
            metadata.update(
                {
                    "balanced_panel": "balanced_context_100",
                    "panel_family": "babilong",
                    "question_type_label": BABILONG_TASK_INFO.get(task, {}).get("name", task),
                }
            )
            rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def build_oolong_synth() -> list[TaskRow]:
    rows: list[TaskRow] = []
    for length in ("128k", "256k", "512k", "1M"):
        for group in ("counting", "timeline", "user"):
            for sample_idx in (0, 1):
                path = OOLONG_SYNTH_DIR / f"oolong_synth_{group}_{length}_{sample_idx:03d}.jsonl"
                row = load_task_rows(path)[0]
                metadata = dict(row.metadata)
                metadata.update({"balanced_panel": "balanced_context_100", "panel_family": "oolong_synth"})
                rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def build_oolong_real() -> list[TaskRow]:
    rows: list[TaskRow] = []
    for length in ("3ep", "6ep", "10ep", "16ep"):
        for qtype in ("multidoc_rolls", "multidoc_spells"):
            for sample_idx in (0, 1):
                path = OOLONG_REAL_DIR / f"oolong_real_{qtype}_{length}_{sample_idx:03d}.jsonl"
                row = load_task_rows(path)[0]
                metadata = dict(row.metadata)
                metadata.update({"balanced_panel": "balanced_context_100", "panel_family": "oolong_real"})
                rows.append(row.model_copy(update={"metadata": metadata}))
    return rows


def build_lme(*, snapshot_arg: str, haystack_name: str, target_tokens: int, max_trajectories: int) -> list[TaskRow]:
    snapshot = resolve_lme_snapshot(snapshot_arg)
    if snapshot is None:
        raise RuntimeError("LongMemEval-V2 local HF cache not found")
    haystack_path = snapshot / "haystacks" / haystack_name
    if not haystack_path.exists() and haystack_name == "lme_v2_medium.json":
        fallback = snapshot / "haystacks" / "lme_v2_small.json"
        if fallback.exists():
            haystack_path = fallback
    trajectories_path = snapshot / "trajectories.jsonl"
    questions_path = snapshot / "questions.jsonl"
    for path in (haystack_path, trajectories_path, questions_path):
        if not path.exists():
            raise FileNotFoundError(path)

    qtypes = sorted({str(q.get("question_type") or "unknown") for q in load_lme_questions(questions_path)})
    rows = prepare_lme_tasks(
        haystack_path,
        trajectories_path,
        questions_path,
        count=len(qtypes) * 2,
        target_tokens=target_tokens,
        question_types=set(qtypes),
        count_per_type=2,
        max_trajectories=max_trajectories,
    )
    counts = Counter(str(row.metadata.get("question_type")) for row in rows)
    missing = {qtype: counts[qtype] for qtype in qtypes if counts[qtype] != 2}
    if missing:
        raise RuntimeError(f"Could not prepare two LME rows per type: {missing}")
    return [
        row.model_copy(
            update={
                "metadata": {
                    **row.metadata,
                    "balanced_panel": "balanced_context_100",
                    "panel_family": "lme",
                }
            }
        )
        for row in rows
    ]


def build_synthetic() -> list[TaskRow]:
    source_rows = load_task_rows(SYNTHETIC_PATH)
    by_task: defaultdict[str, list[TaskRow]] = defaultdict(list)
    for row in source_rows:
        by_task[row.source_task].append(row)
    rows: list[TaskRow] = []
    for task in sorted(by_task):
        selected = by_task[task][:2]
        if len(selected) != 2:
            raise RuntimeError(f"Need two synthetic rows for {task}, found {len(selected)}")
        for row in selected:
            metadata = dict(row.metadata)
            metadata.update({"balanced_panel": "balanced_context_100", "panel_family": "synthetic"})
            rows.append(row.model_copy(update={"source_benchmark": "synthetic", "metadata": metadata}))
    return rows


def resolve_lme_snapshot(raw: str) -> Path | None:
    if raw != "auto":
        return Path(raw)
    root = Path.home() / ".cache/huggingface/hub/datasets--xiaowu0162--longmemeval-v2/snapshots"
    if not root.exists():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def row_to_manifest(row: TaskRow, panel_path: Path) -> dict[str, str]:
    length = str(row.metadata.get("length_label") or row.metadata.get("target_tokens") or row.metadata.get("context_len") or "")
    qtype = str(row.metadata.get("question_type") or row.metadata.get("question_type_label") or row.source_task)
    return {
        "panel_path": str(panel_path),
        "task_id": row.task_id,
        "benchmark": row.source_benchmark,
        "panel_family": str(row.metadata.get("panel_family", "")),
        "source_task": row.source_task,
        "question_type": qtype,
        "length_or_size": length,
        "scorer": row.scorer,
        "context_tokens_est": str(len(row.context) // 4),
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
    by_length = Counter(str(row.metadata.get("length_label") or row.metadata.get("target_tokens") or "unknown") for row in rows)
    lines = ["# Balanced context 100 panel", ""]
    lines.append(f"Task file: `{panel_path}`")
    lines.append("")
    lines.append("## Composition")
    lines.append("")
    lines.append(f"- total rows: `{len(rows)}`")
    lines.append(f"- by benchmark: `{dict(by_benchmark)}`")
    lines.append(f"- by panel family: `{dict(by_family)}`")
    lines.append(f"- by context length/size: `{dict(by_length)}`")
    lines.append("")
    lines.append("## Intended Codex run")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run python scripts/run/run_task_panel_codex_parallel.py \\")
    lines.append("  --tasks data/benchmarks/confirmation/balanced_context_100.jsonl \\")
    lines.append("  --root-dir artifacts/batches/balanced_context_100/<timestamp> \\")
    lines.append("  --model gpt-5.4-mini --condition auto --chunk-tokens 32000 \\")
    lines.append("  --auto-compact-limit 150000 --reasoning-effort high --verbosity low \\")
    lines.append("  --timeout-s 300 --max-workers 4")
    lines.append("```")
    lines.append("")
    lines.append("## Manifest preview")
    lines.append("")
    lines.append("| Benchmark | Family | Source task | Question type | Length/size | Task id |")
    lines.append("|---|---|---|---|---|---|")
    for row in manifest[:120]:
        lines.append(
            f"| `{row['benchmark']}` | `{row['panel_family']}` | `{row['source_task']}` | "
            f"`{row['question_type']}` | `{row['length_or_size']}` | `{row['task_id']}` |"
        )
    path.write_text("\n".join(lines) + "\n")


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
