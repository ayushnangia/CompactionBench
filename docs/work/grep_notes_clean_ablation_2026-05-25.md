# Grep + notes clean ablation

Started: 2026-05-25

Goal: isolate whether the useful thing is retrieval, structured notes, or putting notes in a file.

## Proper task panel

Same 250-task real panel used by `docs/real_full_context_vs_grep_500.html`:

`data/benchmarks/confirmation/real_lossless_250.jsonl`

Relevant existing baselines:

- Full context: 40 / 250 in `docs/real_full_context_vs_grep_500.html`
- File grep: 50 / 250 in `docs/real_full_context_vs_grep_500.html`
- Previous OS-level/context-access run: `artifacts/batches/os_levels_babilong_oolong_1500/20260519-185502`
  - full_context: 36 / 250
  - grep_file: 52 / 250
  - paged_context: 37 / 250
  - virtual_context_8k: 59 / 250
  - virtual_context_24k: 62 / 250
  - virtual_context_48k: 60 / 250

## New clean ablation arms

Implemented in `scripts/run_lossless_vs_grep_codex_parallel.py`:

1. `raw_snippets_prompt`
   - harness does deterministic query-term grep windows
   - raw snippets are pasted into prompt

2. `raw_snippets_file`
   - exact same raw snippets
   - saved as `notes.md`
   - model answers from the note file

3. `structured_notes_prompt`
   - harness builds the existing structured virtual-context evidence packet
   - notes are pasted into prompt

4. `structured_notes_file`
   - exact same structured notes
   - saved as `notes.md`
   - model answers from the note file

This separates:

- raw retrieval vs structured notes: `raw_snippets_*` vs `structured_notes_*`
- prompt vs file storage: `*_prompt` vs `*_file`

## Full run

Root:

`artifacts/batches/notes_ablation_1000/20260525-223108`

Command:

```bash
uv run python scripts/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/real_lossless_250.jsonl \
  --root-dir artifacts/batches/notes_ablation_1000/20260525-223108 \
  --arm raw_snippets_prompt \
  --arm raw_snippets_file \
  --arm structured_notes_prompt \
  --arm structured_notes_file \
  --model gpt-5.4-mini \
  --timeout-s 360 \
  --reasoning-effort low \
  --verbosity low \
  --max-workers 8
```

Status files:

- `artifacts/batches/notes_ablation_1000/20260525-223108/status.json`
- `artifacts/batches/notes_ablation_1000/20260525-223108/runner.out`
- `artifacts/batches/notes_ablation_1000/20260525-223108/pid.txt`

## Completion + results

Completed: 2026-05-25T17:36:55Z

- 1000 / 1000 runs completed
- 0 subprocess failures
- 0 record errors

Analysis:

```bash
uv run python scripts/analyze_lossless_vs_grep.py \
  --runs-root artifacts/batches/os_levels_babilong_oolong_1500/20260519-185502/runs \
  --runs-root artifacts/batches/notes_ablation_1000/20260525-223108/runs \
  --out-dir artifacts/batches/notes_ablation_1000/20260525-223108/analysis \
  --title "Grep + notes clean ablation" \
  --baseline-arm grep_file
```

Strict accuracy on 250-task panel:

| Arm | Correct | Accuracy | Parse OK | Avg tools | Avg seconds |
|---|---:|---:|---:|---:|---:|
| full_context | 36/250 | 14.4% | 248 | 0.00 | 15.9 |
| grep_file | 52/250 | 20.8% | 250 | 4.32 | 26.1 |
| raw_snippets_prompt | 37/250 | 14.8% | 250 | 0.00 | 9.9 |
| raw_snippets_file | 39/250 | 15.6% | 250 | 3.99 | 25.0 |
| structured_notes_prompt | 54/250 | 21.6% | 250 | 0.00 | 11.8 |
| structured_notes_file | 41/250 | 16.4% | 250 | 3.83 | 21.7 |
| virtual_context_24k | 62/250 | 24.8% | 250 | 0.00 | 12.9 |

Interpretation:

- Raw snippets are not enough; they underperform grep_file.
- Structured notes in prompt slightly beat grep_file (54 vs 52) and are faster/no-tool.
- Same structured notes in file underperform prompt, so `.md` storage itself is not the win in this setup.
- The stronger previous virtual-context variants still do best (59-62 / 250), likely because their selection/extraction is better than the simpler note-file ablation.
