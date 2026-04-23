# Plan: A simple benchmark for long-context compaction in agents

## The short version

This project asks one plain question:

> If we give a very long task to a real agent system, and that system has to shrink or compress its old context, does it still remember the right things at the end?

That is the whole idea.

We care about this because many real systems now work like agents:
- coding assistants,
- research assistants,
- chat assistants,
- document tools,
- and future systems that track long streams of information over time.

These systems do not always keep the full raw history forever. At some point they often **compact** the context: they shorten it, summarize it, or drop parts of it so the run can keep going.

That may be necessary. But it also creates a risk:

- the system may keep the **gist**,
- while losing the **exact fact**,
- the **latest update**,
- or the **small detail** that actually matters.

This project tries to measure that failure in a clean way.

---

## Why this matters

A model may claim a very large context window.
That is useful, but it is not the whole story.

In real use, what matters is not just:

> “Can the model read 1M tokens?”

It is also:

> “Can the full system still answer correctly after a long, messy, multi-turn run?”

Those are different questions.

A real agent has:
- a model,
- a harness around the model,
- a chat history,
- maybe tools,
- and often some rule for handling too much context.

So if we want to understand memory in practice, we should measure the **whole system**, not just the raw model in isolation.

That makes this project useful for agent work.
It also makes it useful beyond agents, because many future systems will have the same problem: too much history, too little room, and a need to decide what to keep.

---

## The core idea of the benchmark

The setup is very simple on purpose.

We do this:

1. Take a benchmark example with a long context.
2. Split the context into chunks.
3. Feed those chunks into a live agent session over many turns.
4. Ask one final question at the end.
5. Record whether the answer is right.
6. Record whether context compaction happened along the way.

That is it.

This is almost boring by design. That is a good thing.
A benchmark is easier to trust when the path from input to answer is easy to explain.

---

## What we are trying to learn

We want to answer questions like these:

- What breaks first when context gets compacted?
- Do systems lose exact facts before they lose general meaning?
- Are temporal details more fragile than simple facts?
- Are counting and aggregation harder than one-shot retrieval?
- Does more reasoning help, or does it just make the context messier?

These are useful questions for both science and engineering.

For science, they tell us what kind of memory is actually being preserved.
For engineering, they tell us how to build better agent systems.

---

## The experiments are simple

### Experiment 1: exact fact memory
Use a benchmark where the system must remember the exact right fact after a long context.

If the system answers wrong, we can ask:
- Did it forget the fact?
- Did it mix up two entities?
- Did it keep an old state instead of the newest one?

This is the role of **BABILong** in our setup.

### Experiment 2: many-small-facts aggregation
Use a benchmark where the system must process many local facts and combine them into one final answer.

If the system answers wrong, we can ask:
- Did it fail to keep enough pieces?
- Did it fail to count or aggregate correctly?
- Did it lose temporal structure?

This is the role of **OOLONG** in our setup.

### Experiment 3: compare both under the same compaction settings
Run both kinds of tasks with the same models and the same compaction settings.

Then we can see whether compaction hurts:
- exact recall,
- aggregation,
- temporal reasoning,
- or all of them in different ways.

This comparison is one of the most useful parts of the project.

---

## Why these benchmarks

### BABILong
BABILong is a good test for exact long-context memory.

It is useful because:
- answers are clear,
- many tasks are easy to score,
- and it stresses facts spread across long text.

In plain words, BABILong helps us ask:

> Did the system keep the exact thing it needed?

That makes it very good for studying compaction.

### OOLONG
OOLONG is a good test for long-context aggregation.

It is useful because:
- it is not just “find one needle,”
- it includes counting,
- user-based grouping,
- and timeline questions.

In plain words, OOLONG helps us ask:

> Did the system keep enough structure to combine many small pieces into one correct answer?

That makes it a strong partner to BABILong.

### RULER
RULER is still useful as a simple retrieval-style baseline.

It helps us check whether the system can do the easier kind of long-context work before we move to harder memory and aggregation tasks.

---

## What has been built so far

We already have a working benchmark pipeline.

### The pipeline now does this
- prepares tasks as clean JSONL rows,
- runs direct multi-turn injection into Codex or Claude Code,
- records run artifacts,
- records compaction events,
- scores results deterministically,
- and supports a secondary judge pass when needed.

