#!/usr/bin/env python3
"""Compute retention and degradation metrics from existing batch results.

Metrics:
1. Compaction Retention Score (CRS) — how often the gold answer appears in the run trace
2. Compaction Degradation Ratio (CDR) — accuracy drop as context grows
3. Exact vs Aggregate Score gap — difference between BABILong and OOLONG performance
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

OUTPUT_DIR = Path("artifacts/analysis/retention_metrics")


def iter_run_records(runs_root: Path):
    for path in sorted(runs_root.rglob("*.json")):
        try:
            yield json.loads(path.read_text())
        except Exception:
            continue


def compute_retention_score(runs_root: Path, label: str) -> dict:
    """For each run, check whether the gold answer appears anywhere in the trace."""
    records = list(iter_run_records(runs_root))
    if not records:
        return {"label": label, "n": 0, "retention": 0, "accuracy": 0}

    retention = 0
    correct = 0
    total = 0

    for rec in records:
        total += 1
        gold = str(rec.get("gold_answer") or "").strip().lower()
        if not gold:
            continue

        # Check if gold appears in any turn preview
        turns = rec.get("turns") or []
        found = False
        for t in turns:
            preview = str(t.get("content_preview") or "").lower()
            if gold in preview:
                found = True
                break

        if found:
            retention += 1

        if rec.get("correct"):
            correct += 1

    return {
        "label": label,
        "n": total,
        "retention": retention / max(total, 1),
        "accuracy": correct / max(total, 1),
    }


def compute_retention_by_length(runs_root: Path, label: str) -> dict:
    """Retention and accuracy broken down by length extracted from task_id."""
    LENGTH_RE = re.compile(r"-(1k|2k|4k|8k|16k|32k|64k|128k|256k|512k|1M|2M|4M|\d+ep)-")

    records = list(iter_run_records(runs_root))
    buckets: dict[str, dict] = defaultdict(lambda: {"retention": 0, "correct": 0, "total": 0})

    for rec in records:
        tid = rec.get("task_id", "")
        m = LENGTH_RE.search(tid)
        length = m.group(1) if m else "unknown"

        gold = str(rec.get("gold_answer") or "").strip().lower()
        if not gold:
            continue

        turns = rec.get("turns") or []
        found = any(gold in str(t.get("content_preview") or "").lower() for t in turns)

        buckets[length]["total"] += 1
        if found:
            buckets[length]["retention"] += 1
        if rec.get("correct"):
            buckets[length]["correct"] += 1

    result = {"label": label, "by_length": {}}
    for length, data in sorted(buckets.items()):
        t = data["total"]
        result["by_length"][length] = {
            "n": t,
            "retention": data["retention"] / max(t, 1),
            "accuracy": data["correct"] / max(t, 1),
        }
    return result


def compute_exact_aggregate_gap(runs_root: Path, label: str) -> dict:
    """Compare exact-memory tasks vs aggregation tasks."""
    records = list(iter_run_records(runs_root))
    if not records:
        return {"label": label, "gap": None}

    # Heuristic: BABILong tasks test exact memory, OOLONG tasks test aggregation
    exact_correct = 0
    exact_total = 0
    agg_correct = 0
    agg_total = 0

    for rec in records:
        benchmark = rec.get("source_benchmark", "")
        if benchmark == "babilong":
            exact_total += 1
            if rec.get("correct"):
                exact_correct += 1
        elif benchmark == "oolong":
            agg_total += 1
            if rec.get("correct"):
                agg_correct += 1

    exact_acc = exact_correct / max(exact_total, 1)
    agg_acc = agg_correct / max(agg_total, 1)
    gap = exact_acc / max(agg_acc, 0.001)

    return {
        "label": label,
        "exact_accuracy": exact_acc,
        "aggregate_accuracy": agg_acc,
        "gap": gap,
        "exact_n": exact_total,
        "agg_n": agg_total,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    batch_roots = [
        ("babilong-qa1-10", "artifacts/batches/babilong_codex_auto_high_models_parallel/20260422-123112/runs"),
        ("babilong-qa11-20", "artifacts/batches/babilong_codex_auto_high_models_qa11_to_20_s3/20260422-095719/runs"),
        ("oolong-synth", "artifacts/batches/oolong_synth_codex_auto_high_models/20260423-173654/runs"),
    ]

    all_retention: list[dict] = []
    all_by_length: list[dict] = []

    for label, root_str in batch_roots:
        root = Path(root_str)
        if not root.exists():
            print(f"SKIP {label}: {root_str} not found")
            continue

        print(f"\n=== {label} ===")

        ret = compute_retention_score(root, label)
        print(f"  retention: {ret['retention']:.1%}  accuracy: {ret['accuracy']:.1%}  (n={ret['n']})")
        all_retention.append(ret)

        by_len = compute_retention_by_length(root, label)
        all_by_length.append(by_len)
        for length, data in by_len["by_length"].items():
            print(f"    {length:>8s}: retention {data['retention']:.1%}  accuracy {data['accuracy']:.1%}  n={data['n']}")

    # Save
    (OUTPUT_DIR / "retention_summary.json").write_text(json.dumps(all_retention, indent=2))
    (OUTPUT_DIR / "retention_by_length.json").write_text(json.dumps(all_by_length, indent=2))

    # Compute gaps
    for label, root_str in batch_roots:
        root = Path(root_str)
        if not root.exists():
            continue
        gap_data = compute_exact_aggregate_gap(root, label)
        print(f"\nGAP {label}: exact={gap_data['exact_accuracy']:.1%} agg={gap_data['aggregate_accuracy']:.1%} gap={gap_data['gap']:.2f}x")

    print(f"\nSaved to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
