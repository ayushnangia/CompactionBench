# Project context for finding better research questions

This is a context dump / cleaned summary for asking an LLM to help sharpen the research question. The project objective is still not fully clear. There are multiple related threads: compaction, long-context memory, grep/RAG, continual learning, forgetting, LoRA memory, self-distillation, and agent benchmarks.

## Why I am making this

Right now the work has useful experiments, but the objective is fuzzy.

The current experiments show things like:
- compaction drops exact facts
- grep/search can beat full-context prompting in some cases
- paging context into files did not help much
- question-dependent search + notes helps
- RLM depth-0 helps exact lookup
- OOLONG needs counting/event logic, not just retrieval

But the bigger project could go in several directions:
- compaction as memory loss
- retrieval vs full context
- agent memory systems
- continual learning without training
- continual learning with LoRA / finetuning / replay
- benchmarks for forgetting and memory
- task-specific memory operators

So I want to use this doc to ask an LLM: what are the best research questions here?

## Short project history / current thread

The original direction was:

> understand compaction for large context, 128k to 1M+ and beyond, and how it affects a model's ability to answer after context compression.

Main idea:

> When context is compressed, what exact information survives and what disappears?

Especially:
- names
- numbers
- places
- object bindings
- file state
- user/project state
- event counts
- first/last events

This later expanded into long-context memory more broadly:
- full context
- file grep
- paging
- search + notes
- RLM/code-over-context
- retrieval/RAG
- external memory systems
- continual learning benchmarks

## Important empirical findings so far

### 1. Compaction keeps vague story but drops exact state

From BABILong compaction experiments:
- the model often keeps the rough story
- but drops exact details like object, place, name, number, binding
- example style: keeps “Mary moved around” but drops “Mary is in the bathroom”

This suggests compaction is not just shortening text. It is selectively destroying state.

Possible framing:

> Auto-compaction creates a lossy memory bottleneck where exact answer-critical facts disappear before vague semantic gist.

### 2. Question-aware compression helps

Small sanity check:
- without the target question, compression kept wrong facts: 0/5 correct
- with the question known, compression kept right facts: 3/5 correct
- vague hints like “find the current value” also helped almost as much as exact question

Possible framing:

> Compression quality is not absolute. It depends on the future task. Question-aware memory can preserve the right state better than blind compression.

### 3. Stronger raw model does not automatically mean compression robustness

Observation:
- GPT-5.4 handles raw long context well
- after compression, it fails similarly to smaller model

Possible direction:
- test if general model intelligence / benchmark score correlates with compaction resilience
- or if compression is a separate bottleneck

### 4. Grep/search is a strong baseline

Inspired by “Is Grep All You Need?” and direct corpus interaction papers.

Fixed real BABILong + OOLONG panel, no compaction:
- full context: 36/250 strict
- file grep: 52/250 strict
- model picks pages: 37/250 strict
- search + notes / old virtual context: 59-62/250 strict, best relaxed 99/250
- RLM depth-0: 74/250 strict, best exact score
- RLM depth-1 recursive: 47/250 strict, slower and worse

Interpretation:
- file grep is a strong simple baseline
- just splitting into pages and making the model pick pages did not help
- search + notes works better because the source is searched before answering and the model sees only useful snippets/facts
- RLM depth-0 works well for exact lookup because the model can write code/search over external context
- RLM depth-1 recursion worked technically, but did not improve results here

### 5. OOLONG shows retrieval is not enough

OOLONG has D&D transcript/event questions requiring counting, first/last, and aggregation.

Observation:
- grep/full context/search notes are all weak on OOLONG
- child RLM calls also miscount roll/spell events

Possible framing:

> Some long-context tasks are not retrieval tasks. They need structured event extraction and counting.

### 6. SWE-chat needs semantic scoring

SWE-chat outputs may include code examples or different phrasing.
Exact string match is too harsh.

Need:
- judge scoring
- semantic scoring
- maybe task-specific rubrics
- file/state tracking metrics

## Broader continualbench / related-work context from Slack

This channel has multiple related threads. Need to decide what belongs in the project and what is just background.

### A. LoRA / parametric memory

Paper:
- Understanding LoRA as Knowledge Memory: An Empirical Analysis
- https://arxiv.org/abs/2603.01097

Why it might matter:
- LoRA can act like modular knowledge memory
- may be complementary to ICL and RAG
- could be another memory mechanism besides context/retrieval

Question:
- Is project about non-parametric memory only, or also parametric memory like LoRA?

### B. Forgetting / post-training drift

Paper:
- CapTrack: Multifaceted Evaluation of Forgetting in LLM Post-Training
- https://arxiv.org/abs/2603.06610

Why it matters:
- forgetting should not be only factual accuracy loss
- it can be behavior/capability drift
- this connects to compaction forgetting: not just fact loss but user experience degradation

