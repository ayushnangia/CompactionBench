<p align="center">
  <img src="https://img.shields.io/badge/experiments-648-blue" alt="experiments">
  <img src="https://img.shields.io/badge/models-gpt--5.4%20%7C%20gpt--5.4--mini%20%7C%20gpt--5.3--codex-green" alt="models">
  <img src="https://img.shields.io/badge/benchmarks-BABILong%20%7C%20OOLONG%20%7C%20SWE--chat-orange" alt="benchmarks">
  <img src="https://img.shields.io/badge/tests-50%20passing-brightgreen" alt="tests">
</p>

# CompactionBench

**A diagnostic benchmark for long-context agent memory.** Measures what AI agents forget when their conversation history gets compressed, and why.

---

## The problem

When an AI coding agent runs for hundreds of messages, the context window fills up. The system compresses (compacts) the history to keep going — dropping tokens, summarizing turns, condensing context. But what gets lost?

CompactionBench answers this with controlled experiments: inject long context, trigger compaction, ask questions, and measure what survived.

## Key findings

| # | Finding | Evidence |
|---|---:|---|
| 1 | **Exact facts disappear first.** Names, numbers, places, and bindings degrade faster than big-picture understanding. | BABILong: 37pt retention-accuracy gap vs OOLONG: 8pt gap |
| 2 | **Compression needs a goal.** Without knowing the question, compression keeps the wrong facts (0/5). With the question, it matches raw performance (3/5). | 5-task BABILong transfer, gpt-5.4-mini + gpt-5.4 |
| 3 | **Task type determines compression effect.** Stale-update: helps (100%). Counting: destroys (5/5→0/5). Entity binding: neutral (20%). | 15 synthetic tasks, 5 compression conditions |
| 4 | **A smarter model cannot recover what was deleted.** GPT-5.4 counts perfectly with full context. After compression: 0/5. | 158k token context, counting task |

## How it works

```
JSONL task row → inject long context into Codex → auto-compaction kicks in → ask final question → score answer → diagnose failure
```

1. **Prepare:** Generate or load a task (long context + question + gold answer)
2. **Compress:** Optionally apply an explicit compression policy (entropy, static, LLMLingua, weak-hint)
3. **Run:** Inject chunks into a live Codex session. Compaction events are logged.
4. **Score:** Deterministic exact/substring/aggregation scoring + optional LLM judge
5. **Diagnose:** Retention metric, failure taxonomy, compaction event analysis

## Quick start

```bash
git clone https://github.com/ayushnangia/CompactionBench.git
cd CompactionBench
uv sync

# Generate 15 synthetic tasks at ~158k tokens each
uv run cbench prepare synth --count 5 --filler-sentences 8000

# Compress with entropy (query-aware)
uv run cbench compress --tasks data/benchmarks/synthetic_tasks.jsonl \
  --policy entropy --budget-tokens 200 --query-aware

# Run with Codex
uv run cbench run codex --tasks data/benchmarks/synthetic_tasks.jsonl \
  --model gpt-5.4-mini --condition auto --chunk-tokens 16000

# Score
uv run cbench score --runs artifacts/runs_direct
```

## Benchmarks

| Benchmark | What it tests | Context length |
|---|---|---|
| BABILong | Exact fact retrieval (Who? Where? What object?) | 128k – 10M tokens |
| OOLONG-synth | Aggregation over many local decisions | 128k – 1M tokens |
| OOLONG-real | Real D&D transcript reasoning | 3ep – 16ep |
| Synthetic | Stale-update, entity binding, counting | Configurable |
| SWE-chat | Real coding agent conversations | Padded to 160k+ tokens |

## Repository structure

```
compactionbench/     # Core library
  schema.py          # TaskRow, RunRecord, scoring models
  run.py             # Codex and Claude Code runners
  score.py           # Deterministic scorers
  judge.py           # LLM-as-judge pass
  loaders.py         # BABILong, OOLONG, RULER loaders
  compression.py     # Offline entropy/static compression
  tasks.py           # Synthetic task generators
  swe_chat_loader.py # SWE-chat integration
  cli.py             # cbench CLI

scripts/             # Batch runners, analysis
specs/               # Experiment YAML specs
docs/                # HTML experiment visualizations
tests/               # 50 tests
```

## Requirements

- Python 3.11+
- [Codex CLI](https://github.com/openai/codex) (for running experiments)
- HuggingFace token (for SWE-chat and BABILong/OOLONG datasets)
- `uv` for dependency management

## Install

```bash
uv sync
uv run pytest  # 50 tests should pass
```

## License

MIT
