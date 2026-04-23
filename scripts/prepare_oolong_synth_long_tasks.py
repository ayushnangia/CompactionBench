#!/usr/bin/env python3
"""Prepare long-context OOLONG-synth tasks into one-row direct-task JSONL files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.loaders import prepare_oolong_synth_task_matrix_from_hf, write_prepared_tasks


LENGTH_TO_TOKENS = {
    "128k": 131072,
    "256k": 262144,
    "512k": 524288,
    "1M": 1_048_576,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default="data/benchmarks/oolong_synth_codex_128k_to_1m_s3",
        help="Directory to write one prepared JSONL file per sample.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Samples per task-group / context-length pair.",
    )
    parser.add_argument(
        "--length",
        action="append",
        dest="lengths",
        help="Optional length label; repeat for multiple. Defaults to 128k, 256k, 512k, 1M.",
    )
    parser.add_argument(
        "--task-group",
        action="append",
        dest="task_groups",
        help="Optional task-group; repeat for multiple. Defaults to counting, user, timeline.",
    )
    parser.add_argument(
        "--include-labels",
        action="store_true",
        help="Use the in-context labeled variant of OOLONG-synth.",
    )
    parser.add_argument(
        "--split",
        default="test",
        help="HF split to read from (default: test).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lengths = args.lengths or ["128k", "256k", "512k", "1M"]
    task_groups = args.task_groups or ["counting", "user", "timeline"]

    for length in lengths:
        if length not in LENGTH_TO_TOKENS:
            raise SystemExit(f"Unsupported length: {length}")

    matrix = prepare_oolong_synth_task_matrix_from_hf(
        split=args.split,
        count_per_bucket=args.count,
        task_groups=task_groups,
        context_lens=[LENGTH_TO_TOKENS[length] for length in lengths],
        include_labels=args.include_labels,
    )

    written = 0
    for length in lengths:
        context_len = LENGTH_TO_TOKENS[length]
        for task_group in task_groups:
            rows = matrix[(task_group, context_len)]
            for idx, row in enumerate(rows):
                path = out_dir / f"oolong_synth_{task_group}_{length}_{idx:03d}.jsonl"
                write_prepared_tasks([row], path)
                print(path)
                written += 1

    print(f"Wrote {written} prepared files under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
