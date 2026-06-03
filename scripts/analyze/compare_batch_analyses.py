#!/usr/bin/env python3
"""Compare analysis outputs produced by analyze_codex_batch.py."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--analysis", action="append", required=True, help="label=analysis_dir")
    p.add_argument("--out", required=True, help="Markdown report path")
    return p.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> int:
    args = parse_args()
    entries: list[tuple[str, Path]] = []
    for item in args.analysis:
        label, raw = item.split("=", 1)
        entries.append((label, Path(raw)))

    lines = ["# Batch comparison", ""]

    lines.append("## Overall")
    lines.append("")
    lines.append("| Benchmark | Resolved | Deterministic acc (total) | Deterministic acc (resolved) | Judge acc (total) | Judge acc (resolved) | Avg compactions/run |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, directory in entries:
        summary = json.loads((directory / "summary.json").read_text())["overall"]
        lines.append(
            "| {label} | {resolved}/{total} ({rate:.1%}) | {det_total:.1%} | {det_resolved:.1%} | {judge_total} | {judge_resolved} | {comp:.2f} |".format(
                label=label,
                resolved=summary["n_resolved"],
                total=summary["n_total"],
                rate=summary["resolved_rate"],
                det_total=summary["deterministic_accuracy_total"],
                det_resolved=summary["deterministic_accuracy_resolved"],
                judge_total=(f"{summary['judge_accuracy_total']:.1%}" if summary.get("judge_accuracy_total") is not None else "n/a"),
                judge_resolved=(f"{summary['judge_accuracy_resolved']:.1%}" if summary.get("judge_accuracy_resolved") is not None else "n/a"),
                comp=summary["avg_compactions_total"],
            )
        )
    lines.append("")
    lines.append("## By model")
    lines.append("")
    for label, directory in entries:
        rows = read_csv(directory / "by_model.csv")
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Model | Resolved | Det total | Det resolved | Judge total | Judge resolved | Parse rate | Compactions/run |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for row in rows:
            lines.append(
                "| {model} | {resolved}/{total} | {det_total:.1%} | {det_resolved:.1%} | {judge_total} | {judge_resolved} | {parse:.1%} | {comp:.2f} |".format(
                    model=row["key_1"],
                    resolved=row["n_resolved"],
                    total=row["n_total"],
                    det_total=float(row["deterministic_accuracy_total"]),
                    det_resolved=float(row["deterministic_accuracy_resolved"]),
                    judge_total=(f"{float(row['judge_accuracy_total']):.1%}" if row.get("judge_accuracy_total") not in {None, '', 'None'} else "n/a"),
                    judge_resolved=(f"{float(row['judge_accuracy_resolved']):.1%}" if row.get("judge_accuracy_resolved") not in {None, '', 'None'} else "n/a"),
                    parse=float(row["parse_ok_rate"]),
                    comp=float(row["avg_compactions_total"]),
                )
            )
        lines.append("")

    lines.append("## By length")
    lines.append("")
    for label, directory in entries:
        rows = read_csv(directory / "by_length.csv")
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Length | Resolved | Det total | Det resolved | Judge total | Judge resolved | Compactions/run |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in rows:
            lines.append(
                "| {length} | {resolved}/{total} | {det_total:.1%} | {det_resolved:.1%} | {judge_total} | {judge_resolved} | {comp:.2f} |".format(
                    length=row["key_1"],
                    resolved=row["n_resolved"],
                    total=row["n_total"],
                    det_total=float(row["deterministic_accuracy_total"]),
                    det_resolved=float(row["deterministic_accuracy_resolved"]),
                    judge_total=(f"{float(row['judge_accuracy_total']):.1%}" if row.get("judge_accuracy_total") not in {None, '', 'None'} else "n/a"),
                    judge_resolved=(f"{float(row['judge_accuracy_resolved']):.1%}" if row.get("judge_accuracy_resolved") not in {None, '', 'None'} else "n/a"),
                    comp=float(row["avg_compactions_total"]),
                )
            )
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
