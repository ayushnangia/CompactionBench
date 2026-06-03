# Generic bidirectional proof memory canary

Date: 2026-06-03

## Rule

No benchmark-specific semantic hardcoding.

The new arm does not contain hardcoded categories like BABILong locations, OOLONG rolls/spells, dinner/preference/project state, etc. It only hardcodes the generic protocol:

1. induce a task-local query contract,
2. search raw `context.txt`,
3. discover evidence handles from the context,
4. write a cited `proof_packet.json`,
5. return the final `{"answer": "..."}`.

## Implemented arm

Runner arm:

- `bidirectional_proof`

Files changed:

- `scripts/run_lossless_vs_grep_codex_parallel.py`
- `scripts/analyze_lossless_vs_grep.py`
- `tests/test_bidirectional_proof_runner.py`

The arm writes/reads:

- `context.txt`
- `proof_packet.json`
- optional `proof_packet.md`

The metadata reader validates citations generically by checking whether source quotes appear in the raw context. It does not interpret domain semantics.

## OOLONG canary

Panel:

- `data/benchmarks/generic_bidirectional_oolong_canary_6.jsonl`
- 6 tasks: OOLONG synthetic counting/timeline/user + OOLONG-real rolls/spells.

Run:

- `artifacts/batches/generic_bidirectional_oolong_canary_18`
- 18/18 jobs completed, 0 errors.

Analysis:

- `artifacts/analysis/generic_bidirectional_oolong_canary_18/report.md`

| Arm | Strict | Notes |
|---|---:|---|
| `bidirectional_proof` | 3/6 | solved synthetic aggregate tasks; failed real rolls/spells |
| `grep_file` | 2/6 | solved synthetic timeline/user only |
| `virtual_context` | 1/6 | solved synthetic counting only |

## Cross-benchmark canary

Panel:

- `data/benchmarks/generic_bidirectional_cross_benchmark_canary_9.jsonl`
- 9 tasks across OOLONG, BABILong, synthetic, LME, and SWE-chat.

Run:

- `artifacts/batches/generic_bidirectional_cross_benchmark_canary_18`
- 18/18 jobs completed, 0 errors.

Analysis:

- `artifacts/analysis/generic_bidirectional_cross_benchmark_canary_18/report.md`

| Arm | Strict | Relaxed |
|---|---:|---:|
| `bidirectional_proof` | 2/9 | 4/9 |
| `grep_file` | 3/9 | 5/9 |

## Interpretation

This is the honest outcome: removing semantic hardcoding makes the method scientifically cleaner but much harder.

The generic proof arm can induce useful schema for some synthetic aggregate tasks, but it is not yet strong enough for:

- OOLONG-real cumulative roll/spell counting,
- LME UI/procedure questions,
- SWE-chat review tasks.

This is a useful negative/diagnostic result. It says the next step is not to add benchmark categories back in, but to improve the generic protocol:

- better decomposition into subqueries,
- stronger deterministic quote validation,
- proof repair loops,
- explicit contradiction/refutation checks,
- maybe multiple independent proof attempts with consensus.

## Current caveat

This arm is generic but model-call heavy. It uses tools and averages ~5 tool calls/run in these canaries. It should not be compared as a cheap no-tool memory packet yet.
