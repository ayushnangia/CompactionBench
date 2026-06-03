# RLM/RM3 virtual context arm

This adds a classical IR-style relevance language model variant to the virtual-context story.

## What RLM means here

RLM = **Relevance Language Model**, specifically an RM3-style pseudo-relevance-feedback retriever.

It is not another answer-generating LLM. It is a system-side retrieval model:

```text
question
  -> initial lexical retrieval over source pages
  -> estimate expansion terms from top pages
  -> retrieve pages again with expanded query
  -> build resident evidence packet
  -> model answers with tools disabled
```

## Why try it

This is a more research-standard retrieval baseline than hand-written task extractors.

It asks:

> Can a generic relevance-model retriever serve as the memory kernel, without BABILong/OOLONG-specific rules?

## How it differs from other arms

| Arm | Retrieval manager | Retrieval style |
|---|---|---|
| `grep_file` | model | manual shell search over one file |
| `paged_context` | model | manual page search/load |
| `virtual_context_24k` | system | typed/task-aware evidence extraction |
| `virtual_context_rlm` | system | generic RLM/RM3 pseudo-relevance feedback |

## Expected behavior

- May help OOLONG-ish lexical matching because query expansion can find related roll/spell terms.
- May be worse than typed virtual context on BABILong because pseudo-relevance feedback can expand around carrier-prose distractors.
- Useful as a reviewer-friendly IR baseline.

## Current implementation

- Code: `compactionbench/virtual_context.py`
- Runner arm: `virtual_context_rlm`
- Uses hidden pages and zero model tools.
- Stores metadata under `metadata.virtual_context.strategy = transparent_virtual_context+rlm_rm3`.

## Run policy

Do not rerun baselines. Run only `virtual_context_rlm`, then merge with existing fixed-panel baselines in analysis.
