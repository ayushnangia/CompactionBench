# What we are doing wrong — and how to fix it

## Problem 1: No sharp hypothesis

### What is wrong
We ask "does compression affect performance?" That is descriptive, not explanatory. It produces observations, not conclusions. A good experiment should be able to surprise us by proving us wrong. Our current setup can only produce "it helps here, hurts there" — which is data, not a finding.

### What sharp hypotheses look like

**Hypothesis A:** Compaction fails on exact-memory tasks because it drops low-frequency tokens. The words that carry the answer ("bathroom", "Jeff", "K-1942") are rarer than the filler words that surround them, and compressing to a token budget naturally discards rare tokens.

→ Test: measure token frequency of retained vs dropped facts. If retained facts have higher frequency than dropped ones, the hypothesis is supported.

→ Surprise: if retained facts are NOT higher frequency, then something else is causing the loss — position, syntax, or the model's attention pattern.

**Hypothesis B:** Query-blind compression fails not because it selects wrong facts, but because it has no selection signal at all beyond surface statistics. The answer-bearing fact ("Mary journeyed to the bathroom") looks statistically identical to a distractor fact ("Mary discussed the weather") to a compressor that cannot see the question.

→ Test: compress with a weak proxy for the question — e.g. a task-type label ("this is a location question") rather than the full question. If performance improves, the compressor just needs a hint, not the exact question.

→ Surprise: if a weak hint matches full-question performance, then the compressor does not need much.

**Hypothesis C:** A stronger model does not recover deleted information because the compressor's output is the model's entire evidence. Information theory says you cannot reconstruct what was never preserved. If true, this means better compression policy matters more than better models for long-context reliability.

→ Test: vary the compression budget (50, 200, 500, 1000 tokens) and see if accuracy plateaus. If more tokens do not help beyond a point, the compressor is structurally losing information, not just running out of space.

### Recommendation
Pick **Hypothesis A and B** as the next sprint. Both are testable within a week, both can produce a clear yes/no, and both connect to an existing literature (token frequency effects in compression, query-aware vs query-agnostic summarization).

---

## Problem 2: Synthetic tasks at wrong difficulty

### What is wrong
Stale-update = 100% (ceiling). Counting = 0% for mini (floor). Entity binding = 20% regardless of condition. We have no task in the 30-70% range where compression can show a visible swing. The experiment becomes: "everything is tied" — which looks like a null result even when it is not.

### Fix: design tasks for the sweet spot

**Stale-update — make it harder:**
- Add multiple intermediate values. "Alpha → beta → gamma → delta. Then changed back to beta. Then final: epsilon."
- Add conflicting distractor updates. "Someone suggested changing it to zeta, but the team decided against it."
- Place the final value in the middle of the context, not near the end.
- Measure: raw should drop from 100% to ~60%. Then compression can show an effect.

**Entity binding — reduce confusion:**
- Current task: 3 entities, 3 values, easy to mix up.
- Better: 5 entities with similar names. "Project Orion, Project Orin, Project Oren, Project Oran, Project Orun." Only one has the right key.
- Add distractor bindings: "Orion was discussed near Orin, but their keys are different."
- Measure: raw should be ~40%. Then we can see if compression makes binding better or worse.

**Counting — use gpt-5.4 as the primary model:**
- Mini cannot count. Stop testing counting on mini — it is a waste of runs.
- For gpt-5.4: add more distractor events (50+), make the target count less obvious (17 instead of 15), scatter events unevenly.
- Measure: raw should be ~60-80%. Then compression drop becomes visible as a score decrease, not just a binary 5/5 → 0/5.

### Recommendation
Regenerate all synthetic tasks with these difficulty adjustments. Run on gpt-5.4 only for counting. This takes one afternoon.

---

## Problem 3: Never compared against existing methods

### What is wrong
We built our own compression (entropy-based, static, heuristic) and compare it against "no compression." But LLMLingua, LongLLMLingua, and MEMENTO exist. We cite them as motivation but have never run a head-to-head.

The real question is not "does our compression beat nothing?" — it is "does our compression beat *their* compression?" Without that comparison, we are building in a vacuum.

### What exists

| Method | What it does | Code available | Ease of integration |
|---|---|---|---|
| LLMLingua | Token-level prompt compression, coarse-to-fine | `pip install llmlingua` | Easy — takes text, returns compressed text |
| LongLLMLingua | Same, optimized for long context with question-aware compression | Same package | Easy — takes (text, question), returns compressed text |
| Selective Context | Self-information based filtering | GitHub: liyucheng09/Selective_Context | Moderate — needs a small LM for scoring |
| MEMENTO | Compresses reasoning traces into mementos for long-horizon agents | GitHub: microsoft/memento | Unknown — need to check API |

### Proposed comparison

Take our 5 BABILong tasks. Compress with:
1. Our entropy (query-aware) — already done
2. Our entropy (query-blind) — already done
3. LongLLMLingua (query-aware) — needs implementation
4. LongLLMLingua (query-blind) — needs implementation
5. Selective Context — needs implementation

Run all on gpt-5.4-mini. Compare accuracy, compression ratio, and gold survival.

If our method beats theirs: we have a claim.
If their method beats ours: we learn what we are missing.
If they are tied: the task is the bottleneck, not the compression method.

### Recommendation
Integrate LongLLMLingua first (easiest, most cited, most directly comparable). Run the comparison. This answers whether we have a method worth publishing or just an interesting observation.

---

## What a fixed sprint looks like

**Day 1:** Write sharp hypotheses. Pick A and B. Design difficulty-adjusted synthetic tasks.

**Day 2:** Regenerate tasks. Run raw baselines to confirm 40-60% ceiling.

**Day 3:** Integrate LongLLMLingua. Run compression comparison across all methods on BABILong 5-task.

**Day 4:** Analyze results. Answer: which method wins? Which hypothesis is supported? What surprised us?

**Day 5:** Write up. Decide: graduate to research question, pivot, or shelve.

The difference from the current sprint: we stop asking "what happens?" and start asking "was my hypothesis wrong?"
