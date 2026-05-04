# Sharp Hypotheses — CompactionBench Sprint

## Hypothesis A: Token frequency

> Compaction drops answer-bearing facts because they contain low-frequency tokens. Words like "bathroom", "K-1942", "Jeff" are rarer than filler words, and compression to a fixed token budget naturally discards rare tokens.

**Test:** Measure token frequency of retained vs dropped facts. If retained facts have higher average token frequency than dropped facts, Hypothesis A is supported.

**Falsification:** If retained and dropped facts have no frequency difference, then something else causes the loss (position, syntax, attention pattern).

**If true:** Token-frequency-aware compression should outperform entropy alone.

---

## Hypothesis B: Question signal

> Query-blind compression fails because it has no signal for relevance beyond surface statistics. The answer-bearing fact looks identical to distractor facts without the question as a relevance anchor.

**Test:** Compare query-blind vs query-aware with partial hints. If even a weak hint (task type: "this is a location question") improves performance over query-blind, the compressor just needs *any* relevance signal, not the exact question.

**Falsification:** If weak hints perform like query-blind, then the compressor needs full question access — or the task is fundamentally different.

**If true:** Semi-aware compression (task-type hint, no full question) could close the gap with query-aware, making compression more agent-realistic.

---

## Hypothesis C: Method comparison

> Our entropy-based compression performs worse than LongLLMLingua on exact-memory tasks because LongLLMLingua uses a learned token-importance model rather than heuristic scoring.

**Test:** Head-to-head on recalibrated tasks. If LongLLMLingua wins on exact-memory but ties on aggregation, the learned model captures something our heuristics miss.

**Falsification:** If they tie, the heuristic is good enough and the task difficulty is the bottleneck.

**If true:** Heuristic methods are insufficient for exact-memory compression; a learned component is needed.
