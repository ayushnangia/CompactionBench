# Exploration Sprint: Can optimized compression beat default compaction?

> **Status:** Exploration Sprint, not a final Research Question yet.  
> **Purpose:** Decide whether there is a surprising, useful signal worth sharpening into a research question.

---

## One-line summary

I want to test whether long-context failures in agent runs are partly caused by **bad compaction/compression**, and whether simple or optimized compression policies can preserve answer-critical information better than default auto-compaction.

This is **not yet** a full project claim. It is a short scout mission.

---

## Why this is an Exploration Sprint, not a Research Question yet

Right now we do not know whether there is a real effect.

The current benchmark results show that long-context agent performance degrades under compaction, especially on exact memory and symbolic binding tasks. But those results do not yet tell us whether the problem is:

1. the model cannot reason over long context,
2. the model loses exact facts during native compaction,
3. the context contains too much irrelevant information,
4. the compression format preserves gist but loses state,
5. or our benchmark/scoring setup is too harsh.

So the exploration is:

> If we replace or augment default compaction with explicit compression policies, do results change in a clear way?

If yes, then we can sharpen into a Research Question.  
If no, we shelve or pivot.

---

# BEFORE YOU START

## The What-If

I wonder whether default auto-compaction fails because it compresses long context into a broad semantic summary, while the benchmark needs exact answer-critical state.

More concretely:

> What would happen if we compare native auto-compaction against explicit compression policies that are designed to preserve high-value facts such as entities, numbers, dates, corrections, latest values, and counts?

The policies we want to compare are:

| Policy | Meaning |
|---|---|
| `auto` | normal Codex auto-compaction |
| `static-compress` / `auto+static-notebook` | hand-written structured compression format |
| `entropy-compress` / `auto+entropy-notebook` | compression selects facts using information, novelty, rarity, and query relevance |
| `optimized-compress` / `auto+dspy/gepa-notebook` | compression prompt/policy optimized using DSPy/GEPA-style feedback |

Important clarification:

> GEPA/DSPy are part of the sprint direction, but not the first baseline. We first need a measurable compression loop and simple baselines. Then GEPA/DSPy can optimize the compression policy instead of optimizing the final answer prompt.

---

## Why this, why now?

This came from the CompactionBench results so far.

We observed:

- BABILong exact/symbolic tasks are very harsh under long context.
- OOLONG-synth aggregation tasks are cleaner but still not solved.
- Codex compaction events become load-bearing around long contexts, especially `256k+`.
- Many failures look like the system keeps the rough story but loses exact state:
  - wrong entity binding,
  - stale fact,
  - lost exact number,
  - wrong location,
  - wrong latest update,
  - plausible but incorrect answer.

This suggests a concrete hunch:

> Default compaction may preserve gist better than exact state.

Recent surrounding research also makes this worth exploring:

- **LLMLingua / LongLLMLingua** show prompt compression can sometimes reduce tokens while preserving or improving task performance.
- **Selective Context** suggests self-information/entropy can help decide what content is worth keeping.
- **LLMLingua-2** warns that entropy alone may be insufficient because it is not perfectly aligned with task success.
- **RULER, BABILong, OOLONG, LongMemEval** show that long-context ability is not one skill; retrieval, aggregation, updates, and temporal reasoning fail differently.
- **DSPy / GEPA / TextGrad / OPRO** suggest that prompts or pipeline components can be optimized against metrics.

So the timing is right: we already have a benchmark harness, and now we can ask whether better compression changes outcomes.

---

# EXPECTATIONS

## What do I expect to observe?

I expect different compression policies to help different task types.

### Expected pattern

| Task type | Expected best policy | Why |
|---|---|---|
| Exact retrieval / BABILong `qa1` | `entropy-compress` or query-aware compression | The answer-bearing sentence may be rare and query-relevant. |
| Entity binding | `entropy-compress` | Entities, IDs, and key-value facts are easy to score as high-information. |
| Latest update / stale fact | `static-compress` or optimized compression | Needs explicit preservation of corrections and latest-state markers. |
| Counting / aggregation | uncertain | Aggressive compression may drop too many small local facts. |
| OOLONG-real transcript aggregation | uncertain | Real transcripts are messy; compression might help by removing noise or hurt by losing coverage. |

