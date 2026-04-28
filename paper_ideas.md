# What makes CompactionBench worth a paper

This project needs a metric that researchers can reason about, not just a collection of accuracy numbers.

---

## The core claim

> Long-context agents fail partly because compaction keeps prose summaries instead of exact state. We can measure this with a retention metric that separates memory loss from reasoning failure.

**Evidence so far:**

| Benchmark | Retention | Accuracy | Gap |
|---|---:|---:|---:|
| BABILong qa1-10 | 45.8% | 8.3% | +37.5pp |
| BABILong qa11-20 | 41.9% | 14.7% | +27.2pp |
| OOLONG-synth | 54.6% | 46.3% | +8.3pp |

For BABILong, the gold answer appears in context ~46% of the time, but the model only answers correctly ~8% of the time. **The model has the information but cannot use it.**

For OOLONG, the gap is small. **When information survives, the model can aggregate it.**

This bifurcation — exact memory degrades while aggregation survives — is the key paper finding.

---

## Three candidate metrics

### Metric 1: Compaction Retention Score

For each task, we check whether the answer-bearing fact survived in the compressed context.

```text
retention = (answer-bearing facts in compressed context) / (answer-bearing facts in original context)
```

For a batch:

```text
CRS = mean(retention across all tasks)
```

If retention is high but accuracy is low, the model can reason but could not find the fact.  
If retention is low and accuracy is low, compaction dropped the fact entirely.  
If retention is high and accuracy is high, the system works.

This gives a two-dimensional diagnosis.

### Metric 2: Compaction Degradation Ratio

For each task type, compare accuracy at different context lengths.

```text
CDR = accuracy at length L / accuracy at baseline (no compaction)
```

A sharp drop at the compaction threshold is a strong signal.

This can be plotted as a curve for each task type. Researchers can see exactly where and how their system degrades.

### Metric 3: Exact vs Aggregate Score

BABILong tests exact single-fact recall. OOLONG tests aggregation over many facts. The gap between them tells us whether compaction hurts exact memory more than broad coverage.

```text
Exact Score = mean(exact-memory task accuracy)
Aggregate Score = mean(aggregation task accuracy)
EAS Gap = Exact Score / Aggregate Score
```

A small gap means compaction is doing well at preserving both kinds of information.  
A large gap means one type of information is being lost disproportionately.

---

## Why these metrics matter

Currently, most long-context papers only report:

```text
accuracy at length L
```

But that does not tell us why the model failed.

Our metrics would let a researcher say:

> At 256k tokens, retention of answer-bearing facts dropped to 12%,  
> but among those 12%, the model could reason correctly 80% of the time.  
> This means compaction is the bottleneck, not reasoning.

That is a much stronger scientific claim than:

> Accuracy dropped from 46% to 37%.

---

## What would actually be useful to researchers

### For long-context model builders

> Here is a simple diagnostic that tells you whether your model is bad at finding facts or bad at reasoning over them.

### For agent harness builders

> Here is the exact context length where your system starts losing important information. You should checkpoint before this point.

### For prompt compression researchers

> Here is a metric that tells you whether your compression method preserves answer-critical information, not just semantic similarity.

### For coding agent evaluation

> Here is a benchmark that measures whether the agent remembers the correct file path, variable name, or state update, not just the general story.

---

## The "double descent" analogy

The original suggestion was to find a metric like the double-descent phenomenon: a clear, surprising signal that makes researchers rethink what they know.

For CompactionBench, the candidate surprise is not a U-curve. It is a bifurcation:

> At some context length, exact-memory accuracy and aggregation accuracy diverge sharply. This tells us the system is keeping the story but losing the state.

If we can reliably show this bifurcation across models and tasks, that is a paper-level finding.

---

## How to present this in a paper

Not as:

> We ran BABILong, OOLONG, and Codex and here are 30 accuracy numbers.

Instead as:

1. We built a benchmark that separates memory retention from reasoning accuracy.
2. We found that compaction starts hurting exact state well before it hurts broad semantic recall.
3. We showed that a simple compression policy can partially close this gap.
4. We propose three metrics that other researchers can use to diagnose their own systems.

A reader should finish the paper and think:

> I want to use this metric to test my own agent.

Not:

> Okay, another benchmark.

---

## The simplest useful application

For someone building a coding agent, the most useful output of this project would be:

> At approximately 200k tokens of conversation, your agent will start losing exact file paths, variable names, error codes, and entity bindings. Consider checkpointing state before this threshold, or using a structured state ledger.

That one sentence, backed by evidence, is worth more than 50 accuracy tables.

---

## What we still need to reach that

1. Clean retention metrics across the existing batches.
2. Compression comparison results.
3. A plot: retention vs accuracy across lengths.
4. One clean number that any researcher can quote: "at 256k tokens, retention drops below X%."
