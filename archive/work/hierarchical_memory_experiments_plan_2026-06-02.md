# Hierarchical memory experiment plan

## Core question

Does a hierarchical memory/retrieval system beat flat retrieval, PEEK-style context maps, and virtual context under the same budget?

More precise version:

> If an agent has recent raw memory, older summaries/timelines, stable semantic facts, and a cold raw archive, does it answer long-term memory questions more accurately / cheaply than flat grep/RAG or a single PEEK context map?

## Main hypothesis

Hierarchy should help when the task needs one of these:

1. recent exact recall with low latency,
2. old exact recall with fallback to raw archive,
3. pattern/summary over many episodes,
4. stale-update handling,
5. repeated-context orientation,
6. provenance-backed answers.

Hierarchy may not help when:

1. each context is used only once,
2. the question needs exact counting but no counter exists,
3. reflection summarizes away answer-critical details,
4. routing picks the wrong tier,
5. flat grep already finds clean evidence.

## Memory systems to compare

### A. Full context

Paste all memory/context into the prompt. Expensive upper-ish bound, not scalable.

### B. Flat grep

All memory saved as one file. Agent searches with grep/python.

### C. Flat vector/BM25/hybrid retrieval

One flat index over all memory chunks. No hierarchy, maybe recency score as an ablation.

### D. PEEK-style context map

Small prompt-resident map that says what the recurring context contains and how it is organized. It does not store everything.

### E. Virtual context / system evidence packet

System builds a question-conditioned evidence packet before the model answers. This is the current best simple non-RLM arm on our panel.

### F. RLM depth-0

Agent writes code/search over the external source. Current strongest strict baseline on our 250 panel.

### G. Hierarchical memory, no reflection

Deterministic hierarchy only:

- L0: current/recent raw turns
- L1: session/day chunks
- L2: summaries by session/day/topic
- L3: cold raw archive

No LLM memory writer except maybe deterministic extractors.

### H. Hierarchical memory + reflection

Same hierarchy, but an LLM writer promotes/demotes memories:

- raw episode -> session summary
- repeated fact -> semantic fact
- contradicted fact -> updated/stale marker
- important exact fact -> pinned memory

### I. Hierarchical memory + PEEK map

Same as H, plus a small PEEK-like prompt map that tells the agent how the memory system is organized and which tier to query.

### J. Oracle retrieval upper bound

Give the model the gold relevant memory/evidence. This separates retrieval failure from reasoning failure.

## The hierarchy to test

### L0: hot recent memory

Last N turns/sessions in high resolution.

Expected to answer: “What did I say/eat/do last night?”

### L1: warm episodic memory

Recent sessions/days as structured events with timestamps.

Expected to answer: “What happened last week?” or “Where was the file changed two sessions ago?”

### L2: semantic / summary memory

Stable facts, preferences, recurring patterns, project decisions, timelines.

Expected to answer: “What do I usually prefer?” or “What decision did we settle on?”

### L3: cold archive

Full raw logs, slower search, only used when summaries are insufficient.

Expected to answer: “What exactly did I say on April 17?”

### Always-near map

Small prompt-resident orientation cache:

- what tiers exist
- what each tier stores
- known schemas/entities
- which facts are pinned
- retrieval policy hints

## Experiment set 1: controlled synthetic memory age benchmark

Build a synthetic benchmark where gold answers are deterministic.

### Data

Generate fake user memory over 1, 7, 30, 90 days.

Examples:

- meals
- meetings
- tasks
- preferences
- project decisions
- code edits
- repeated habits
- corrections/stale updates

Each event has:

- timestamp
- entities
- type
- importance
- raw text
- optional contradiction/update
- optional repeated pattern

### Query types

| Query type | Example | Expected tier |
|---|---|---|
| recent exact | What did I eat last night? | L0/L1 |
| old exact | What did I eat 30 days ago? | L3 fallback |
| pattern | What do I usually eat for dinner? | L2 |
| temporal change | Did my preference change after X? | L1/L2 timeline |
| stale update | What is my current preference? | L2 with stale handling |
| multi-hop | Which project decision followed the bug report? | L1/L2 |
| abstention | What did I eat on a day never mentioned? | none / calibrated no-answer |
| provenance | Which memory supports this answer? | any tier + citation |

