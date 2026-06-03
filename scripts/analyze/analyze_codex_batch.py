#!/usr/bin/env python3
"""Analyze a batch of direct run artifacts with optional judge outputs.

Produces:
- rows_enriched.csv
- summary.json
- by_model.csv
- by_model_length.csv
- by_model_task.csv
- by_length.csv
- by_task.csv
- error_categories.csv
- report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

csv.field_size_limit(sys.maxsize)

from compactionbench.runners.run import _load_codex_session_compaction_events
from compactionbench.core.schema import RunRecord
from compactionbench.core.score import iter_run_records, score_value_one

LENGTH_RE = re.compile(r"-(1k|2k|4k|8k|16k|32k|64k|128k|256k|512k|1M|2M|4M|\d+ep)-")


@dataclass
class Row:
    task_id: str
    benchmark: str
    source_task: str
    model: str
    condition: str
    length: str
    parse_ok: bool
    contaminated: bool
    error: str | None
    error_category: str
    deterministic_score: float
    deterministic_correct: bool
    judge_applied: bool
    judge_equivalent: bool | None
    final_correct_with_judge: bool
    compaction_event_count: int
    has_compaction: bool
    duration_s: float | None


@dataclass
class Stats:
    n_total: int
    n_resolved: int
    n_errors: int
    resolved_rate: float
    parse_ok_rate: float
    parse_ok_resolved_rate: float
    deterministic_accuracy_total: float
    deterministic_accuracy_resolved: float
    judge_accuracy_total: float | None
    judge_accuracy_resolved: float | None
    avg_score_total: float
    avg_score_resolved: float
    avg_compactions_total: float
    avg_compactions_resolved: float
    runs_with_any_compaction: int
    avg_duration_s: float | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--runs-root", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--judge-csv", default=None)
    p.add_argument("--title", default=None)
    return p.parse_args()


def infer_length(task_id: str) -> str:
    m = LENGTH_RE.search(task_id)
    return m.group(1) if m else "unknown"


def categorize_error(error: str | None, *, parse_ok: bool) -> str:
    if error:
        lowered = error.lower()
        if "usage limit" in lowered or "purchase more credits" in lowered:
            return "usage_limit"
        if "token_invalidated" in lowered or "refresh_token" in lowered or "access token" in lowered:
            return "auth"
        if "timeoutexpired" in lowered or "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        return "runtime_error"
    if not parse_ok:
        return "parse_only"
    return "none"


def _judge_key(task_id: str, model: str, harness: str, condition: str) -> tuple[str, str, str, str]:
    return (task_id, model, harness, condition)



def read_judge_map(path: Path | None) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not path or not path.exists():
        return {}
    rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[_judge_key(row["task_id"], row["model"], row["harness"], row["condition"])] = row
    return rows


def fixed_compaction_count(rec: RunRecord) -> int:
    if rec.compaction_events:
        return len(rec.compaction_events)
    if rec.harness == "codex" and rec.condition == "auto" and rec.session_id:
        return len(_load_codex_session_compaction_events(rec.session_id, condition=rec.condition))
    return 0


def build_rows(runs_root: Path, judge_map: dict[tuple[str, str, str, str], dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    for run_path in iter_run_records(runs_root):
        rec = RunRecord.model_validate_json(run_path.read_text())
        agent_answer = rec.final_answer_parsed.answer if rec.final_answer_parsed else None
        score = score_value_one(
            scorer=rec.scorer,
            gold=rec.gold_answer,
            gold_aliases=rec.gold_answer_aliases,
            answer=agent_answer,
        )
        judge = judge_map.get(_judge_key(rec.task_id, rec.model, rec.harness, rec.condition))
        judge_applied = bool(judge and judge.get("judge_applied", "False") == "True")
        judge_equivalent_raw = judge.get("judge_equivalent") if judge else None
        judge_equivalent = None
        if judge_equivalent_raw in {"True", "False"}:
            judge_equivalent = judge_equivalent_raw == "True"
        final_correct = bool(rec.correct) if judge is None else (judge.get("final_correct_with_judge", "False") == "True")
        compactions = fixed_compaction_count(rec)
        rows.append(
            Row(
                task_id=rec.task_id,
                benchmark=rec.source_benchmark,
                source_task=rec.source_task,
                model=rec.model,
                condition=rec.condition,
                length=infer_length(rec.task_id),
                parse_ok=rec.parse_ok,
                contaminated=rec.contaminated_by_tools,
                error=rec.error,
                error_category=categorize_error(rec.error, parse_ok=rec.parse_ok),
                deterministic_score=score,
                deterministic_correct=bool(score >= 1.0),
                judge_applied=judge_applied,
                judge_equivalent=judge_equivalent,
                final_correct_with_judge=final_correct,
                compaction_event_count=compactions,
                has_compaction=compactions > 0,
                duration_s=rec.duration_s,
            )
        )
    return rows


def compute_stats(rows: list[Row], *, use_judge: bool) -> Stats:
    n_total = len(rows)
    resolved = [r for r in rows if not r.error]
    n_resolved = len(resolved)
    n_errors = n_total - n_resolved
    parse_ok = [r for r in rows if r.parse_ok]
    parse_ok_resolved = [r for r in resolved if r.parse_ok]
    durs = [r.duration_s for r in rows if r.duration_s is not None]

    return Stats(
        n_total=n_total,
        n_resolved=n_resolved,
        n_errors=n_errors,
        resolved_rate=n_resolved / n_total if n_total else 0.0,
        parse_ok_rate=len(parse_ok) / n_total if n_total else 0.0,
        parse_ok_resolved_rate=len(parse_ok_resolved) / n_resolved if n_resolved else 0.0,
        deterministic_accuracy_total=sum(r.deterministic_correct for r in rows) / n_total if n_total else 0.0,
        deterministic_accuracy_resolved=sum(r.deterministic_correct for r in resolved) / n_resolved if n_resolved else 0.0,
        judge_accuracy_total=(sum(r.final_correct_with_judge for r in rows) / n_total if n_total else 0.0) if use_judge else None,
        judge_accuracy_resolved=(sum(r.final_correct_with_judge for r in resolved) / n_resolved if n_resolved else 0.0) if use_judge else None,
        avg_score_total=sum(r.deterministic_score for r in rows) / n_total if n_total else 0.0,
        avg_score_resolved=sum(r.deterministic_score for r in resolved) / n_resolved if n_resolved else 0.0,
        avg_compactions_total=sum(r.compaction_event_count for r in rows) / n_total if n_total else 0.0,
        avg_compactions_resolved=sum(r.compaction_event_count for r in resolved) / n_resolved if n_resolved else 0.0,
        runs_with_any_compaction=sum(r.has_compaction for r in rows),
        avg_duration_s=(sum(durs) / len(durs) if durs else None),
    )


def group_and_write(rows: list[Row], out_dir: Path, *, use_judge: bool) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_csv(path: Path, fieldnames: list[str], items: list[dict[str, Any]]) -> None:
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(items)

    rows_payload = [asdict(r) for r in rows]
    write_csv(out_dir / "rows_enriched.csv", list(rows_payload[0].keys()) if rows_payload else [], rows_payload)

    overall = asdict(compute_stats(rows, use_judge=use_judge))

    group_specs = {
        "by_model.csv": lambda r: (r.model,),
        "by_model_length.csv": lambda r: (r.model, r.length),
        "by_model_task.csv": lambda r: (r.model, r.source_task),
        "by_length.csv": lambda r: (r.length,),
        "by_task.csv": lambda r: (r.source_task,),
    }

    group_json: dict[str, list[dict[str, Any]]] = {}
    for filename, key_fn in group_specs.items():
        buckets: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
        for row in rows:
            buckets[key_fn(row)].append(row)
        out_rows: list[dict[str, Any]] = []
        for key, bucket in sorted(buckets.items()):
            stats = asdict(compute_stats(bucket, use_judge=use_judge))
            rec = {f"key_{i+1}": part for i, part in enumerate(key)}
            rec.update(stats)
            out_rows.append(rec)
        if out_rows:
            write_csv(out_dir / filename, list(out_rows[0].keys()), out_rows)
        group_json[filename] = out_rows

    error_counts = Counter(r.error_category for r in rows)
    error_rows = [{"error_category": k, "count": v, "rate": v / len(rows) if rows else 0.0} for k, v in sorted(error_counts.items())]
    if error_rows:
        write_csv(out_dir / "error_categories.csv", list(error_rows[0].keys()), error_rows)

    summary = {
        "overall": overall,
        "groups": group_json,
        "errors": error_rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def write_report(summary: dict[str, Any], rows: list[Row], out_path: Path, *, title: str, use_judge: bool) -> None:
    overall = summary["overall"]
    errors = summary["errors"]
    by_model = summary["groups"].get("by_model.csv", [])
    by_length = summary["groups"].get("by_length.csv", [])
    by_task = summary["groups"].get("by_task.csv", [])

    lines = [f"# {title}", "", "## Overall", ""]
    lines.append(f"- total runs: `{overall['n_total']}`")
    lines.append(f"- resolved (no run error): `{overall['n_resolved']}` ({overall['resolved_rate']:.1%})")
    lines.append(f"- parse ok: `{overall['parse_ok_rate']:.1%}` of all runs")
    lines.append(f"- deterministic accuracy: `{overall['deterministic_accuracy_total']:.1%}` of all runs")
    lines.append(f"- deterministic accuracy on resolved runs: `{overall['deterministic_accuracy_resolved']:.1%}`")
    if use_judge and overall['judge_accuracy_total'] is not None:
        lines.append(f"- judge-adjusted accuracy: `{overall['judge_accuracy_total']:.1%}` of all runs")
        lines.append(f"- judge-adjusted accuracy on resolved runs: `{overall['judge_accuracy_resolved']:.1%}`")
    lines.append(f"- runs with any compaction: `{overall['runs_with_any_compaction']}`")
    lines.append(f"- avg compaction events per run: `{overall['avg_compactions_total']:.2f}`")
    lines.append("")

    lines.append("## Error categories")
    lines.append("")
    for row in errors:
        lines.append(f"- `{row['error_category']}`: `{row['count']}` ({row['rate']:.1%})")
    lines.append("")

    lines.append("## By model")
    lines.append("")
    for row in by_model:
        name = row['key_1']
        line = (
            f"- `{name}`: resolved `{row['n_resolved']}/{row['n_total']}` | "
            f"det `{row['deterministic_accuracy_total']:.1%}` total / `{row['deterministic_accuracy_resolved']:.1%}` resolved"
        )
        if use_judge and row['judge_accuracy_total'] is not None:
            line += f" | judge `{row['judge_accuracy_total']:.1%}` total / `{row['judge_accuracy_resolved']:.1%}` resolved"
        line += f" | parse `{row['parse_ok_rate']:.1%}` | compactions/run `{row['avg_compactions_total']:.2f}`"
        lines.append(line)
    lines.append("")

    lines.append("## By length")
    lines.append("")
    for row in by_length:
        lines.append(
            f"- `{row['key_1']}`: resolved `{row['n_resolved']}/{row['n_total']}` | det `{row['deterministic_accuracy_total']:.1%}` total / `{row['deterministic_accuracy_resolved']:.1%}` resolved | compactions/run `{row['avg_compactions_total']:.2f}`"
        )
    lines.append("")

    top_tasks = sorted(by_task, key=lambda r: (r['deterministic_accuracy_resolved'], r['n_resolved']), reverse=True)
    bottom_tasks = sorted(by_task, key=lambda r: (r['deterministic_accuracy_resolved'], r['n_resolved']))
    lines.append("## Tasks with best resolved accuracy")
    lines.append("")
    for row in top_tasks[:5]:
        lines.append(
            f"- `{row['key_1']}`: det `{row['deterministic_accuracy_resolved']:.1%}` on resolved runs (`{row['n_resolved']}` resolved / `{row['n_total']}` total)`"
        )
    lines.append("")
    lines.append("## Tasks with worst resolved accuracy")
    lines.append("")
    for row in bottom_tasks[:5]:
        lines.append(
            f"- `{row['key_1']}`: det `{row['deterministic_accuracy_resolved']:.1%}` on resolved runs (`{row['n_resolved']}` resolved / `{row['n_total']}` total)`"
        )

    out_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    runs_root = Path(args.runs_root)
    out_dir = Path(args.out_dir)
    judge_map = read_judge_map(Path(args.judge_csv) if args.judge_csv else None)
    rows = build_rows(runs_root, judge_map)
    summary = group_and_write(rows, out_dir, use_judge=bool(judge_map))
    title = args.title or f"Batch analysis for {runs_root}"
    write_report(summary, rows, out_dir / "report.md", title=title, use_judge=bool(judge_map))
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