### Expected ranking, early sprint

Before optimization:

```text
auto < static-compress < entropy-compress(query-aware)
```

But for query-blind compression, I expect weaker gains:

```text
entropy-compress(query-blind) <= entropy-compress(query-aware)
```

After we have a small dev set and add DSPy/GEPA-style optimization, I expect:

```text
optimized-compress >= entropy-compress
```

but only if the metric is clean and the dev set is not too small.

---

## Why do I expect this?

My intuition is that long contexts contain many irrelevant or redundant tokens. Default compaction is opaque, and it may summarize the context in a way that is good for fluency but bad for exact answerability.

For example, a native summary might preserve:

```text
Mary moved around several rooms.
```

But the benchmark needs:

```text
Mary journeyed to the bathroom.
```

Similarly, for agent-like tasks, a summary might preserve:

```text
The deployment branch changed during the discussion.
```

But the task needs:

```text
The current deployment branch is beta, replacing alpha.
```

That difference matters.

Entropy/novelty selection should help because exact facts often contain high-information tokens:

- names,
- IDs,
- numbers,
- dates,
- file paths,
- rare entities,
- correction phrases,
- latest/current/final markers.

GEPA/DSPy may help later because they can optimize the compression prompt/policy using downstream answer accuracy rather than human intuition alone.

---

## What would genuinely surprise me?

### Surprise 1: Query-blind compression works almost as well as query-aware compression

That would be very interesting.

It would suggest that a general-purpose compression policy can preserve broadly useful state without knowing the final question.

This would make the result more relevant to real agent compaction, because real compaction usually does not know exactly what question will be asked later.

### Surprise 2: Compression helps BABILong but hurts OOLONG

This would suggest a real tradeoff:

- exact retrieval benefits from aggressive high-information selection,
- aggregation needs broad coverage and may be damaged by compression.

That would open a strong follow-up question:

> Which long-context tasks are compressible, and which require broad coverage?

### Surprise 3: Entropy compression beats optimized GEPA/DSPy compression

This would mean simple information structure matters more than prompt optimization.

That would be surprising because the optimized policy should, in theory, learn better task-specific rules.

### Surprise 4: All explicit compression hurts

This would mean native model context/compaction is already doing something useful that our external compression destroys.

That would also be valuable. It would tell us not to assume explicit compression is automatically better.

---

# FRUITFULNESS PRE-CHECK

## If this surprises me, then what?

If we find that a compression policy reliably beats default auto-compaction, the downstream research question becomes:

> What information should long-context agents preserve under compression pressure?

Or more specifically:

> Can learned or information-guided compression policies outperform native auto-compaction for exact state retention and aggregation in long-context agents?

This could lead to a real project because it connects:

- long-context evaluation,
- prompt compression,
- agent reliability,
- benchmark design,
- optimized prompting/pipeline methods.

The most interesting possible result would be:

> Query-blind or lightly optimized compression improves exact-memory tasks without damaging aggregation too much.

That would suggest that native compaction is not the best available memory/compression policy.

---

## Who would care?

Specific groups who would care:

- researchers building long-context benchmarks,
- people working on prompt compression,
- people building coding/research agents,
- people working on agent memory and context management,
- researchers using DSPy/GEPA-style program optimization,
- teams building systems that must preserve exact evolving state over long sessions.

Concrete nearby communities/papers:

- LLMLingua / LongLLMLingua / LLMLingua-2,
- Selective Context,
- RULER,
- BABILong,
- OOLONG,
- LongMemEval,
- DSPy,
- GEPA,
- TextGrad,
- OPRO.

---

## Does this connect to our research directions?

Yes.

This fits under:

- long-context evaluation,
- agent reliability,
- context compression,
- optimized AI pipelines,
- information selection under budget,
- compaction behavior in long-running agents.

It also connects to future InfiniNews-style directions because news/research agents need to preserve:

- corrections,
- updates,
- entity bindings,
- timelines,
- counts,
- source-specific claims,
- and latest-known state.

---

# TIME BOX

## Sprint duration

