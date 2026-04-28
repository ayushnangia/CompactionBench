# Exploration Sprint: Can better compression preserve what long-horizon agents need?

> **Type:** Exploration Sprint, not a final Research Question yet.  
> **Goal:** Find out whether there is a surprising signal worth sharpening into a real research question.

---

## Short version

I am testing whether long-running agents fail not only because they run out of context, but because **compaction keeps the wrong information**.

Default auto-compaction may preserve the general story, while coding and reasoning tasks often need precise state:

- variables,
- file names,
- IDs,
- numbers,
- diffs,
- locations,
- latest decisions,
- updated instructions.

The sprint asks:

> What happens if we compare native auto-compaction against explicit compression algorithms designed to preserve this precise information?

This is still exploration. The purpose is not to prove a paper claim yet. The purpose is to see whether there is a clear effect worth turning into a research question.

---

# Background: What we have done so far

## 1. Built CompactionBench

We built a simple benchmark path:

```text
JSONL task
→ inject long context into Codex
→ let Codex auto-compact
→ ask final question
→ score answer
→ inspect failures
```

This is intentionally simple. We want to observe what happens when a real coding-agent-like system is pushed into long context and compaction.

---

## 2. Ran BABILong qa1–qa10

BABILong is a long-context benchmark where the model has to recover or reason over facts hidden inside a large noisy context.

The early result:

> For qa1–qa10, many failures looked like vague summaries instead of exact memory.

In plain English:

- the model often kept the rough story,
- but lost the exact word/object/place needed to answer correctly.

Example failure shape:

```text
Needed: Mary is in the bathroom.
Model remembers: Mary moved around / Mary was somewhere indoors.
```

This suggests compaction may preserve gist but lose exact state.

---

## 3. Added BABILong qa11–qa20

We extended the benchmark to include BABILong qa11–qa20, which cover additional reasoning families.

The early observation:

> The model sometimes preserved basic coreference and supporting facts better than expected.

This matters because it means failure is not just about length. The exact question type and context structure matter a lot.

Important caveat:

- Some qa11–qa20 runs were affected by usage-limit errors.
- So these results are useful for direction, but not yet a clean final matrix.

---

## 4. Added OOLONG-synth

We also added OOLONG, a benchmark for long-context reasoning and aggregation.

BABILong mostly asks:

> Can you recover an exact fact from long noise?

OOLONG asks more like:

> Can you analyze many local chunks and aggregate them into a global answer?

This is important because real agent work is often aggregation:

- count failures,
- summarize logs,
- track timelines,
- compare many files,
- combine many local observations.

Current result:

> OOLONG-synth is cleaner operationally than BABILong and tests a different long-context skill.

---

## 5. OOLONG-real is planned but not fully run yet

OOLONG-real uses realistic long transcripts instead of synthetic examples.

Why it matters:

> It is closer to real long-running agent context: messy, conversational, repetitive, and full of entities/events.

This is a next step, but not the first thing needed for the sprint.

---

## 6. Added first compression baseline infrastructure

We started implementing a compression path:

```text
raw task context
→ compress context first
→ run normal benchmark on compressed context
→ compare with raw auto-compaction
```

Implemented so far:

- `cbench compress`
- basic `static-notebook` compression
- basic `entropy-notebook` compression
- tests passing

This is not GEPA/DSPy yet. It is the simple baseline needed before optimization.

---

# Why the current results alone are hard to interpret

Paras's point is right:

> The results are hard to interpret without knowing exactly what the experiments are about.

Right now, the BABILong and OOLONG results tell us that long-context performance degrades, but they do not yet tell us **why**.

Possible explanations:

1. The model cannot reason over very long context.
2. The model can reason, but compaction drops exact facts.
3. The benchmark is too strict with exact answers.
4. The task type matters more than length.
5. The model preserves gist but loses precise state.
6. Aggregation tasks and exact-memory tasks fail differently.

This sprint is meant to make the next experiment easier to interpret.

Instead of only asking:

> Does Codex fail on long context?

we ask:

> Does changing the compression policy change what Codex remembers?

That is a clearer experiment.

---

# BEFORE YOU START

## The What-If

I wonder whether long-horizon agents, when a task runs across many messages or sessions, fail not only because they run out of context, but because compaction keeps the wrong information.

Default auto-compaction may preserve the general story, while coding and reasoning tasks need precise state.

What would happen if we compared native auto-compaction against explicit compression algorithms designed to preserve this kind of information?

Can we later tune or optimize the compression policy with a metric?

---

## Why this, why now?

Two reasons.

First, our current failures often look like this:

> The model remembers the rough story but loses the exact detail needed to continue correctly.

Second, recent work suggests this is becoming an active research direction.

Relevant examples:

- **MEMENTO**: teaches models to split reasoning into blocks and compress those blocks into compact “mementos.”  
  Link: https://github.com/microsoft/memento/blob/main/docs/memento.pdf