### Variables

- age: 1 day, 7 days, 30 days, 90 days
- memory size: 50, 500, 5000 events
- noise: low/medium/high
- importance: one-off vs repeated vs pinned
- update pressure: no contradiction vs contradiction
- budget: 2k, 8k, 24k prompt/evidence tokens

### Metrics

- exact/semantic answer accuracy
- retrieval recall@k
- correct tier selected
- tool calls / latency
- token cost
- stale-memory error rate
- hallucinated recall rate
- abstention accuracy
- provenance correctness

### Expected result

Hierarchy should beat flat retrieval on pattern, temporal-change, stale-update, and old-exact-with-fallback questions. Flat grep may tie on simple exact recent questions.

## Experiment set 2: PEEK-style repeated context stress test

PEEK should help only when the same context is queried repeatedly. Test that directly.

### Data

Use one recurring context with many questions:

- OOLONG-synth shared context
- OOLONG-real shared transcript
- synthetic personal memory stream
- code repo / SWE-chat session family

### Conditions

Same context, varying number of prior questions before evaluation:

- 0 warmup questions
- 1 warmup
- 2 warmup
- 4 warmup
- 8 warmup
- 16 warmup

### Arms

- flat grep
- PEEK context map
- hierarchy without reflection
- hierarchy with reflection
- hierarchy + PEEK map
- virtual context
- RLM depth-0

### Key plot

Accuracy vs number of repeated queries over same context.

If PEEK/hierarchy is doing what it claims, it should improve as warmup count increases. If not, grep/virtual context may remain stronger.

## Experiment set 3: grep-fail targeted benchmark

Use existing evidence from our 250-task panel.

### Data

Tasks where `grep_file` was wrong but virtual context / structured notes was right.

Existing candidate set:

- `data/benchmarks/confirmation/grep_fail_notes_win_26.jsonl`
- 54 grep-fail/system-evidence-win candidates identified from the 250 panel

### Arms

- grep_file
- CLI-made notes same session
- CLI-made notes two-stage
- structured notes prompt
- virtual context 8k/24k/48k
- hierarchy with event/state tier
- oracle evidence

### Goal

Classify why grep failed:

1. wrong search terms
2. noisy carrier prose
3. stale state
4. missed later update
5. bad ordering
6. counting error
7. final reasoning error despite evidence

### Expected result

If hierarchy helps, it should recover failures caused by stale state / ordering / repeated patterns. If failures are pure exact retrieval, virtual context may be enough.

## Experiment set 4: BABILong state hierarchy

BABILong is useful because it has clean state transitions hidden inside huge carrier text.

### Memory hierarchy variant

- L0 raw text/page windows
- L1 extracted event trace
- L2 current entity/object state table
- L3 raw archive

### Queries

- current location
- object holder
- object location
- before/after location
- yes/no location
- counting movement events

### Arms

- grep
- virtual context event trace
- hierarchy event trace + state table
- hierarchy state table only
- oracle trace

### Expected result

State-table hierarchy should beat generic PEEK and grep on BABILong because the answer often requires latest-state reasoning, not just retrieval.

## Experiment set 5: OOLONG counter hierarchy

OOLONG failures are often counting/event-classification failures.

### Memory hierarchy variant

- L0 raw transcript
- L1 episode-level event tables
- L2 aggregate counters by episode / entity / event type
- L3 raw transcript archive

### Queries

- total rolls by episode
- most common roll type
- natural value count
- first/last spell per character per episode
- cumulative totals

### Arms

- grep
- virtual context windows
- hierarchy with episode event tables
- hierarchy with aggregate counters
- RLM depth-0
- oracle event table

### Expected result

Generic memory hierarchy may not help. Structured counters should help. This tells us whether the hierarchy needs task-specific memory operators.

## Experiment set 6: LongMemEval / LoCoMo-style real memory

Use existing long-term memory benchmarks if available locally.

### Query types to preserve

