# ContinualBENCH: A Unified Benchmark for Updating LLMs Over Time

Date: February 24, 2026  
Target venue (tentative): NeurIPS Datasets & Benchmarks

## Summary (what we will build)

LLMs become outdated. Updating them introduces three coupled failure modes:

1. **Adaptation**: learn new facts from new data.
2. **Forgetting**: avoid losing older still-true knowledge.
3. **Temporal connectivity**: retain the ability to *use updated facts inside multi-step reasoning chains* with older stable facts.

**Today there is no single benchmark that measures all three together under a strict time-ordered, no-leakage protocol.** We will build one: **ContinualBENCH**.

## Datasets (what we use and why)

We will be explicit about which resources are for *training streams* vs *evaluation*.

### Training corpus (time-ordered stream)

- **Infini-News / CC-News-style news corpus (chronological)**: used to create monthly buckets `D_t` for continual updating, and to build timestamped retrieval indexes `I_<=t` for retrieval baselines.  
  - Dataset/index entry point: https://huggingface.co/datasets/ruggsea/infini-news-index

### Our released benchmark dataset (evaluation)

- **ContinualBENCH (this work)**: a timestamped QA benchmark built from the time-ordered corpus with strict no-leakage rules, split into three task families:
  - Freshness QA (adaptation)
  - Retention QA (forgetting)
  - Multi-hop Temporal QA (temporal connectivity)

Each item includes `query_time` and timestamped evidence passages (doc IDs + dates), enabling both parametric and retrieval-based evaluation.

### External evaluation anchors (existing public datasets)

These are not replacements for ContinualBENCH; they are anchors to make results comparable to prior work:

- **FreshQA / FreshLLMs**: measures knowledge freshness (recent facts).  
  - https://arxiv.org/abs/2310.03214
- **SealQA**: evaluates robustness of retrieval + QA under noisy retrieval settings.  
  - https://arxiv.org/abs/2506.01062
- **PAT-Questions**: present-anchored temporal QA benchmark designed to self-update over time.  
  - https://aclanthology.org/2024.findings-acl.777/
- **TimeBench**: comprehensive evaluation of temporal reasoning abilities in LLMs.  
  - https://aclanthology.org/2024.acl-long.66/

## Core research question

**Can we measure, in one benchmark and one protocol, how well an LLM update strategy achieves adaptation without forgetting while preserving temporal multi-hop reasoning?**

Secondary (practical) question:

**Which update strategy works best: weight updates (continual learning), retrieval-only updates (temporal RAG), or a hybrid of both?**

## Why this is new / useful

Existing evaluation is fragmented:

- “Freshness” benchmarks test whether the model knows recent facts (adaptation) but typically do not measure forgetting or temporal multi-hop reasoning in the same setting.
- Continual-learning papers often measure average task accuracy / forgetting but do not explicitly test whether updated facts remain usable in multi-hop reasoning chains over time.

**ContinualBENCH’s contribution is the *unified* evaluation protocol and dataset design** that ties all three together with timestamped evidence and strict chronological constraints.

## Benchmark design (high level)

### Data

- A time-ordered news corpus split into **monthly buckets**.
- Strict **no-future leakage**: at month `t`, training and retrieval can only use documents with timestamps `<= end_of_month(t)`.

We represent the stream as:

- `D_t`: documents arriving in month `t` (training bucket).
- `R_<t`: optional replay reservoir sampled only from months `< t`.
- `I_<=t`: retrieval index built only from documents `<= t`.

### Tasks: three families (one benchmark, three slices)

We evaluate at each month checkpoint `t` on:

1. **Freshness QA (Adaptation)**  
Single-hop questions whose answers changed recently, e.g. “Who is the CEO of X (as of {t})?”
2. **Retention QA (Forgetting)**  
Single-hop questions about facts introduced earlier that remain valid at `t`.
3. **Multi-hop Temporal QA (Temporal Connectivity)**  
Questions that require chaining an updated fact with a stable one, e.g.  
“The new CEO of X used to work at Y. What does Y make?”