### Important engineering progress
We also fixed a practical but important problem:
- Codex does emit compaction events,
- but they were not always being parsed correctly at first,
- so we updated the parser to recover those events from both the live stream and saved session logs.

This matters because without that fix, we would be measuring answers but not the context-management events that likely shaped those answers.

---

## Progress so far

### 1. BABILong qa1–qa10
This full sweep is done.

What it gave us:
- a clean end-to-end test of the pipeline,
- real compaction events,
- and clear performance drop-off as length grows.

This was important because it showed that the project is not just an idea anymore. It already produces measurable system behavior.

### 2. BABILong qa11–qa20
This extended sweep is also done.

This matters because it adds more task types, including:
- coreference,
- time reasoning,
- deduction and induction,
- positional reasoning,
- path finding,
- motivations.

So we now cover much more than just the first few BABILong tasks.

### 3. OOLONG integration
OOLONG is now wired into the same pipeline.

That means we can prepare OOLONG tasks, run them through the same direct injection setup, and score them with task-appropriate rules.

### 4. OOLONG-synth long set prepared
We now have a prepared OOLONG-synth long-context set with:
- `128k`, `256k`, `512k`, and `1M`,
- task groups `counting`, `user`, and `timeline`,
- 3 samples per group per length.

So the next step is no longer setup. It is running and analyzing.

---

## What we are already learning

Even at this stage, a few things are becoming clear.

### First lesson: long context is not one problem
There is a big difference between:
- finding one fact,
- remembering one exact state,
- and combining many facts into one answer.

A system may do okay on one and badly on another.

### Second lesson: the harness matters
The outer system around the model matters.

If the harness compacts, summarizes, or evicts context, then the final behavior is not only about the model’s raw window size.
It is about what survives that process.

### Third lesson: failure is often subtle
The system does not always fail by saying something random.
Sometimes it gives a plausible answer that is almost right, but not exact.

That is a very important failure mode for real agents.
A confident near-miss can be more dangerous than an obvious failure.

---

## Why this is fruitful for agents

This project is useful for agents because agents live in long histories.

A short one-shot QA system may not hit the same problem.
But an agent often does all of the following:
- reads a lot,
- acts over many turns,
- keeps notes or tool outputs,
- revisits old facts,
- and keeps going even after the context gets crowded.

So agents need some way to manage context.
And once they manage context, memory quality becomes a systems question.

That is exactly where this project sits.

### Why this matters for coding agents
A coding agent may need to remember:
- what file changed,
- what assumption was made earlier,
- what bug was already ruled out,
- what the latest design decision was.

If compaction keeps only a vague summary, the agent may look smart while repeating old mistakes.

### Why this matters for research agents
A research agent may need to remember:
- which paper said what,
- which result was stronger,
- what limitation was already noted,
- what question is still open.

If compaction drops the exact source or exact claim, the final synthesis gets weaker.

### Why this matters for personal assistants and chat systems
These systems often need:
- long-term preferences,
- updates over time,
- knowledge corrections,
- and abstention when memory is uncertain.

So this work also lines up with long-term assistant memory questions.

---

## Why this matters beyond agents

Even if one does not care about coding agents, the same problem appears in any long-running system that needs memory.

A future system may need to track:
- news,
- legal documents,
- support tickets,
- project logs,
- medical notes,
- or multi-day conversations.

All of these create the same core challenge:

> Too much history must be reduced somehow, but the right facts still need to survive.

That makes this project broader than one harness or one model.

---

## Connection to InfiniNews

From our discussions, **InfiniNews** is not something we should present as an established benchmark paper.
Instead, it is best understood as a promising future direction: a Common Crawl–based news-style benchmark with multi-hop reasoning.

That is a very natural next step for this project.

### Why the connection is strong
A news-style benchmark would need systems to:
- track people, places, and events across many pieces of text,
- connect evidence across articles,
- deal with corrections and updates,
- answer temporal questions,
- and combine many small facts into a useful answer.

That lines up almost perfectly with what we are already measuring.

### How the current work helps
- **BABILong** helps with exact fact tracking and state updates.
- **OOLONG** helps with aggregation and temporal questions.
- The harness setup helps test what survives after long runs and compaction.

