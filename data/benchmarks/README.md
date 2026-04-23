# Benchmark data notes

This directory is for prepared direct-task JSONL files used by the active benchmark path.

## BABILong standard

Use these defaults unless there is a specific reason not to:

- dataset: `RMT-team/babilong`
- config: `1M`
- initial task set: `qa1` to `qa5`

Important:
- `RMT-team/babilong-1k-samples` is useful for smaller-scale experiments, but it does **not** provide `1M` splits.
- `qa8` is a set-valued task and should not be scored with plain exact string match; the active scorer for it is `csv_set_ci`.

## OOLONG

The active OOLONG path now supports:

- `oolongbench/oolong-synth`
- `oolongbench/oolong-real`

Useful notes:
- `OOLONG-synth` rows already separate `context_window_text` from `question`; the direct-task format stores them as `context` + `question` again.
- `OOLONG-synth` uses task-group labels such as `counting`, `user`, and `timeline`.
- `OOLONG-real` mixes numeric, string, and comma-separated list answers; the direct scorer setup preserves the benchmark's partial-credit numeric and list-overlap behavior.

## File convention

Examples:
- `ruler_1m_niah_single_1.jsonl`
- `babilong_qa1_1m.jsonl`
- `babilong_qa5_1m.jsonl`
- `oolong_synth_counting_128k_000.jsonl`
- `oolong_synth_timeline_1M_002.jsonl`