Each QA item includes **timestamped evidence passages** (with doc IDs + dates) so correctness is verifiable and to support retrieval-based baselines.

### What we release

- `benchmark_v1_dev.jsonl` / `benchmark_v1_test.jsonl` with:
  - `query_time` timestamp
  - answer + aliases
  - evidence doc IDs/snippets with timestamps
  - event IDs so dev/test are disjoint by underlying fact-change event
- Code to reproduce:
  - corpus filtering + dedup
  - benchmark generation + leakage checks
  - training/update loops and retrieval baselines
  - scoring scripts

## Methods we will benchmark (initial baselines)

We will include baselines that reflect what people actually do:

1. **Static LM**: no updates.
2. **Continual update (LoRA) without replay**: update monthly on `D_t`.
3. **Continual update (LoRA) with replay**: update monthly on `D_t + replay(R_<t)`.
4. **Temporal RAG**: no weight updates; answer using retrieval over `I_<=t`.
5. **Hybrid**: continual update + temporal retrieval.

We will keep training budgets fixed per month (same steps/tokens) to make comparisons meaningful.

## Metrics (simple, aligned to the 3 goals)

At each checkpoint `t`:

1. **AdaptAcc**: accuracy on Freshness QA.
2. **RetainAcc**: accuracy on Retention QA.
3. **ConnectAcc**: accuracy on Multi-hop Temporal QA.

We will also report:

- **Forgetting**: drop in RetainAcc relative to earlier checkpoints.
- Slice breakdowns by time-lag and by relation type (CEO changes, acquisitions, event winners, etc.).

## External benchmarks (for anchoring, not replacing our benchmark)

We will report results on established datasets to make comparisons legible:

- FreshQA / FreshLLMs (freshness)
- SealQA (retrieval and robustness under noise)
- PAT-Questions (temporal QA anchored to the present)
- TimeBench (temporal reasoning coverage)

ContinualBENCH is the *unified* benchmark; these are sanity anchors.

## Concrete MVP (first 2 weeks)

To avoid vagueness, we freeze an MVP:

- 6 months stream (2021-01 to 2021-06), English only.
- 300 QA items total across months and task families.
- 4–5 baselines above (starting with 0.6B model).
- Strict leakage checks and fully reproducible scripts.

Success criterion for MVP: the benchmark produces clear, non-trivial separation between at least two baseline families on at least one of the three metrics (AdaptAcc/RetainAcc/ConnectAcc).

## Timeline (4 weeks to first submission-quality artifact)

Week 1:

- Finalize schema + leakage checks.
- Build candidate pool and validate 300-item v1 benchmark.

Week 2:

- Implement/update baselines and run first full benchmark.
- Write initial analysis and error taxonomy.

Week 3:

- Scale benchmark size and diversity (more change events; more multi-hop).
- Add stronger baselines if needed (different replay policies, better retrieval chunking).

Week 4:

- Package dataset (hosting + documentation + metadata).
- Polish paper draft and release repository.

## Risks and mitigations

- **Ambiguous facts in news**: require multiple evidence sources or drop items.
- **Leakage via retrieval**: timestamp-filter every passage; enforce `I_<=t`.
- **Benchmark too easy**: increase multi-hop depth and contradiction-heavy revision cases.
- **Benchmark too hard/noisy**: increase evidence quality gates and simplify relation types.

## What I need from you (advisor)

1. Confirm target venue: NeurIPS Datasets & Benchmarks vs NLP venue.
2. Confirm whether we should optimize for (a) benchmark artifact first or (b) method contribution.
3. Confirm acceptable annotation effort for v1 (e.g., 300 items with double-validation).

## References (starting point)

- FreshQA / FreshLLMs: https://arxiv.org/abs/2310.03214  
- SealQA: https://arxiv.org/abs/2506.01062  
- PAT-Questions: https://aclanthology.org/2024.findings-acl.777/  
- TimeBench: https://aclanthology.org/2024.acl-long.66/  
- TiC-LM (time-continual pretraining benchmark): https://aclanthology.org/2025.acl-long.1551/
