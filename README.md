# CompactionBench

A benchmark that measures what AI agents forget when their context gets compressed.

## What this is

When an AI coding agent works on a long task, the conversation grows. Eventually it exceeds the context window and the system compresses (compacts) the history to keep going. CompactionBench asks: **what gets lost?**

## Key findings

1. **Compaction selectively destroys exact facts.** Names, numbers, places, and bindings disappear faster than big-picture understanding.

2. **The Retention-Accuracy Gap.** A diagnostic metric: for exact-fact questions, the answer is in context 46% of the time but the model only gets it right 8% of the time. For aggregation questions, the model uses nearly everything it has (8pt gap vs 37pt gap).

3. **Compression needs to know what matters.** Query-blind compression fails completely (0/5). Query-aware compression matches raw performance (3/5). A weak task-type hint nearly matches full question awareness.

4. **A smarter model cannot recover deleted information.** GPT-5.4 counts perfectly with full context (5/5). After compression: 0/5.

## How it works

```text
JSONL task → inject long context into Codex → auto-compaction → ask question → score answer
```

Benchmarks supported: BABILong (exact fact retrieval), OOLONG (aggregation), RULER, LongBench v2, plus synthetic generators and SWE-chat integration.

## Quick start

```bash
git clone https://github.com/ayushnangia/CompactionBench.git
cd CompactionBench
uv sync

# Generate synthetic tasks
uv run cbench prepare synth --count 5 --filler-sentences 8000

# Compress tasks
uv run cbench compress --tasks data/benchmarks/synthetic_tasks.jsonl --policy entropy --budget-tokens 200

# Run with Codex
uv run cbench run codex --tasks data/benchmarks/synthetic_tasks.jsonl --model gpt-5.4-mini --condition auto

# Score results
uv run cbench score --runs artifacts/runs_direct
```

## Docs

- `RESULTS.md` — overall results
- `hypotheses.md` — testable hypotheses
- `paper_ideas.md` — candidate paper metrics
- `SESSION_LOG.md` — full session log
- `docs/` — HTML experiment visualizations

## Requirements

- Python 3.11+
- Codex CLI (for running experiments)
- HuggingFace token (for SWE-chat integration)

## License

MIT
