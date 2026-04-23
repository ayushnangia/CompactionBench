#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-artifacts/batches/babilong_codex_auto_high_models/$(date +%Y%m%d-%H%M%S)}"
SPEC="specs/babilong_codex_auto_high_models.yaml"
TASK_DIR="data/benchmarks/babilong_codex_128k_to_1m"
RUNS_DIR="$ROOT_DIR/runs"
RESULTS_DIR="$ROOT_DIR/results"
LOG_FILE="$ROOT_DIR/runner.log"
REPORT_FILE="$ROOT_DIR/report.txt"
INVENTORY_JSON="$ROOT_DIR/task_inventory.json"
INVENTORY_CSV="$ROOT_DIR/task_inventory.csv"
STATUS_FILE="$ROOT_DIR/status.txt"

mkdir -p "$ROOT_DIR" "$RUNS_DIR" "$RESULTS_DIR"
cp "$SPEC" "$ROOT_DIR/spec.yaml"

echo "started $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
echo "root_dir=$ROOT_DIR" >> "$STATUS_FILE"
echo "log_file=$LOG_FILE" >> "$STATUS_FILE"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== CompactionBench batch run =="
echo "root_dir=$ROOT_DIR"
echo "spec=$SPEC"
echo "task_dir=$TASK_DIR"

declare -i FAILURES=0

uv run python - <<'PY' "$TASK_DIR" "$INVENTORY_JSON" "$INVENTORY_CSV"
import csv, json, sys
from pathlib import Path
from compactionbench.schema import load_task_rows

task_dir = Path(sys.argv[1])
out_json = Path(sys.argv[2])
out_csv = Path(sys.argv[3])
rows = []
for path in sorted(task_dir.glob('*.jsonl')):
    task = load_task_rows(path)[0]
    rows.append({
        'file': path.name,
        'task_id': task.task_id,
        'source_task': task.source_task,
        'length': task.metadata.get('length_label'),
        'question': task.question,
        'gold_answer': task.gold_answer,
        'scorer': task.scorer,
    })
out_json.write_text(json.dumps(rows, indent=2))
with out_csv.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['file','task_id','source_task','length','question','gold_answer','scorer'])
    w.writeheader()
    w.writerows(rows)
print(f'wrote inventory with {len(rows)} tasks')
PY

run_length() {
  local model="$1"
  local length="$2"
  local chunk_tokens="$3"

  echo
  echo "== model=$model length=$length chunk_tokens=$chunk_tokens =="

  local task_args=()
  local found=0
  while IFS= read -r file; do
    task_args+=(--tasks "$file")
    found=1
  done < <(find "$TASK_DIR" -maxdepth 1 -type f -name "*_""$length"".jsonl" | sort)

  if [[ "$found" -eq 0 ]]; then
    echo "No tasks found for length=$length"
    return 1
  fi

  uv run cbench run codex \
    "${task_args[@]}" \
    --model "$model" \
    --condition auto \
    --chunk-tokens "$chunk_tokens" \
    --out "$RUNS_DIR" \
    --timeout-s 240 \
    --auto-compact-limit 150000 \
    --reasoning-effort high \
    --verbosity low
}

for model in gpt-5.4 gpt-5.4-mini gpt-5.3-codex; do
  for pair in "128k 16000" "256k 32000" "512k 64000" "1M 100000"; do
    set -- $pair
    length="$1"
    chunk_tokens="$2"
    if ! run_length "$model" "$length" "$chunk_tokens"; then
      echo "FAILED model=$model length=$length"
      FAILURES+=1
    fi
  done
done

echo

echo "== scoring =="
uv run cbench score --runs "$RUNS_DIR" --out "$RESULTS_DIR"
uv run cbench report --results "$RESULTS_DIR" | tee "$REPORT_FILE"

if [[ "$FAILURES" -gt 0 ]]; then
  echo "failed $(date -u +%Y-%m-%dT%H:%M:%SZ) failures=$FAILURES" >> "$STATUS_FILE"
  echo "done_with_failures=$FAILURES"
  exit 1
fi

echo "completed $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATUS_FILE"
echo "done"
