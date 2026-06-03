# Hierarchical memory execution summary

Date: 2026-06-02

## What we built

Implemented and pushed a deterministic hierarchy-memory evaluation path:

- synthetic age-aware memory generator
- hierarchy packets with L0/L1/L2/L3 evidence
- flat raw memory packet baseline
- oracle memory evidence arm
- configurable hierarchy/flat packet budgets
- query-type and evidence-token analysis
- BABILong state-table hierarchy arm

Main code paths:

- `compactionbench/taskgen/hierarchical.py`
- `compactionbench/memory/hierarchical_memory.py`
- `compactionbench/memory/babilong_hierarchy.py`
- `scripts/prepare/prepare_hierarchical_memory_tasks.py`
- `scripts/run/run_lossless_vs_grep_codex_parallel.py`
- `scripts/analyze/analyze_lossless_vs_grep.py`

## Main results

### 1. Simple lookup/stale-update synthetic panel

On a 90-task synthetic panel, grep and flat retrieval were very strong. The only grep gap was mostly strict formatting for abstention/no-record answers.

Takeaway: do not claim hierarchy beats grep on simple lookup. Grep is hard to beat when the answer is findable in raw text.

### 2. Synthetic budget-pressure aggregate panel

Aggregate tasks: `dinner_count` and `least_common_dinner` across 10 streams with 180 days of memory.

| Arm | Strict | Avg evidence |
|---|---:|---:|
| flat raw packet | 3–5/20 across budgets | ~223–940 tok |
| virtual context | 14/20 | ~9.1k tok |
| hierarchy packet | 20/20 | ~142 tok |

Takeaway: hierarchy starts to matter when the answer is compact derived state over many raw events, not a single retrievable line.

### 3. Mixed synthetic budget-pressure panel

55 tasks across exact recall, current/stale facts, aggregate counts, least-common aggregate, and abstention.

| Arm | Strict | Relaxed | Avg evidence/duration |
|---|---:|---:|---:|
| grep_file | 50/55 | 55/55 | tools, 12.6s |
| flat raw packet | 47/55 | 47/55 | ~602 tok, 6.8s |
| virtual context | 44/55 | 44/55 | ~8.4k tok, 10.9s |
| hierarchy packet | 55/55 | 55/55 | ~232 tok, 6.2s |

Takeaway: hierarchy is best among tool-free packet arms; grep remains semantically strong when allowed tools.

### 4. BABILong state-table hierarchy

Implemented `babilong_state_packet`: extract BABI-style events, drop carrier-prose false matches, consolidate current state, and answer from a compact state packet.

All-length qa11–qa14 panel: 48 tasks = qa11–qa14 × 3 samples × 128k/256k/512k/1M.

| Arm | Strict | Relaxed | Avg evidence/duration |
|---|---:|---:|---:|
| babilong_state_packet | 48/48 | 48/48 | ~208 tok, 6.2s |
| grep_file | 12/48 | 47/48 | tools, 11.8s |
| virtual_context | 7/48 | 18/48 | ~279 tok, 11.7s |

Takeaway: BABILong validates the task-specific memory-operator hypothesis. Generic evidence windows are not enough; explicit state extraction is the clean win.

## Caveats

- Synthetic wins are controlled canaries, not broad external validation.
- BABILong result currently covers qa11–qa14 movement/coreference/time reasoning only.
- Grep often answers semantically correctly under relaxed scoring; strict-score gaps partly reflect answer formatting.
- PEEK-style context map was only canaried; full PEEK comparison should wait for a repeated-context setup that is actually accuracy-separating.

## Best framing

Do not frame this as “hierarchy beats grep everywhere.” The defensible claim is narrower:

> Grep/flat retrieval is excellent for single-fact lookup. Hierarchical memory helps when the useful answer is a compact maintained state — counts, current state, or derived transitions — that would require reading too many raw events under a fixed packet budget.

## Shareable one-liners

Synthetic budget pressure:

> On aggregate memory under an equal packet budget, hierarchy separated cleanly: flat raw retrieval got 3–5/20, virtual context got 14/20 with ~9k evidence tokens, and the hierarchy packet got 20/20 with ~142 tokens by carrying consolidated L2 state.

BABILong:

> On BABILong qa11–qa14 across 128k–1M contexts, a deterministic state-table hierarchy got 48/48 strict with a ~208-token packet and no tools. Generic virtual context got 7/48 strict, while grep was mostly semantically right under relaxed scoring but only 12/48 strict and slower.

## Pushed commits

- `b70b371` — synthetic hierarchy benchmark and budget-pressure results
- `f2aea4a` — BABILong state-table hierarchy canary
- `b720842` — scaled BABILong canary results
- `288d0dd` / `589cb6a` — all-length BABILong result notes

Latest relevant summary docs:

- `archive/work/hierarchical_memory_execution_log_2026-06-02.md`
- `archive/work/hierarchical_memory_budget_pressure_share_2026-06-02.md`
- `archive/work/babilong_state_hierarchy_share_2026-06-02.md`
- `docs/current/hierarchical_memory_final_summary_2026-06-02.md`
