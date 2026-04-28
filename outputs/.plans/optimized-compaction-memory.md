# Plan: Optimized Compaction Memory

Slug: `optimized-compaction-memory`

## Topic
Can we improve long-context compaction/evaluation by borrowing ideas from prompt compression, long-context benchmarks, prompt/program optimization, and information-guided selection — without committing yet to a full agent memory-system project?

## Core question
Default long-context compaction is opaque and may preserve gist while losing exact state. This narrowed sweep asks which surrounding research ideas are most useful for a near-term CompactionBench exploration: compression policies, benchmark design, optimizer-driven policy search, and entropy/novelty-based fact selection.

## Sources to compare
I will search and compare source material across these groups:

1. **Context compression / prompt compression**
   - LLMLingua / LongLLMLingua
   - Selective Context
   - query-aware context compression
   - KV/cache/context pruning if relevant
   - learned summarization or compression for long-context reasoning

2. **Long-context evaluation benchmarks**
   - BABILong
   - OOLONG
   - LongMemEval
   - Needle-in-a-haystack variants
   - multi-document aggregation/evolving-state benchmarks

3. **Prompt/program optimization**
   - DSPy
   - GEPA or GEPA-like reflective prompt optimization
   - TextGrad / OPRO / prompt optimization by feedback
   - using optimization to improve compression/intermediate artifacts, not just final answers

4. **Information-theoretic / entropy-guided selection**
   - novelty, salience, surprise, information gain
   - redundancy reduction / maximal marginal relevance
   - summarization under budget
   - extracting high-value facts: entities, numbers, dates, corrections, contradictions

## Dimensions to evaluate
For each source or source family, I will evaluate:

| Dimension | Question |
|---|---|
| Source | What paper/system/benchmark is this? |
| Key claim | What does it claim about memory, compression, context, or optimization? |
| Mechanism | What actually changes: prompt, memory store, retriever, summarizer, compressor, optimizer? |
| Evidence type | Benchmark, ablation, human eval, system demo, theoretical argument, or code? |
| Relevance to our policy table | Does it support `static-notebook`, `entropy-notebook`, `dspy/gepa-notebook`, or only background? |
| Caveats | What does it not prove? What assumptions differ from CompactionBench? |
| Confidence | High / medium / low, based on evidence quality and directness. |

## Expected output structure
The final output will be exactly one comparison/research file:

`outputs/optimized-compaction-memory-comparison.md`

Planned sections:

1. **Short answer** — What the surrounding research suggests we should try.
2. **Comparison matrix** — Source, key claim, evidence type, caveats, confidence.
3. **Agreement** — What sources broadly agree on.
4. **Disagreement / uncertainty** — What is unresolved or contradictory.
5. **Method map** — Mermaid diagram of possible compression-policy pipeline.
6. **Implications for CompactionBench** — Concrete policy designs to implement later:
   - `auto`
   - `auto+static-notebook`
   - `auto+entropy-notebook`
   - `auto+dspy/gepa-notebook`
7. **Recommended Exploration Sprint** — 1-week plan with tasks, metrics, and stop/go criteria.
8. **Sources** — Direct URLs for every source used.

## Quantitative charts / diagrams
- If I find comparable quantitative metrics across papers, I will generate a chart with `pi-charts`.
- Since many sources will be method/system papers with non-comparable metrics, I expect a **Mermaid method diagram** to be more appropriate than a quantitative chart.

## Verification approach
- Use paper search first for primary sources.
- Prefer primary papers and official repos over blog posts.
- Use source verification before finalizing claims.
- Downgrade claims that are only weakly supported or transfer only indirectly to CompactionBench.

## Initial hypothesis
The literature will likely support three points:

1. Prompt/context compression is useful but lossy and often task-sensitive.
2. Long-context benchmarks disagree on what counts as success: exact retrieval, aggregation, multi-hop reasoning, and persistent-memory evaluation expose different weaknesses.
3. A hybrid policy — entropy/novelty candidate selection plus DSPy/GEPA-style optimization of the compression prompt — is plausible and under-tested.

## Deliverable
A cited comparison and action plan for eventually implementing and testing four policies:

| Policy | Meaning |
|---|---|
| `auto` | normal Codex auto-compaction |
| `auto+static-notebook` | hand-written structured memory |
| `auto+entropy-notebook` | memory chooses facts using information/novelty score |
| `auto+dspy/gepa-notebook` | optimized memory policy |