So this project can act like a clean stepping stone toward an InfiniNews-style benchmark.

---

## What makes this project different from nearby work

A lot of prior work looks at one of two things:

1. raw long-context model ability,
2. or clever memory/compression methods.

This project is a little different.

It asks:

> What happens in a real running system when context management is part of the loop?

That may sound modest, but it is very practical.
And practical work is often where benchmark results become useful.

---

## Related work in plain English

### BABILong
BABILong tests whether a model can reason across facts spread over very long text.

Why it matters here:
- it is a strong test of exact long-context factual memory.

Reference:
- Kuratov et al., *BABILong: Testing the Limits of LLMs with Long Context Reasoning-in-a-Haystack*  
  https://arxiv.org/abs/2406.10149

### RULER
RULER goes beyond the very simplest “needle in a haystack” test.

Why it matters here:
- it is a useful retrieval-style baseline.

Reference:
- Hsieh et al., *RULER: What's the Real Context Size of Your Long-Context Language Models?*  
  https://arxiv.org/abs/2404.06654

### OOLONG
OOLONG studies long-context aggregation.

Why it matters here:
- it is closer to “many little steps must add up correctly,” which is very relevant for agents.

Reference:
- Bertsch et al., *Oolong: Evaluating Long Context Reasoning and Aggregation Capabilities*  
  https://arxiv.org/abs/2511.02817

### LongMemEval
LongMemEval studies long-term interactive memory in assistants.

Why it matters here:
- it reminds us that memory is not only about one big prompt; it is also about history across interaction.

Reference:
- Wang et al., *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*  
  https://arxiv.org/abs/2410.10813

### MemGPT
MemGPT treats memory like a systems problem, with different memory tiers.

Why it matters here:
- it is a strong example of the idea that limited active context can be managed, not just suffered.

Reference:
- Packer et al., *MemGPT: Towards LLMs as Operating Systems*  
  https://arxiv.org/abs/2310.08560

### MEMENTO
MEMENTO teaches models to manage their own context by breaking reasoning into blocks and summarizing those blocks.

Why it matters here:
- it is very close in spirit to our question,
- but from the model side instead of the harness side.

A simple contrast is:
- **MEMENTO**: can the model learn to compress its own reasoning well?
- **our project**: does a real agent system still work well after harness-level compaction?

Reference:
- Kontonis et al., *MEMENTO: Teaching LLMs to Manage Their Own Context*  
  https://github.com/microsoft/memento/blob/main/docs/memento.pdf

### ACON
ACON studies context compression for long-horizon agents.

Why it matters here:
- it is another sign that context compression is becoming a central agent problem, not a niche one.

Reference:
- *ACON: Optimizing Context Compression for Long-horizon LLM Agents*  
  https://arxiv.org/abs/2510.00615

---

## What we should claim carefully

We should be ambitious, but not magical.

### It is fair to say
- We now have a working system for measuring harness-level long-context compaction.
- We have evidence that compaction events happen in real runs and can be logged.
- We can now compare exact memory tasks and aggregation tasks under the same settings.
- This is directly useful for understanding agent behavior.

### It is not fair to say yet
- That we have solved long-context memory.
- That every failure is caused by compaction.
- That news-style or long-horizon real-world performance is already fully covered.
- That one benchmark result settles the question.

That honest framing is important.

---

## Immediate next steps

1. Run the prepared **OOLONG-synth** sweep under the same Codex settings as BABILong.
2. Score the OOLONG run and compare it to BABILong.
3. Finish the richer analysis for the extended BABILong runs.
4. Write a short summary of what fails first:
   - exact fact memory,
   - temporal reasoning,
   - aggregation,
   - parse failures,
   - and compaction-linked failures.
5. Use that as the base for thinking about an **InfiniNews-style** downstream benchmark.

---

## One clean way to explain the whole project to an advisor

Here is the simplest version:

> We are studying what happens when a real agent system has to shrink its own long context. Instead of only asking whether a model can read a long prompt, we ask whether the full running system still keeps the right information after compaction. We use BABILong for exact fact memory and OOLONG for aggregation over many facts. This is useful for coding agents today and for future long-running systems, including possible news-style multi-hop benchmarks such as InfiniNews.

That is the project.
It is simple, grounded, and useful.
