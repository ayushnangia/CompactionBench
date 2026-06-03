# Infinite-context paging prototype

This is the next experiment direction: instead of asking whether a giant prompt or grep is better, we build a memory system that behaves more like **infinite context with paging**.

## Plain-English idea

A model has a limited context window. Treat that window like RAM.

The original source text lives outside the model as page files. Treat those files like disk.

When the model needs evidence, it searches the page table and loads only the pages it needs.

```text
Long source text
  -> split into stable pages
  -> build page table + search tool
  -> prompt starts with small working set
  -> agent searches/loads more pages as needed
  -> final answer comes from loaded evidence
```

## Update: transparent virtual context added

A second, more OS-like arm now exists:

```text
virtual_context
```

Unlike `paged_context`, the model does **not** see `pager.py` or decide which pages to load. The harness builds a hidden page table, selects a resident evidence packet, and gives the model that packet directly.

See: `docs/virtual_context_memory.md`

## What was implemented first

### Core module

`compactionbench/paged_context.py`

It writes a deterministic paged memory directory:

```text
memory/
  manifest.json
  page_index.jsonl
  page_table.md
  pager.py
  pages/
    page_000001.txt
    page_000002.txt
    ...
```

The original source is not summarized or deleted. It is split into page files with overlap.

### Pager commands

Inside a run workspace, the agent can call:

```bash
python memory/pager.py stats
python memory/pager.py search "Where is Mary" --top-k 8
python memory/pager.py grep "exact phrase" --ignore-case --context 2
python memory/pager.py show 51 --radius 1
python memory/pager.py table --limit 80
```

### New experiment arm

`scripts/run/run_lossless_vs_grep_codex_parallel.py` now supports:

- `full_context`
- `grep_file`
- `paged_context`
- `virtual_context`

The first paging arm stores the source as pages and gives Codex the pager tool instead of one giant prompt or one monolithic `full_context.txt`.

The newer `virtual_context` arm stores the source as hidden pages, retrieves evidence before the model call, and prompts the model with only the resident evidence packet.

### Question-aware prefetch

The paged prompt includes a small **initial working set**: candidate pages selected from the question only.

This is like an OS prefetching likely pages before the process asks for them.

It is not a summary and it does not use the gold answer.

## Why this is better than plain grep

Plain grep gives the model raw string matching.

Paged context gives the model:

1. a page table,
2. exact search,
3. page loading,
4. nearby-page loading,
5. a small question-aware starting cache,
6. task hints that prevent obvious dataset ambiguities.

## Why this is better than compaction

Compaction changes or deletes information.

Paging keeps the original source intact and recoverable.

The model can forget what is in RAM, but the original page is still on disk.

## Fair experiment design

Use real datasets only:

- BABILong
- OOLONG-real
- LongMemEval rendered
- SWE-chat

Compare arms:

| Arm | What it tests |
|---|---|
| `full_context` | all source placed directly in the prompt |
| `grep_file` | source saved as one searchable file |
| `paged_context` | model-visible pages and pager tool |
| `virtual_context` | system-managed hidden paging; model sees evidence packet only |
| compacted agent memory | source injected over many turns and allowed to compact |

Important labels:

- BABILong/OOLONG 500-run control: non-compacted/lossless full context.
- LME rendered: rendered/clipped browser trajectories, not raw lossless JSON.
- SWE-chat: requires semantic/judge scoring, not exact substring scoring.

## Smoke test result

A one-task BABILong paged-context smoke run succeeded mechanically:

- run root: `artifacts/batches/_smoke_paged_context5`
- task: `babilong-qa1-128k-0`
- question: `Where is Mary?`
- gold: `bathroom`
- paged answer: `the bathroom`
- strict scorer: false because of article `the`
- human/normalized read: correct

This reinforces that the next proper experiment should include normalized scoring for BABILong short answers.

## Recommended next batch

A practical first full pager experiment:

```bash
uv run python scripts/run/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/real_lossless_250.jsonl \
  --root-dir artifacts/batches/real_paged_context_750/$(date +%Y%m%d-%H%M%S) \
  --arm full_context \
  --arm grep_file \
  --arm paged_context \
  --model gpt-5.4-mini \
  --reasoning-effort low \
  --verbosity low \
  --timeout-s 420 \
  --max-workers 8
```

That gives:

- 250 real BABILong/OOLONG tasks
- 3 arms
- 750 runs
- no synthetic data

Then repeat on:

```bash
data/benchmarks/confirmation/swe_lme_real_125.jsonl
```

for 375 more runs, with judge/semantic scoring for SWE-chat.

## Research framing

The claim should be:

> Long-running agents should not depend on remembering everything in chat. They should keep original sources in paged external memory and load evidence on demand.

Not:

> Grep beats full context.

The pager lets us test a more realistic system design: **searchable original memory + small working context + page loading**.

The newer `virtual_context` arm is closer to the OS analogy: **hidden page table + system-selected resident working set + no model-managed page commands**.