- **ACON**: studies optimized compression for long-horizon agents/reasoning.  
  Link: https://arxiv.org/abs/2510.00615v1

So this sprint asks a smaller version of the bigger question:

> Can better compression preserve the state that long-context agents actually need?

---

# EXPECTATIONS

## What do I expect to observe?

I expect explicit compression to help most when the task depends on a small number of precise facts.

Examples:

- latest update / stale fact,
- entity binding,
- exact ID or number,
- file path,
- object/location tracking.

I expect compression to help less, or even hurt, when the task needs many small details spread across the whole context.

Examples:

- counting,
- aggregation,
- timeline summaries,
- OOLONG-style distributional questions.

---

## Why do I expect this?

My hunch is:

> Agents often keep the rough story but lose the precise fact.

Default compaction may summarize what happened, but not preserve the exact information needed to answer correctly later.

For example:

```text
Bad compressed memory:
Mary moved through several rooms.

Useful compressed memory:
Mary is currently in the bathroom.
```

Or in coding-agent terms:

```text
Bad compressed memory:
The parser was changed during debugging.

Useful compressed memory:
The bug is in compactionbench/run.py, parse_codex_jsonl, where context_compacted events were missed.
```

The second version is what an agent needs to continue work correctly.

---

## What would genuinely surprise me?

### Surprise 1

I would be surprised if simple compression works almost perfectly out of the box on 1M+ context.

That would mean a lot of the long-context problem is just poor selection of important facts.

### Surprise 2

I would also be surprised if simple entropy/static compression beats more complex optimized compression like GEPA/DSPy or MEMENTO-style compression.

That would suggest simple information signals are already enough:

- rarity,
- entity names,
- IDs,
- numbers,
- latest/current markers,
- correction words.

### Surprise 3

I would be surprised if compression helps exact-memory tasks but clearly hurts aggregation tasks.

That would reveal a real tradeoff:

> Some tasks need sharp compression; others need broad coverage.

This could become a strong research direction.

---

# FRUITFULNESS PRE-CHECK

## If this surprises me, then what?

If explicit compression works better than default compaction, it opens a bigger research question:

> What kind of memory or compressed state should an adapting AI keep while it is learning or solving a domain-specific task?

Follow-up questions:

- What information should an agent keep versus discard during long tasks?
- Can an agent learn what matters in a new domain while it is working?
- Can better compression make agents adapt faster with less context?
- Can we train or optimize a compactor using downstream task success as the metric?

This would be more interesting than only saying:

> Long context is hard.

It would let us ask:

> What should the system preserve under context pressure?

---

## Who would care?

This would be relevant to people working on:

- long-context models,
- coding agents,
- research agents,
- prompt compression,
- context management,
- agent memory,
- long-horizon reasoning.

Specific related systems/work:

- MEMENTO, Microsoft Research,
- ACON, KAIST / Microsoft / University of Cambridge,
- LLMLingua / LongLLMLingua,
- OOLONG,
- BABILong,
- LongMemEval,
- DSPy,
- GEPA,
- TextGrad,
- OPRO.

It would also matter to builders of coding-agent harnesses, such as:

- pi.dev / Mario Zechner,
- OpenCode / Dax Raad,
- Codex-style coding agents,
- Claude Code-style coding agents.

These systems all need to decide what context, files, memory, and task history an agent should carry forward during long coding sessions.

---

## Does this connect to our research directions?

Yes.

This fits under:

> **Research Direction 1: AI that adapts to a domain.**

The connection is simple:

> Domain adaptation requires memory.

An agent cannot adapt to a local codebase, dataset, user, or task if it forgets the details it just learned.

This sprint asks whether better compression can help an agent preserve the right domain-specific information while discarding noise.

---

# TIME BOX

## Sprint duration

**1 week**

## Check-in date

**30 / 04 / 2026**

At check-in, ask:

> Is anything surprising emerging?

If not, consider stopping early or narrowing the scope.

## Hard stop date

**04 / 05 / 2026**

No extension without a new sprint.

---

# What “done” looks like

This should stay small.

Minimum done:

1. Compare default auto-compaction against simple explicit compression.
2. Test on a few tiny synthetic tasks:
   - latest update / stale fact,
   - entity binding,
   - counting or aggregation.
3. Track:
   - final accuracy,
   - whether the important fact survived compression,
   - compression ratio,
   - which task types improved or got worse.
4. Decide whether GEPA/DSPy optimization is worth adding next.

This is a scout mission, not a full benchmark campaign.

---

# Concrete experiment plan

## Conditions

| Condition | Meaning | Why |
|---|---|---|
| `auto_raw` | raw long context with normal Codex auto-compaction | baseline |
| `static_compress` | hand-written structured compression | simple explicit state baseline |
| `entropy_compress_query_blind` | compression uses rarity/novelty/entities/numbers but does not see final question | closer to real compaction |
| `entropy_compress_query_aware` | same compression, but sees final question | upper bound |
| `optimized_compress` | later GEPA/DSPy/OPRO-style optimized compressor | only after baselines are interpretable |