**1 week**

This should stay small. It is a scout mission, not a full paper campaign.

## Check-in date

`____ / ____ / ________`

At check-in, ask:

> Is any compression policy showing a clear difference from `auto`?

If no, reduce scope or stop early.

## Hard stop date

`____ / ____ / ________`

At hard stop, choose:

- graduate,
- shelve,
- or pivot.

No extensions without a new sprint.

---

# What “done” looks like

The minimum useful sprint is **not** a huge benchmark sweep.

Done means we can answer:

> Is there any clear evidence that explicit compression changes long-context task performance compared with default auto-compaction?

## Minimum build

### Already started

- `cbench compress`
- deterministic `static-notebook` compression
- deterministic `entropy-notebook` compression

### Still needed

1. Add tiny synthetic task generator for:
   - stale update / latest value wins,
   - entity binding,
   - counting / aggregation.

2. Run a tiny comparison:

```text
auto raw
vs
entropy-compressed query-aware
vs
entropy-compressed query-blind
```

3. Add `static-compress` to the same comparison if cheap.

4. Only after that, add optimizer-lite:
   - manual prompt variants, or
   - OPRO/DSPy small loop, or
   - GEPA if setup is easy enough.

The important point:

> GEPA/DSPy should optimize the compression policy after we have a baseline and objective. Starting with GEPA before baselines would make results hard to interpret.

---

# Proposed experiment design

## Conditions

| Condition | Description | Purpose |
|---|---|---|
| `auto_raw` | Raw long context with normal Codex auto-compaction | Main baseline |
| `static_compressed_query_blind` | Structured heuristic compression without final question | Tests generic compression format |
| `entropy_compressed_query_blind` | Entropy/novelty/value compression without final question | Tests general information selection |
| `entropy_compressed_query_aware` | Same, but compressor sees final question | Upper bound for extractive compression |
| `optimized_compressed` | DSPy/GEPA/OPRO-optimized compression prompt/policy | Later stage after baselines |

## Why include query-aware and query-blind?

This distinction is crucial.

| Mode | Meaning | Interpretation |
|---|---|---|
| Query-aware | Compressor sees the final question | Easier upper bound; useful but less agent-realistic |
| Query-blind | Compressor does not see the final question | Closer to real compaction |

If query-aware works but query-blind fails, the finding is still useful but narrower.

If query-blind works, the result is much more important.

---

## Tiny synthetic task families

### 1. Stale update / latest value wins

Example:

```text
Earlier: the deployment branch was alpha.
Later: the deployment branch changed to beta.
Final instruction: beta is now the current branch.
Question: Which deployment branch should be used now?
Answer: beta
```

Tests:

- latest-state preservation,
- correction handling,
- stale fact suppression.

### 2. Entity binding

Example:

```text
Project Orion uses key K-1942.
Project Lyra uses key K-7721.
Project Vega uses key K-0388.
Question: Which key belongs to Project Orion?
Answer: K-1942
```

Tests:

- exact binding,
- rare IDs,
- entity confusion.

### 3. Counting / aggregation

Example:

```text
Across many chunks, there are repeated events:
job failed
job passed
job failed
...
Question: How many failed jobs occurred?
Answer: N
```

Tests:

- aggregation,
- broad coverage,
- whether compression drops too many local facts.

---

## Benchmark transfer tasks

After the tiny synthetic tasks, test a very small held-out set:

| Benchmark | Tasks | Why |
|---|---|---|
| BABILong | `qa1`, `qa11`, `qa14` | exact fact, symbolic reasoning, update-ish reasoning |
| OOLONG-synth | `counting`, `timeline` | aggregation and temporal aggregation |
| OOLONG-real | `multidoc_rolls`, `multidoc_spells` | realistic long transcript aggregation |

Keep this small. The sprint is about signal, not full coverage.

---

## Models

For the sprint, use only:

- `gpt-5.4-mini` first,
- then `gpt-5.4` only if the first run shows signal.

Do not start with all models.

Why?

Because model sweeps are expensive and hard to interpret before the experimental mechanism is validated.

---

## Metrics

Primary:

- deterministic accuracy,
- parse success,
- compression ratio,
- selected units / total units,
- whether the answer-bearing fact is present in compressed context for synthetic tasks.

Secondary:

- compaction events,
- judge-adjusted accuracy only for borderline formatting issues,
- unsupported facts in compressed artifact,
- latency/cost if available.

---

# Where GEPA/DSPy fits

GEPA/DSPy should not be skipped, but it should be staged.

## Stage 1: deterministic baselines

Use:

- static compression,
- entropy compression,
- query-aware vs query-blind.

Goal:

> Establish whether compression changes outcomes at all.

## Stage 2: optimizer-lite

Try a small optimization loop over compression prompts.

Possible approaches:

- manual prompt variants,
- OPRO-style prompt search,
- DSPy module optimization,
- GEPA reflective prompt evolution.

Goal:

> Improve the compression policy, not the final answer prompt.

## Stage 3: held-out transfer

Evaluate optimized compression on examples not used during optimization.

Goal:

> Check whether the optimizer learned a general compression rule or just overfit the dev set.

## Objective for optimizer

The optimizer should maximize:

```text
final answer accuracy
- compression budget penalty
- unsupported/hallucinated fact penalty
```

Approximate objective:

```text
score = task_accuracy - 0.05 * compression_ratio - 0.20 * unsupported_fact_rate
```

The exact formula can change, but the principle is:

> Optimize for answerability under compression, not pretty summaries.

---

# AFTER THE SPRINT

## What did we actually observe?

_To fill at the end._

Questions to answer:

1. Did any compression policy beat `auto_raw`?
2. Did query-aware compression beat query-blind compression?
3. Did compression help exact-memory tasks more than aggregation tasks?
4. Did compression ever hurt performance?
5. Did the compressed artifact preserve the answer-bearing fact?
6. Did results transfer from synthetic tasks to BABILong/OOLONG/OOLONG-real?

---

## Were expectations violated?

_To fill at the end._

Examples:

- Expected entropy to help entity binding, but it did not.
- Expected query-aware to dominate query-blind, but they were similar.
- Expected compression to help BABILong, but it hurt OOLONG.
- Expected optimized compression to beat static compression, but it did not.

---

# THE DECISION

## Graduate

Graduate to Research Question Sharpener if:

> A compression policy clearly beats default `auto_raw` on at least one important task family and transfers beyond the synthetic tasks.

Possible sharpened RQ:

> Can information-guided or learned compression policies outperform native auto-compaction for preserving answer-critical state in long-context agent tasks?

Or:

> Which types of long-context tasks benefit from aggressive compression, and which require broad context coverage?

---

## Shelve

Shelve if:

- compression variants are noisy,
- no condition consistently beats `auto_raw`,
- results only work in query-aware mode and fail query-blind,
- or improvements are too small to matter.

What we learned anyway:

> Default compaction may be hard to beat with simple external compression, or our current compression objective is not aligned enough with the tasks.

---

## Pivot

Pivot if the original what-if is not fruitful but an adjacent surprise appears.

Possible pivots:

### Pivot A: Compression tradeoff by task type

If compression helps BABILong but hurts OOLONG:

> Which long-context tasks are compressible, and which need broad coverage?

### Pivot B: Query-aware gap

If query-aware compression works but query-blind fails:

> How much future-task information does a compactor need to preserve useful state?

### Pivot C: Optimizer failure

If GEPA/DSPy does not beat simple entropy compression:

> Are high-information facts mostly detectable with simple heuristics?

### Pivot D: Native compaction is stronger than expected

If all explicit compression hurts:

> What does native compaction preserve that external compression destroys?

---

# Final note for advisor/boss

This is an Exploration Sprint because the current results are impossible to interpret as a research claim without a clearer experimental mechanism.

The sprint is designed to make the next results interpretable:

```text
Question: Does changing compression policy change long-context performance?

Baseline: native auto-compaction.

Interventions:
1. static structured compression,
2. entropy/novelty compression,
3. later DSPy/GEPA-optimized compression.

Outcome: decide whether this becomes a real research question.
```

The goal is not to prove a final claim this week.  
The goal is to find out whether there is a surprising enough signal to justify sharpening the question.
