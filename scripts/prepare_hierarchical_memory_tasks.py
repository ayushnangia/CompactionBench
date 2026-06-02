#!/usr/bin/env python3
"""Prepare synthetic age-controlled hierarchical-memory tasks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.hierarchical_tasks import generate_hierarchical_memory_tasks
from compactionbench.schema import write_task_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/benchmarks/hierarchical_memory_canary.jsonl")
    p.add_argument("--streams", type=int, default=4)
    p.add_argument("--days", type=int, default=45)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-noise", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rows = generate_hierarchical_memory_tasks(
        streams=args.streams,
        days=args.days,
        seed=args.seed,
        include_noise=not args.no_noise,
    )
    out = Path(args.out)
    write_task_rows(rows, out)
    print(f"wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
