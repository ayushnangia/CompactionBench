#!/usr/bin/env python3
"""Prepare long-context qa11-qa20 BABILong tasks from 0k upstream rows.

Upstream `RMT-team/babilong` provides qa11-qa20 only at config `0k`. This
script constructs long versions by embedding those real short tasks into cleaned
long BABILong carrier contexts from qa1-qa10 at the target length.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compactionbench.loaders import (
    BABILONG_EXTENDED_SOURCE_TASKS,
    BABILONG_LONG_CONFIGS,
    prepare_babilong_long_missing_tasks_from_hf,
    write_prepared_tasks,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default="data/benchmarks/babilong_codex_qa11_to_20_128k_to_1m_s3",
        help="Directory to write one prepared JSONL file per sample.",
    )
    parser.add_argument(
        "--carrier-dir",
        default="data/benchmarks/babilong_codex_128k_to_1m",
        help="Directory containing long BABILong carrier files for qa1-qa10.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Samples per split to prepare.",
    )
    parser.add_argument(
        "--length",
        action="append",
        dest="lengths",
        help="Optional target length label; repeat for multiple. Defaults to 128k,256k,512k,1M.",
    )
    parser.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Optional task name; repeat for multiple. Defaults to qa11-qa20.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    carrier_dir = Path(args.carrier_dir)
    lengths = args.lengths or ["128k", "256k", "512k", "1M"]
    tasks = args.tasks or list(BABILONG_EXTENDED_SOURCE_TASKS)

    for length in lengths:
        if length not in BABILONG_LONG_CONFIGS:
            raise SystemExit(f"Unsupported length: {length}")
    for task in tasks:
        if task not in BABILONG_EXTENDED_SOURCE_TASKS:
            raise SystemExit(f"Unsupported task: {task}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for length in lengths:
        for task in tasks:
            rows = prepare_babilong_long_missing_tasks_from_hf(
                length_label=length,
                split=task,
                count=args.count,
                carrier_dir=carrier_dir,
            )
            for idx, row in enumerate(rows):
                path = out_dir / f"babilong_{task}_{length}_{idx:03d}.jsonl"
                write_prepared_tasks([row], path)
                written += 1
                print(path)

    print(f"Wrote {written} prepared files under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