- information extraction
- temporal reasoning
- knowledge updates
- multi-session reasoning
- abstention

### Arms

- flat retrieval
- recency-weighted retrieval
- PEEK map
- hierarchy with reflection
- hierarchy without reflection
- hierarchy + PEEK map

### Expected result

This is the closest external validation for the human-memory hypothesis.

## Experiment set 7: compaction interaction

Question: does hierarchy reduce compaction loss?

### Conditions

- normal long conversation with auto-compaction
- same conversation with external flat memory
- same conversation with hierarchy
- same conversation with PEEK map
- same conversation with hierarchy + PEEK map

### Evaluation

Ask post-compaction questions:

- exact recent fact
- exact old fact
- updated/stale fact
- project decision
- repeated preference

### Metrics

- answer accuracy after compaction
- whether answer-critical fact survived in prompt/memory
- number of compaction events
- hallucinated recall

### Expected result

Hierarchy should help if answer-critical facts are promoted before compaction deletes them.

## Critical ablations

Run these to avoid fooling ourselves:

1. No cold archive: tests whether summaries lost exact facts.
2. No semantic tier: tests whether pattern questions need abstraction.
3. No recent raw tier: tests whether exact recent recall depends on raw logs.
4. No reflection: tests whether deterministic hierarchy is enough.
5. No provenance: tests hallucination risk.
6. Recency-only ranking: tests whether hierarchy beats simple time weighting.
7. Importance-only ranking: tests whether recency matters.
8. Equal prompt budget: prevent hierarchy from winning only by seeing more tokens.
9. Equal tool-call budget: prevent hierarchy from winning only by doing more work.
10. Oracle router: separates routing failure from memory representation failure.

## Main result table we want

| Arm | Overall | Recent exact | Old exact | Pattern | Update/stale | Counting | Abstention | Cost | Latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full context | | | | | | | | | |
| flat grep | | | | | | | | | |
| flat retrieval | | | | | | | | | |
| PEEK | | | | | | | | | |
| virtual context | | | | | | | | | |
| hierarchy no reflection | | | | | | | | | |
| hierarchy + reflection | | | | | | | | | |
| hierarchy + PEEK map | | | | | | | | | |
| oracle evidence | | | | | | | | | |

## First execution order

### Step 1: tiny synthetic canary

20 memory streams, 5 questions each. Make sure metrics and tiers work.

### Step 2: controlled synthetic full run

500-1000 questions over synthetic age-controlled memory.

### Step 3: repeated-context PEEK stress test

Same context, increasing warmup questions. This directly tests whether PEEK/hierarchy needs repeated use.

### Step 4: grep-fail targeted run

Use existing grep-fail/system-evidence-win tasks and compare hierarchy vs virtual context.

### Step 5: BABILong state-table hierarchy

Build deterministic event/state memory and test exact state queries.

### Step 6: OOLONG event-counter hierarchy

Build episode-level roll/spell counters and test aggregation queries.

### Step 7: LongMemEval / LoCoMo external validation

Run on real long-term memory tasks.

## What would count as a real finding?

### Strong positive

Hierarchy beats flat retrieval and PEEK on old exact, pattern, stale-update, and abstention questions under equal budget, while matching flat grep on recent exact questions.

### Mixed but useful

Hierarchy only helps when it has task-specific operators, e.g. state tables for BABILong and counters for OOLONG.

### Negative but publishable

Hierarchy does not beat flat retrieval once retrieval is strong and budgets are equal. This would mean the hard part is evidence selection, not memory tiering.

### Failure mode finding

Reflection creates false summaries or deletes exact facts. This would support provenance/cold-archive designs.

## Short Slack framing

I think the clean experiment is not “is hierarchy human-like?” but:

> Under equal token/tool budgets, does tiered memory beat flat retrieval as memory gets older and questions shift from exact recall to summaries, updates, and patterns?

We should compare flat grep/RAG, PEEK, virtual context, RLM depth-0, hierarchy without reflection, hierarchy with reflection, and hierarchy + PEEK map. The key plots should be accuracy/cost vs memory age and query type.