Possible connection:
- build a capability-centric taxonomy for context compaction failures
- not just exact answer accuracy

### C. Fine-tuning without forgetting / expansion

Paper:
- Grow, Don't Overwrite: Fine-tuning Without Forgetting
- https://www.alphaxiv.org/abs/2603.08647

Why it matters:
- capacity expansion can preserve original model behavior during adaptation
- different from context memory, but same high-level goal: add new knowledge without overwriting old capability

Question:
- Is the project about inference-time memory only, or continual learning broadly?

### D. Replay and adaptive memory

Paper:
- MSSR: Memory-Aware Adaptive Replay for Continual LLM Fine-Tuning
- https://www.alphaxiv.org/abs/2603.09892

Why it matters:
- replay is a training-time memory mechanism
- could compare with context memory: what should be stored/replayed vs retrieved/compacted?

### E. Fast-weight / continual learning attention

FALCON tweet:
- Fast-Weight Attention for Continual Learning
- https://x.com/yifan_zhang_/status/2033412156939505944?s=20

Why it matters:
- another memory mechanism between context and weights
- possible long-term direction, not immediate benchmark work

### F. Self-distillation / SDFT / SDPO / OPSD

Relevant links:
- self-distillation replication: https://github.com/ayushnangia/Self-Distillation/blob/main/REPLICATION_REPORT.md
- Paras negative results: https://github.com/paraschopra/self-distillation-experiment
- SDFT discussions had reproducibility concerns
- SDPO: https://arxiv.org/abs/2601.20802
- OPSD: https://arxiv.org/abs/2601.18734

Status from Slack:
- baseline/degradation after training looked better than SFT in some runs
- later runs showed SDFT may preserve benchmark average better than SFT, but config selection may be questionable
- authors clarified FKL token-level setup
- concern that more resources into SDFT paper may not be useful due to reproducibility/gaming issues

Possible connection:
- self-distillation as a continual learning mechanism
- but likely separate from current compaction/retrieval project unless the RQ becomes training-time memory

### G. Out-of-context reasoning / multihop reasoning

Links:
- https://www.lesswrong.com/posts/PPDuLtqCtpqmGzEzH/owain-evans-on-situational-awareness-and-out-of-context
- https://outofcontextreasoning.com/
- continual eval dataset: https://huggingface.co/datasets/ruggsea/continual-eval

Why it matters:
- multi-hop reasoning across separated facts is a memory/generalization challenge
- reasoning models may solve some cases better

Observation from Slack:
- need better model than Llama for a -> b -> c hops
- sometimes structure is a -> b <- c, so simple chain assumption is wrong

Possible connection:
- compaction/retrieval can drop intermediate hops
- test whether memory systems preserve multi-hop dependencies

### H. Memorization

Paper:
- Hubble: a Model Suite to Advance the Study of LLM Memorization
- https://arxiv.org/abs/2510.19811

Why it matters:
- model memorization is another kind of memory
- could separate what model knows parametrically vs what it needs from context

Possible direction:
- compaction may interact with model prior/memorized knowledge
- need tests where answer cannot come from pretraining

### I. Continual Learning Bench

Link:
- https://continual-learning-bench.com/

Slack notes:
- talked to folks behind benchmark
- strategy is to release tasks and have people compete
- tasks include codebase adaptation and sales prediction
- reward/feedback steers model direction over time
- they are also working on compaction and memory instead of only training
- ran 6 tasks with compaction pipeline
- model got 0% exact match, around 16% semantic scoring
- tasks are code/logic generation based on data, not just retrieval
- sales/cohort tasks are DB-based with SQLite, so logical errors can be traced and scored

Why it matters:
- more realistic continual-agent setting than BABILong
- may be useful if project moves toward agent adaptation/memory over sequential tasks

### J. Real long-context datasets considered

Datasets mentioned:
- LongMemEval-V2: long-term chat memory
  - https://github.com/xiaowu0162/LongMemEval-V2
- MIMIC-IV: clinical notes across years
- MS MARCO: real Bing queries
- DialogSum: real dialogues
- LegalBench: legal reasoning
- QMSum: meeting transcripts
- SWE-chat: real coding agent sessions
- OOLONG: long-context reasoning/aggregation
- CorpusQA by Qwen

Current practical set:
- BABILong
- OOLONG-real
- SWE-chat
- LongMemEval rendered/subset

## The project objective is unclear right now

There are at least 5 possible objectives:

### Objective 1: Compaction failure science

Study how auto-compaction loses answer-critical state.

Core RQ:
> What information is systematically lost during LLM context compaction, and can question-aware hints preserve answer-critical state?

Pros:
- closest to original project
- existing results support it
- concrete failure mode: exact facts vanish before gist

Cons:
- may need deeper mechanistic analysis or stronger metrics to be surprising

### Objective 2: Long-context memory operators

Study which memory operation works for which task type.

