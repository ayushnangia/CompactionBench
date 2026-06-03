# CompactionBench

CompactionBench studies what AI agents lose when long chat history is compressed.

The short version:

- Exact details are fragile: names, numbers, places, current values, and counts.
- Broad patterns survive better.
- If compression deletes the needed detail, a smarter model usually cannot recover it.
- Search helps with literal lookup, but not with every task.
- Task-specific memory operators help when the answer is a maintained state, not one line in a file.

For the current consolidated readout, start here:

- [CONSOLIDATED.md](CONSOLIDATED.md) - plain-language project summary
- [RESULTS.md](RESULTS.md) - main numeric result
- [docs/README.md](docs/README.md) - docs index

## Current Status

The strongest result is the retention-vs-answer gap:

| Task family | Answer still visible | Correct answer | Gap |
|---|---:|---:|---:|
| BABILong qa1-10 | 45.8% | 8.3% | 37.5 points |
| BABILong qa11-20 | 41.9% | 14.7% | 27.2 points |
| OOLONG-synth | 54.6% | 46.3% | 8.3 points |

Plain meaning: for exact-memory tasks, the answer can still be present but the agent often fails to use it. For aggregation tasks, when the useful information survives, the agent uses it more often.

## What Is In This Repo

- `compactionbench/`: library code grouped by role
  - `core/`: schemas, scoring, judging, token utilities
  - `datasets/`: benchmark loaders
  - `memory/`: compression, paging, virtual context, hierarchy methods
  - `runners/`: Codex/Claude runner code
  - `taskgen/`: synthetic task generators
- `scripts/`: batch workflows grouped into `prepare/`, `run/`, `analyze/`, and `report/`
- `tests/`: test suite
- `data/benchmarks/`: prepared benchmark task files
- `artifacts/`: raw runs and analysis outputs
- `docs/current/`: current supporting reports
- `archive/`: older notes, drafts, unrelated handoffs, and superseded reports

## Setup

```bash
uv sync
uv run pytest
```

## Run A Small Example

```bash
uv run cbench run codex \
  --tasks data/benchmarks/confirmation/balanced_context_100.jsonl \
  --model gpt-5.4-mini \
  --condition auto
```

Most large runs require Codex CLI access and model credentials. See `docs/current/experiment_run_policy.md` when running new batches.