---

## Tiny synthetic tasks

### 1. Latest update / stale fact

Question:

> Does compression preserve the latest valid value instead of an old stale value?

Example:

```text
Earlier: the deployment branch was alpha.
Later: the deployment branch changed to beta.
Final: beta is now the current branch.
Question: Which branch should be used now?
Answer: beta
```

---

### 2. Entity binding

Question:

> Does compression preserve the exact relationship between entity and value?

Example:

```text
Project Orion uses key K-1942.
Project Lyra uses key K-7721.
Question: Which key belongs to Project Orion?
Answer: K-1942
```

---

### 3. Counting / aggregation

Question:

> Does compression preserve enough distributed details to compute a count?

Example:

```text
Across the context, many job events appear.
Some are passed, some are failed.
Question: How many failed jobs occurred?
Answer: N
```

This is important because compression may help exact facts but hurt aggregation.

---

# Where GEPA/DSPy fits

GEPA/DSPy is still part of the direction, but it should come after the simple baselines.

Reason:

> If we start with GEPA immediately, the result is hard to interpret.

We would not know whether improvement came from:

- compression helping,
- prompt optimization overfitting,
- query leakage,
- benchmark quirks,
- or random variation.

Better order:

```text
Stage 1: auto_raw vs static/entropy compression
Stage 2: add query-aware vs query-blind comparison
Stage 3: optimize compression prompt with DSPy/GEPA/OPRO
Stage 4: test optimized compression on held-out BABILong/OOLONG/OOLONG-real
```

The optimizer should optimize the **compressor**, not the final answer prompt.

Objective:

```text
final answer accuracy
- compression size penalty
- unsupported/hallucinated fact penalty
```

In plain English:

> Keep what helps the future answer, keep it small, and do not invent facts.

---

# AFTER THE SPRINT

## What did we actually observe?

_To fill at the end._

Questions to answer:

1. Did compression beat default auto-compaction?
2. Did it help exact-memory tasks more than aggregation tasks?
3. Did query-aware compression beat query-blind compression?
4. Did simple compression perform surprisingly well?
5. Did compression hurt any task type?
6. Is GEPA/DSPy optimization worth doing next?

---

## Were expectations violated?

_To fill at the end._

Examples:

- I expected compression to help exact facts, but it did not.
- I expected query-aware compression to beat query-blind, but they were similar.
- I expected aggregation to suffer, but it improved.
- I expected optimized compression to beat simple entropy compression, but it did not.

---

# THE DECISION

## Graduate

Graduate if:

> Compression clearly improves one important task family and the result is not just a one-off artifact.

Possible Research Question:

> Can information-guided or learned compression policies preserve answer-critical state better than native auto-compaction in long-horizon agents?

---

## Shelve

Shelve if:

- results are noisy,
- compression does not help,
- improvements only happen in artificial query-aware settings,
- or the effect is too small to matter.

What I learned anyway:

> Default compaction may be harder to beat than expected, or our compression objective is not yet aligned with the tasks.

---

## Pivot

Pivot if something adjacent is more interesting.

Possible pivots:

### Pivot 1

If compression helps exact retrieval but hurts aggregation:

> Which task types are compressible, and which need broad context coverage?

### Pivot 2

If simple entropy compression beats optimized compression:

> Are high-information facts mostly detectable with simple heuristics?

### Pivot 3

If query-blind compression works well:

> Can we build general-purpose compaction policies that do not need to know the future question?

---

# What is done vs what remains

## Done

- Built the direct-injection benchmark harness.
- Ran BABILong qa1–qa10.
- Added BABILong qa11–qa20.
- Added OOLONG-synth support and ran a first clean batch.
- Added OOLONG-real support, but not a full clean run yet.
- Added compaction-event parsing for Codex.
- Added first compression infrastructure:
  - `cbench compress`,
  - static compression baseline,
  - entropy compression baseline.

## Still to do for this sprint

- Add tiny synthetic tasks:
  - stale update,
  - entity binding,
  - counting/aggregation.
- Run tiny comparison:

```text
auto_raw
vs
static_compress
vs
entropy_compress_query_blind
vs
entropy_compress_query_aware
```

- Inspect whether the important fact survived compression.
- Decide whether to add GEPA/DSPy optimization next.

## Later, only if the sprint graduates

- Add GEPA/DSPy/OPRO optimization.
- Run held-out BABILong/OOLONG/OOLONG-real evaluation.
- Compare optimized compression against default auto-compaction at larger scale.
- Turn the result into a Research Question Sharpener.

---

# Final plain-English framing

The current experiments show that long-context agents can fail after compaction, but the reason is not yet clear.

This sprint asks a smaller and more interpretable question:

> If we change what gets compressed and preserved, does the agent remember the right things more often?

If yes, this becomes a real research direction about learned or information-guided compaction.

If no, we stop or pivot.

That is why this is an Exploration Sprint, not a final research claim yet.
