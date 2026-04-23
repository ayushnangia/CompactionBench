# CompactionBench

CompactionBench is a small benchmark harness for one specific question:

> If a long benchmark context is injected into an agentic coding harness over many chat turns, does the harness still preserve the right facts when compaction is `off` vs `auto`?

This repo now uses the **simple direct-injection path** only.

This GitHub repo is meant to contain:
- the benchmark code,
- reviewed experiment specs,
- preparation and analysis scripts,
- tests,
- and lightweight docs.

It intentionally does **not** contain heavyweight run artifacts or all prepared benchmark corpora.

What it does:
- converts raw benchmark JSONL into validated task JSONL rows
- chunks each task context at run time
- injects the chunks into a live Claude Code or Codex session over repeated turns
- asks one final question
- scores whether the final JSON answer is correct
- logs compaction events and tool contamination

What it deliberately does **not** do anymore:
- no `README.md` task fixtures
- no `docs/chunk_XX.md`
- no distractor padding machinery
- no manual compaction variants
- no file-reading benchmark tasks

## Primary benchmarks

- **RULER** for clean retrieval-style long-context stress
- **BABILong** for distributed-fact retention at very long lengths
- **OOLONG** for long-context aggregation over many local decisions (counting, user, and timeline reasoning)

BABILong standardization in this repo:
- use **`RMT-team/babilong`** for real `1M` runs
- do **not** use `RMT-team/babilong-1k-samples` for `1M` because that dataset does not provide `1M` splits
- start with **`qa1`–`qa5`** as the clean first BABILong pilot
- for the main Codex compaction sweep, start at **`128k`** and go upward, not at `4k`
- `qa8` is a special case because answers can be comma-separated sets like `apple,football`, so it uses a set-aware scorer instead of naive exact string matching

LongBench v2 is intentionally not the primary benchmark here because it is much more reasoning-heavy, which makes failures harder to attribute to harness memory behavior.

OOLONG-specific note:
- `OOLONG-synth` is the easiest place to start in this repo because it already has clean, verifiable answers and explicit context-length buckets.
- `OOLONG-real` is also supported for preparation, but it is a much larger downstream dataset and is better used after the synthetic aggregation path is stable.

## Primary harnesses

- **Claude Code**
- **Codex CLI**

## Why the contexts must be huge

The target harness/model setups here already have large native windows:
- Claude Code models in this environment report about **200k** context
- Codex model metadata in the local cache reports:
  - `gpt-5.4`: **272k** context window
  - `gpt-5.4-mini`: **272k** context window
  - `gpt-5.3-codex`: **272k** context window
  - `gpt-5.3-codex-spark`: **128k** context window

Important note on Codex compaction defaults:
- Codex exposes `model_auto_compact_token_limit`
- if it is unset, the docs say it uses **model defaults**
- we do **not** have a documented numeric default threshold for those model defaults
- so for proper benchmark runs we prefer to pin an explicit auto-compaction threshold instead of relying on hidden defaults

So the main evaluation target is **1M+ context**, not 100k-ish context, because the goal is to force harness compaction to become load-bearing.

## Task format

Each prepared task is one JSONL row with:
- `task_id`
- `source_benchmark`
- `source_task`
- `source_sample_id`
- `context`
- `question`
- `gold_answer`
- `gold_answer_aliases`
- `scorer`
- `metadata`

These rows are validated with **Pydantic** before they are written.

## Run artifacts

Each run writes one validated JSON artifact with:
- task identity and benchmark metadata
- harness, model, condition
- chunking stats
- compact turn traces
- tool events
- compaction events
- raw final answer text
- parsed final answer JSON
- correctness
- contamination flag
- duration and cost when available

## Quickstart

### 1. Install

```bash
uv sync
```

### 2. Run tests

```bash
uv run pytest -q
```

### 3. Prepare RULER rows

```bash
uv run cbench prepare ruler \
  --input path/to/ruler.jsonl \
  --out data/benchmarks/ruler_1m.jsonl \
  --min-length 1000000 \
  --count 10 \
  --task niah_single_1
```

### 4. Prepare BABILong rows

```bash
uv run cbench prepare babilong \
  --input path/to/babilong_qa1_1m.jsonl \
  --out data/benchmarks/babilong_qa1_1m.jsonl \
  --count 10 \
  --dataset-name RMT-team/babilong \
  --source-task qa1 \
  --length-label 1M
```

### 4b. Prepare OOLONG-synth rows from Hugging Face

```bash
uv run cbench prepare oolong-synth-hf \
  --out data/benchmarks/oolong_synth_counting_128k.jsonl \
  --split test \
  --count 10 \
  --task-group counting \
  --context-len 131072
```

### 5. Run Claude Code

Claude Code runs in `--bare` mode for clean isolation. That means you must provide bare-mode auth either via `ANTHROPIC_API_KEY` or via `--settings` with an `apiKeyHelper`-capable Claude settings file/string.

Important note:
- If you only have local Claude OAuth / keychain auth, that works for normal interactive Claude Code, but **not** for the clean benchmark path.
- Anthropic documents that `--bare` does not read OAuth or keychain auth.
- So OAuth-only Claude runs should be treated as convenience/dev runs, not as the strict benchmark condition.

```bash
uv run cbench run claude-code \
  --tasks data/benchmarks/ruler_1m.jsonl \
  --model claude-sonnet-4-6 \
  --condition auto \
  --chunk-tokens 4000
```

### 6. Run Codex

```bash
uv run cbench run codex \
  --tasks data/benchmarks/ruler_1m.jsonl \
  --model gpt-5.4 \
  --condition auto \
  --chunk-tokens 4000 \
  --reasoning-effort high
```

### 7. Score and report

```bash
uv run cbench score --runs artifacts/runs_direct --out artifacts/results
uv run cbench report --results artifacts/results
```

### 8. Run a reviewed batch spec

BABILong parallel batch:

```bash
uv run python scripts/run_babilong_codex_parallel.py \
  --spec specs/babilong_codex_auto_high_models.yaml
```

OOLONG-synth parallel batch:

```bash
uv run python scripts/run_babilong_codex_parallel.py \
  --spec specs/oolong_synth_codex_auto_high_models.yaml
```

## Layout

```text
compactionbench/
  schema.py      # Pydantic task/run models
  chunking.py    # context chunking
  loaders.py     # RULER + BABILong + OOLONG converters
  run.py         # Claude Code + Codex direct runners
  score.py       # scoring and summary
  cli.py         # Typer CLI
specs/
  simple_long_context_experiment.md
tests/
  fixtures/
docs/
  results_so_far.md
```

## Status

The repo is now centered on the direct multi-turn experiment path. Older file-fixture experiments are intentionally not part of the active workflow anymore.

Useful docs in this repo:
- `docs/results_so_far.md` — short summary of completed runs and main findings
- `plan.md` — advisor-facing benchmark and motivation note
- `exploration_sprint.md` — next curiosity-driven sprint idea
