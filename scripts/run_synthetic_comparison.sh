#!/usr/bin/env bash
# Run tiny synthetic compression comparison.
# Usage: bash scripts/run_synthetic_comparison.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BATCH_DIR="artifacts/batches/synthetic_compression_comparison/${TIMESTAMP}"
mkdir -p "$BATCH_DIR"/{runs,job_logs,results}

echo "=== synthetic compression comparison ==="
echo "batch dir: $BATCH_DIR"

# Condition 1: raw auto
echo ""
echo "--- auto_raw ---"
uv run cbench run codex \
  --tasks data/benchmarks/synthetic_tasks_v1.jsonl \
  --model gpt-5.4-mini \
  --condition auto \
  --chunk-tokens 16000 \
  --out "$BATCH_DIR/runs/auto_raw" \
  --reasoning-effort low \
  --verbosity low \
  --auto-compact-limit 150000

# Condition 2: compressed query-blind
echo ""
echo "--- compressed_qb ---"
uv run cbench run codex \
  --tasks data/benchmarks/synthetic_compressed_qb_v1.jsonl \
  --model gpt-5.4-mini \
  --condition auto \
  --chunk-tokens 16000 \
  --out "$BATCH_DIR/runs/compressed_qb" \
  --reasoning-effort low \
  --verbosity low \
  --auto-compact-limit 150000

# Condition 3: compressed query-aware
echo ""
echo "--- compressed_qa ---"
uv run cbench run codex \
  --tasks data/benchmarks/synthetic_compressed_qa_v1.jsonl \
  --model gpt-5.4-mini \
  --condition auto \
  --chunk-tokens 16000 \
  --out "$BATCH_DIR/runs/compressed_qa" \
  --reasoning-effort low \
  --verbosity low \
  --auto-compact-limit 150000

# Score
echo ""
echo "=== scoring ==="
uv run cbench score --runs "$BATCH_DIR/runs" --out "$BATCH_DIR/results"
echo "done. results at $BATCH_DIR/results/summary.json"
