#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-}"
shift || true

if [[ -n "${ROOT_DIR}" ]]; then
  uv run python scripts/run_babilong_codex_parallel.py --spec specs/oolong_synth_codex_auto_high_models.yaml --root-dir "$ROOT_DIR" "$@"
else
  uv run python scripts/run_babilong_codex_parallel.py --spec specs/oolong_synth_codex_auto_high_models.yaml "$@"
fi
