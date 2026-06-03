#!/usr/bin/env python3
"""Prepare multi-episode OOLONG-real tasks into one-row direct-task JSONL files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.datasets.loaders import prepare_oolong_real_task_matrix_from_hf, write_prepared_tasks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default="data/benchmarks/oolong_real_codex_3ep_to_16ep_s3",
        help="Directory to write one prepared JSONL file per sample.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Samples per question-type / episode-count pair.",
    )
    parser.add_argument(
        "--episode-count",
        action="append",
        dest="episode_counts",
        type=int,
        help="Optional episode count; repeat for multiple. Defaults to 3, 6, 10, 16.",
    )
    parser.add_argument(
        "--question-type",
        action="append",
        dest="question_types",
        help="Optional question type; repeat for multiple. Defaults to multidoc_rolls and multidoc_spells.",
    )
    parser.add_argument(
        "--split",
        default="test",
        help="HF split to read from (default: test).",
    )
    parser.add_argument(
        "--config",
        default="dnd",
        help="OOLONG-real config (default: dnd).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    episode_counts = args.episode_counts or [3, 6, 10, 16]
    question_types = args.question_types or ["multidoc_rolls", "multidoc_spells"]

    matrix = prepare_oolong_real_task_matrix_from_hf(
        split=args.split,
        count_per_bucket=args.count,
        question_types=question_types,
        episode_counts=episode_counts,
        config=args.config,
    )

    written = 0
    for episode_count in episode_counts:
        length_label = f"{episode_count}ep"
        for question_type in question_types:
            rows = matrix[(question_type, episode_count)]
            for idx, row in enumerate(rows):
                path = out_dir / f"oolong_real_{question_type}_{length_label}_{idx:03d}.jsonl"
                write_prepared_tasks([row], path)
                print(path)
                written += 1

    print(f"Wrote {written} prepared files under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
