# PEEK run on proper 250-task lossless text panel

Started: 2026-05-25

This is the PEEK context-map arm for the same 250-task real panel used in `docs/real_full_context_vs_grep_500.html`.

## Baseline numbers from the clean 500-run control

Source: `docs/real_full_context_vs_grep_500.html`

- Task panel: `data/benchmarks/confirmation/real_lossless_250.jsonl`
- Full context: 40 / 250 correct = 16%
- File search: 50 / 250 correct = 20%
- 0 compaction events
- Model/settings in original manifest: `gpt-5.4-mini`, low reasoning, low verbosity, 360s timeout

## PEEK run

Root:

`artifacts/batches/peek_real_lossless_250/20260525-172802`

Command:

```bash
uv run python scripts/run_peek_codex_sequential.py \
  --tasks data/benchmarks/confirmation/real_lossless_250.jsonl \
  --root-dir artifacts/batches/peek_real_lossless_250/20260525-172802 \
  --peek-updater codex \
  --peek-evolve-steps 4 \
  --timeout-s 360 \
  --reasoning-effort low \
  --verbosity low \
  --model gpt-5.4-mini
```

Status files:

- `artifacts/batches/peek_real_lossless_250/20260525-172802/status.json`
- `artifacts/batches/peek_real_lossless_250/20260525-172802/runner.out`
- `artifacts/batches/peek_real_lossless_250/20260525-172802/pid.txt`

## Completion + results

Completed: 2026-05-25T18:34:47Z

- 250 / 250 jobs completed
- 0 subprocess failures
- 1 record error: one OOLONG multidoc-rolls task timed out at 360s
- Parse OK: 249 / 250

Analysis command:

```bash
uv run python scripts/analyze_lossless_vs_grep.py \
  --runs-root artifacts/batches/os_levels_babilong_oolong_1500/20260519-185502/runs \
  --runs-root artifacts/batches/peek_real_lossless_250/20260525-172802/runs \
  --out-dir artifacts/batches/peek_real_lossless_250/20260525-172802/analysis \
  --title "PEEK context map on real lossless 250" \
  --baseline-arm grep_file
```

Strict result on 250-task panel:

| Arm | Correct | Accuracy | Relaxed correct | Parse OK | Avg tools | Avg seconds |
|---|---:|---:|---:|---:|---:|---:|
| full_context | 36/250 | 14.4% | 89 | 248 | 0.00 | 15.9 |
| grep_file | 52/250 | 20.8% | 93 | 250 | 4.32 | 26.1 |
| peek_context_map | 46/250 | 18.4% | 93 | 249 | 4.62 | 28.6 |
| virtual_context_24k | 62/250 | 24.8% | 98 | 250 | 0.00 | 12.9 |

Interpretation:

- PEEK context-map integration works on the full 250-task panel.
- It does not beat grep_file on strict accuracy here (46 vs 52), but matches grep_file on relaxed correctness (93 each).
- This panel has 105 exact context groups for 250 tasks; PEEK has some reuse, but not as much as a benchmark intentionally built around many questions per one recurring context.

## Notes

- This uses upstream PEEK core from `artifacts/repos/peek` via `peek.CachePolicy`.
- Because no `OPENAI_API_KEY` is present in this environment, the PEEK Distiller/Cartographer LM is backed by Codex CLI through the local adapter (`--peek-updater codex`).
- Context grouping is by exact context hash, so maps are only reused for truly repeated contexts.