Core RQ:
> Long-context tasks require different memory operators. Which tasks need lookup, notes, paging, counters, or code-over-context?

Pros:
- explains grep/paging/RLM results
- connects to “Is Grep All You Need?”
- practical for agents

Cons:
- broader and may need careful taxonomy

### Objective 3: Retrieval vs full context vs vector DB

Directly test whether grep is enough.

Core RQ:
> Under the same agent setup, when does lexical search beat embeddings/vector retrieval/full context for long-context agent tasks?

Pros:
- timely due to grep paper/tweet
- easy story

Cons:
- may be too narrow and not novel enough unless benchmarks are strong

### Objective 4: Continual agent memory without training

Study how agents should persist memory across long tasks/sessions using context/search/notes.

Core RQ:
> Can inference-time memory systems replace or complement continual fine-tuning for adapting agents over sequential tasks?

Pros:
- connects to Continual Learning Bench
- practical
- avoids expensive training

Cons:
- big scope

### Objective 5: Training-time continual learning / forgetting

Study LoRA, self-distillation, replay, expansion, etc.

Core RQ:
> Which training-time methods add new knowledge without forgetting old capabilities?

Pros:
- many papers and active area

Cons:
- less connected to current compaction experiments
- reproduction issues / expensive
- may distract from current evidence

## Candidate research questions to ask LLM to evaluate

1. What kinds of facts are lost during LLM context compaction, and can question-aware compression preserve answer-critical state?

2. Is long-context failure mostly a retrieval problem, a compression problem, or an aggregation/counting problem?

3. For long-context agent tasks, which memory operator is needed: full prompt, grep, paging, search + notes, code search, or structured counter?

4. When does simple lexical search beat full-context prompting and embedding retrieval for agent memory?

5. Can question-conditioned search + notes act as a cheap alternative to RAG/vector DBs for long-context QA?

6. Why does paging fail: does the model choose wrong pages, or does it fail even after finding the correct page?

7. Can structured event extraction close the gap on OOLONG where retrieval and RLM recursion fail?

8. Does compaction preserve semantic gist but destroy exact state, and can this be measured with entity/binding retention metrics?

9. Can a capability-centric forgetting framework like CapTrack be adapted from post-training to context compaction?

10. Are RLMs useful as an out-of-the-box memory backend for exact lookup compared to grep and full context?

11. Does model intelligence correlate with compaction robustness, or is compaction a separate bottleneck?

12. In continual-agent tasks, is inference-time memory enough, or do we need parametric updates like LoRA/replay?

## My current best framing

Best current direction seems to be:

> Long-context memory is not one thing. Different tasks need different memory operators, and compaction fails when it destroys the operator-relevant state.

Possible paper/blog title style:

> Beyond Grep and Prompt Stuffing: A Task Taxonomy for Long-Context Agent Memory

or

> What Should Long-Context Agents Remember? Measuring State Loss Across Compaction, Search, Paging, and Code Memory

## Concrete next experiments if we choose memory-operator framing

### 1. Task taxonomy

Label each task by required memory operation:
- exact lookup
- entity binding
- multi-hop lookup
- first/last event
- count/aggregate
- code/file state
- semantic answer

### 2. Retrieval baselines

Compare on same panel:
- full context
- grep
- BM25
- embeddings/vector DB
- hybrid
- search + notes
- RLM depth-0

### 3. Search + notes ablations

Test:
- raw snippets vs cleaned notes
- question-dependent notes vs generic summary
- note budget sizes
- with/without nearby context
- with/without reranking

### 4. Paging diagnostics

Test:
- model picks pages
- oracle correct page given
- better page previews
- measure wrong-page vs wrong-answer failures

### 5. OOLONG structured counter

Build:
- roll/spell event extractor
- first/last event logic
- count verifier

Then compare:
- full context
- grep
- search + notes
- RLM
- structured counter + retrieval

### 6. Compaction reconnect

Compare:
- raw context
- auto-compaction
- explicit compression
- question-aware compression
- search + notes

Measure:
- exact entity retention
- binding retention
- number retention
- answer-critical fact retention
- accuracy after compression

## Prompt to ask another LLM

Use this prompt with the context above:

```text
I am exploring long-context memory and compaction for AI agents. I have experiments on BABILong, OOLONG, SWE-chat, and LongMemEval. I tested full context, file grep, paging, question-dependent search + notes, and Recursive Language Models. I also have broader related work around continual learning, LoRA as memory, forgetting, replay, self-distillation, out-of-context reasoning, and Continual Learning Bench.

The project objective is not clear. Please help me sharpen it into 3-5 strong research questions. For each RQ, tell me:
1. why it is interesting,
2. what my current evidence supports,
3. what experiments are missing,
4. what would be a crisp claim if the experiments work,
5. what to avoid because it is too broad or already known.

Prefer research questions that are testable with my current benchmark infrastructure and can lead to a clear paper/blog/report.
```
