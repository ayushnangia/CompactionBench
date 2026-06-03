# 10 Research Questions for an ACL Paper on CompactionBench

Based on 648 experiments, 6 benchmarks, and findings on what gets lost during context compaction.

---

## RQ1: Why does compaction destroy exact facts but preserve aggregation?

We found a 37-point gap for exact facts (BABILong) vs an 8-point gap for aggregation (OOLONG). The mechanism is unknown. Does the model attend differently to single facts vs distributed patterns? Are exact facts encoded in fewer tokens and therefore more likely to be dropped? Answering this would explain a fundamental property of transformer context compression.

**Experiment:** Attention head analysis during compaction. Compare attention weights on answer-bearing tokens before and after compaction.

---

## RQ2: Can a small classifier predict which facts survive compaction?

If a lightweight model can score sentences by "survival probability," we can build a compressor that selectively preserves high-risk facts. This turns compaction from a lossy heuristic into a guided process.

**Experiment:** Train a binary classifier on BABILong training tasks to predict whether a sentence contains the gold answer. Test whether classifier-guided compression beats heuristic entropy.

---

## RQ3: Does the position of a fact in context predict its survival?

We observed that hints at the beginning survive better than hints at the end. Does the U-shaped attention curve ("lost in the middle") apply to compaction? This would connect two established findings.

**Experiment:** Systematically vary the position of the answer-bearing fact in the context. Measure survival rate at 10 position buckets.

---

## RQ4: Is the retention-accuracy gap a universal property of long-context models?

We measured it on Codex (GPT-5.4 family). Does it generalize to Claude, Gemini, Llama, Qwen? A cross-model study would establish the gap as a fundamental diagnostic metric.

**Experiment:** Run BABILong and OOLONG on 5+ models. Compare retention-accuracy gaps. Publish as a leaderboard-style benchmark.

---

## RQ5: Can task-type hints replace query-aware compression?

Our weak-hint experiment showed that "find the current value" nearly matches knowing the exact question. If this generalizes, real agent compression can work without knowing future questions.

**Experiment:** Scale weak-hint to 50+ tasks across BABILong, OOLONG, and SWE-chat. Measure whether task-type labels consistently match query-aware performance.

---

## RQ6: Why does grep beat context injection?

Grep on the original file scored 60% vs 43% for context injection. Why is tool-assisted retrieval better than having the text in context? This has implications for RAG vs long-context debates.

**Experiment:** Compare grep vs context injection at multiple lengths. Control for: chunking overhead, attention dilution, and retrieval precision.

---

## RQ7: What is the optimal compression budget per task type?

Counting needs broad coverage (many events). Exact facts need targeted preservation (one sentence). Is there a task-type-dependent optimal budget?

**Experiment:** Budget sweep (50 to 5000 tokens) on 5 task types. Find the inflection point where accuracy saturates. Publish budget recommendations per task type.

---

## RQ8: Do compression hints change what the model attends to?

We found that hints backfire — "keep grep-friendly terms" made the model drop the answer. Does the hint text literally change attention patterns? This would be the first mechanistic study of how compression instructions affect transformer behavior.

**Experiment:** Open-weight model (Qwen 3.6 27B). Compare attention maps with and without hints. Show that the hint text competes for attention with the actual content.

---

## RQ9: Can we build a compaction diagnostic that works without gold answers?

The retention-accuracy gap requires knowing the gold answer. Can we predict retention from model internals (logprobs, attention entropy) without needing a pre-written question?

**Experiment:** Correlate per-token logprob drop during compaction with downstream accuracy. Train a "compaction quality predictor" that runs without gold labels.

---

## RQ10: Does compaction explain real agent failure modes?

Our failure taxonomy (fact dropped, wrong location, stale value, counting error) came from synthetic and benchmark tasks. Do these same categories appear in real coding sessions?

**Experiment:** Analyze SWE-chat transcripts. Categorize real agent failures using our taxonomy. Show that compaction-induced failures are a measurable fraction of real-world agent errors.
