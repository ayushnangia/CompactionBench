# Virtual Context Memory

This is the proper OS-style version of the paging idea.

The key change:

> The model does **not** manage pages. The system does.

The earlier `paged_context` arm was useful, but it was manual: the model saw `pager.py`, chose search terms, loaded pages, and then answered. That is not how OS paging works. In an operating system, the program just reads memory; the kernel handles page tables, page faults, loading, and eviction.

`virtual_context` is the transparent/system-managed version.

## Architecture

```text
long source text
  ↓
system splits source into pages
  ↓
system builds hidden page table
  ↓
system memory kernel retrieves a resident working set
  ↓
model receives evidence packet only
  ↓
model answers without tools
```

## Experiment arms

| Arm | Who manages memory? | What the model sees |
|---|---|---|
| `full_context` | nobody; everything is pasted | full source in prompt |
| `grep_file` | model/tool loop | one file and permission to grep |
| `paged_context` | model-managed paging | `memory/pager.py` and page table |
| `virtual_context` | system-managed paging | evidence packet only |

## OS analogy

| OS paging concept | Virtual Context Memory |
|---|---|
| disk | original source text |
| page files | fixed-size source pages |
| page table | hidden page index maintained by harness |
| resident set | evidence packet placed in model prompt |
| kernel | retrieval code in `compactionbench/virtual_context.py` |
| page fault handler | future verifier/retry loop |
| program | the model answering the question |

## What was implemented

### Core module

`compactionbench/virtual_context.py`

Main API:

```python
memory = write_paged_memory(source, tmp / "virtual_memory", write_tool=False)
packet = build_virtual_context_packet(
    memory,
    question,
    source_benchmark="babilong",
    source_task="qa1",
)
prompt = build_virtual_context_prompt(
    question,
    packet=packet,
    source_benchmark="babilong",
    source_task="qa1",
)
```

### Runner support

`scripts/run/run_lossless_vs_grep_codex_parallel.py` now accepts:

```bash
--arm virtual_context
```

This creates a hidden paged memory directory, builds an evidence packet, and prompts Codex without page-tool instructions.

### Metadata recorded

Each run stores:

```json
"metadata": {
  "arm": "virtual_context",
  "virtual_context": {
    "strategy": "transparent_virtual_context+...",
    "budget_tokens": 24000,
    "source_tokens_est": 132280,
    "page_count": 167,
    "evidence_tokens_est": 183,
    "selected_page_ids": [77],
    "item_count": 1,
    "items": [...]
  }
}
```

So we can audit what the memory kernel loaded.

## Retrieval strategies

### BABILong

The kernel extracts a concise chronological event trace from the original source.

It looks for BABI-style facts such as:

```text
Mary journeyed to the bathroom.
John picked up the football.
Fred gave the apple to Bill.
The bedroom is north of the garden.
```

It avoids unrelated carrier-novel text such as:

```text
Mary Linden went to Didlum's shop.
```

That carrier text caused failures in the manual paging version.

### OOLONG-real

The kernel retrieves transcript windows around roll/spell/question terms, e.g.:

```text
roll, rolled, natural, crit, attack, save
cast, casts, spell, cantrip, level
```

This is still retrieval, not an oracle. It does not use the gold answer.

## Smoke test

Run:

`artifacts/batches/_smoke_virtual_context`

Task:

```text
Question: Where is Mary?
Gold: bathroom
```

Virtual-context answer:

```text
the bathroom
```

Results:

- parse ok: yes
- tools used: 0
- compactions: 0
- strict score: wrong because of `the bathroom` vs `bathroom`
- relaxed/human score: correct

This confirms the key property: the model did not call a pager or search tool; the system loaded evidence first.

## Next proper experiment

Run a 4-arm real-data experiment:

```bash
uv run python scripts/run/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/real_lossless_250.jsonl \
  --root-dir artifacts/batches/real_virtual_context_1000/$(date +%Y%m%d-%H%M%S) \
  --arm full_context \
  --arm grep_file \
  --arm paged_context \
  --arm virtual_context \
  --model gpt-5.4-mini \
  --reasoning-effort low \
  --verbosity low \
  --timeout-s 420 \
  --max-workers 8
```

That gives:

- 250 real tasks
- 4 arms
- 1000 runs

## Important caveat

This is not yet a full OS implementation. The next missing piece is a verifier-driven page-fault loop:

```text
model answers from resident evidence
  ↓
verifier checks support
  ↓
if evidence is insufficient, kernel retrieves more pages
  ↓
model retries
```

But it is already the important architectural step: **the system now manages paging, not the model**.
