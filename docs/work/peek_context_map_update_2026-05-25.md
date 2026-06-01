# Weekly update: PEEK context-map setup

## Short version

PEEK is directly relevant to our current CompactionBench direction. It frames the thing we have been circling around as **active external-context state**: keep a small prompt-resident map of a recurring context, while the full source stays outside the prompt as files/tools.

This week I set up a PEEK-style benchmark arm and ran a small OOLONG canary.

## Why it matters for our benchmark

PEEK says raw file access, RAG, history compaction, and prompt-learning are not enough by themselves because they do not preserve reusable **orientation knowledge** about the recurring context:

- what the context contains
- how it is organized
- schemas / delimiters / constants
- reusable aggregate results

That matches our own finding that full context, grep, paging, virtual context, and RLM/code-over-context behave differently depending on whether the task needs lookup, counting, notes, or code search.

## What is now set up

- Upstream PEEK repo cloned locally under `artifacts/repos/peek` and installed in the current uv environment.
- New runner: `scripts/run_peek_codex_sequential.py`
- Runner behavior:
  - groups tasks by recurring context hash
  - keeps one PEEK context map per group
  - writes the full source to `context.txt`
  - prepends the current context map in the Codex prompt
  - optionally updates the map with upstream `peek.CachePolicy`
  - saves run records, logs, manifests, and map snapshots

## Smoke / canary runs

### 2-task recurring-context smoke

Command:

```bash
uv run python scripts/run_peek_codex_sequential.py \
  --tasks data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl \
  --root-dir artifacts/batches/_smoke_peek_oolong_two_task \
  --task-id oolong-synth-counting-256k-418040024 \
  --task-id oolong-synth-timeline-256k-418040038 \
  --peek-updater codex \
  --peek-evolve-steps 1 \
  --timeout-s 240 \
  --reasoning-effort low \
  --verbosity low \
  --model gpt-5.4-mini
```

Result:

| Run | Task | Correct | Parse | Duration | Map tokens after |
|---|---|---:|---:|---:|---:|
| 1 | OOLONG-synth counting, 256k | ✅ | ✅ | 85.2s | 215 |
| 2 | OOLONG-synth timeline, same context | ✅ | ✅ | 22.1s | 215 |

Artifacts:

- `artifacts/batches/_smoke_peek_oolong_two_task/status.json`
- `artifacts/batches/_smoke_peek_oolong_two_task/job_results.json`
- `artifacts/batches/_smoke_peek_oolong_two_task/maps/753c5f26bfe8208b/latest.peek.json`

The learned map cached the dataset layout, allowed labels, parsing schema, and corpus size.

### 5-task OOLONG canary

Command:

```bash
uv run python scripts/run_peek_codex_sequential.py \
  --tasks data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl \
  --root-dir artifacts/batches/peek_oolong_5task \
  --peek-updater codex \
  --peek-evolve-steps 4 \
  --timeout-s 300 \
  --reasoning-effort low \
  --verbosity low \
  --model gpt-5.4-mini
```

Result: **3/5 correct, 5/5 parse OK, 0 runner errors**.

| Split | Tasks | Correct |
|---|---:|---:|
| OOLONG-synth shared context | 3 | 3 |
| OOLONG-real D&D shared context | 2 | 0 |

Artifacts:

- `artifacts/batches/peek_oolong_5task/status.json`
- `artifacts/batches/peek_oolong_5task/job_results.json`
- `artifacts/batches/peek_oolong_5task/maps/`

Interpretation: PEEK-style maps are working mechanically and helped/cache-populated on recurring synthetic OOLONG. The real D&D roll/spell tasks still need structured event extraction/counters; a small orientation map alone did not fix those (rolls: predicted 94 vs gold 114; spells: predicted 38 vs gold 49).

### 20-task cross-benchmark text suite

Also ran the PEEK arm on the existing cross-benchmark text panel:

```bash
uv run python scripts/run_peek_codex_sequential.py \
  --tasks data/benchmarks/confirmation/cross_benchmark_20_question_types.jsonl \
  --root-dir artifacts/batches/peek_cross_benchmark_20 \
  --peek-updater codex \
  --peek-evolve-steps 4 \
  --timeout-s 300 \
  --reasoning-effort low \
  --verbosity low \
  --model gpt-5.4-mini
```

Result: **20/20 completed, 20/20 parse OK, 0 runner errors, 6/20 exact/deterministic correct**.

| Benchmark | Tasks | Correct |
|---|---:|---:|
| LME | 7 | 0 |
| OOLONG | 5 | 3 |
| Synthetic | 3 | 2 |
| BABILong | 5 | 1 |

Artifacts:

- `artifacts/batches/peek_cross_benchmark_20/status.json`
- `artifacts/batches/peek_cross_benchmark_20/job_results.json`
- `artifacts/batches/peek_cross_benchmark_20/maps/`

Important caveat: this text panel has **17 context groups for 20 tasks**, so most tasks are first-time contexts. That means it tests whether the PEEK runner/map-update machinery works across the text suite, but it is not the ideal evaluation of PEEK’s persistent-map advantage. The recurring-context signal is mainly the OOLONG groups.

## Next comparison

Compare against the existing arms already set up in `scripts/run_lossless_vs_grep_codex_parallel.py`:

- `full_context`
- `grep_file`
- `paged_context`
- `virtual_context`
- `virtual_context_rlm`
- `rlm_repl_depth0`
- new `peek_context_map` runner above

## Caveat

The new runner uses PEEK’s upstream `CachePolicy`, but the Distiller/Cartographer backbone is Codex CLI by default (`--peek-updater codex`) rather than the exact OpenAI chat-completions client from the paper. Use `--peek-updater openai` for a closer paper-style setup.
