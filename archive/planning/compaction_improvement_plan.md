# Compaction — Motivation and Improvement Plan

## Why study compaction

### The real problem

Coding agents run for hundreds of turns. The context window fills up. The system compresses the history to keep going. But the agent still sounds confident. It just remembers the wrong thing.

This is not a theoretical concern. It is the default behavior of every long-running agent. SWE-chat shows real developers having 260-290 turn conversations. Codex auto-compacts these sessions silently. The user never knows what was lost.

### What we found

1. **Compaction destroys exact facts but keeps the story.** BABILong shows a large gap between what is in context and what the model can retrieve. OOLONG shows aggregation survives better than exact recall.

2. **Compression without a goal is blind.** Query-blind compression picks wrong facts every time. Query-aware compression matches raw performance. A weak task-type hint nearly matches knowing the full question.

3. **Smarter models do not fix it.** GPT-5.4 counts perfectly with full context. After compression, it fails completely. Intelligence cannot recover deleted information.

4. **Tools can help.** Giving the model a file and letting it grep recovers accuracy from 43% to 60%. Keeping original data accessible matters more than perfect compression.

### Who cares

- People building coding agents (Codex, Claude Code, pi.dev, OpenCode)
- Researchers working on agent memory (MEMENTO, ACON)
- Anyone running long-context models at scale
- Continual learning researchers (CLB team)

---

## Where we can improve

### 1. Compression policies need a relevance signal

**Finding:** Query-blind = 0/5. Query-aware = 3/5. Weak-hint = matches query-aware.

**Improvement:** Build a task-classifier that labels each turn ("code question," "file path," "decision," "update"). Feed these labels to the compressor. The compressor does not need the exact future question. It needs to know the task type.

**Experiment:** Train/use a small classifier to label conversation turns. Compare task-labeled compression vs query-aware compression.

### 2. Keep original data accessible

**Finding:** Grep on the original file beats injected context (60% vs 43%).

**Improvement:** When compressing, keep a structured index: file paths, function names, variable names, error messages. Store these as a compressed ledger rather than a prose summary. Let the model grep the ledger.

**Experiment:** Build a "compressed ledger" format: entity list, file path index, decision log. Compare against raw compression on BABILong and SWE-chat.

### 3. Semantic scoring for code tasks

**Finding:** CLB tasks and SWE-chat score 0% on exact match but model clearly understands the task. Format mismatch, not failure.

**Improvement:** Use ROUGE, BLEU, and LLM-as-judge for code generation tasks. Different scoring for different task types.

**Experiment:** Build a scoring pipeline that selects the right scorer per task type. Compare binary vs semantic vs judge accuracy across all benchmarks.

### 4. Budget-aware compression

**Finding:** At 200 tokens budget, counting is destroyed (5/5 → 0/5). At higher budgets, counting might survive.

**Improvement:** Measure the compression budget curve: what accuracy do we get at 50, 200, 500, 1000, 2000 tokens? Find the minimum budget for each task type.

**Experiment:** Budget sweep on BABILong and OOLONG. Identify the inflection point where accuracy recovers.

### 5. Tool-use-aware compression

**Finding:** The model can use grep to recover information. But it does not always run the right grep command.

**Improvement:** During compression, record what grep commands would find each fact. Store these as "recovery hints" in the compressed context.

**Experiment:** Compress with recovery hints. After compaction, the model sees: "To find X, grep for Y." Compare accuracy against raw compression and against grep-only.

### 6. Information-theoretic selection

**Finding:** Entropy-based compression uses simple heuristics (rarity, entities, numbers). LLMLingua-2 shows these can be suboptimal.

**Improvement:** Use a small model to score each sentence by "answer probability" rather than token rarity. The score measures "how likely is a future question to need this sentence?"

**Experiment:** Fine-tune a tiny classifier on BABILong training tasks to predict which sentences contain gold answers. Use this as a compression selector.

---

## Priority plan

### Week 1: Recovery via tools
Prove that tool-accessible compression beats pure context compression. Run grep experiment on all BABILong lengths. Build the compressed ledger format.

### Week 2: Task-type hints
Scale the weak-hint experiment to 50 tasks. Prove that task-type labels match full question awareness.

### Week 3: Budget sweep
Find the minimum compression budget for each benchmark. Identify the point where information loss becomes irreversible.

### Week 4: Write-up
Consolidate findings. Publish a technical report: "CompactionBench: Diagnosing and Fixing Context Compression in Long-Running Agents."

---

## Related work

- MEMENTO: Compresses reasoning traces into compact summaries for long-horizon agents. [microsoft/memento](https://github.com/microsoft/memento)
- ACON: Optimizes compression for long-horizon agents. [arXiv:2510.00615](https://arxiv.org/abs/2510.00615)
- LLMLingua / LongLLMLingua: Prompt compression with token-level and query-aware methods. [arXiv:2310.05736](https://arxiv.org/abs/2310.05736), [arXiv:2310.06839](https://arxiv.org/abs/2310.06839)
- Selective Context: Self-information based content filtering. [arXiv:2304.12102](https://arxiv.org/abs/2304.12102)
- BABILong: Long context reasoning benchmark. [arXiv:2406.10149](https://arxiv.org/abs/2406.10149)
- OOLONG: Long context aggregation benchmark. [arXiv:2511.02817](https://arxiv.org/abs/2511.02817)
- SWE-chat: Real coding agent conversations. [SALT-NLP/SWE-chat](https://huggingface.co/datasets/SALT-NLP/SWE-chat)
- Continual Learning Bench: Sequential agent tasks across episodes. [pgasawa/continual-learning-bench](https://github.com/pgasawa/continual-learning-bench)
