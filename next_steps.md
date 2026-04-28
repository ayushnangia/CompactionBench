# What is next

We have a benchmark that works. We have early results. Now we need to make the results mean something.

---

## Where we are

We built CompactionBench to test one simple thing: when Codex compresses a very long conversation, does it remember the right details?

So far we found:

1. **Compaction is real.** It kicks in around 256k+ tokens. Before that, nothing happens. After that, the model starts compressing its own history.

2. **BABILong is harsh.** The model often keeps the rough story but loses the exact word, place, number, or binding needed. Exact accuracy was around 8%. Even with a judge giving partial credit, it was around 39%.

3. **OOLONG is cleaner.** When the task is about aggregating many small facts rather than recovering one exact fact, the model does better (46% accuracy) and the benchmark is more reliable.

4. **Task type matters a lot.** Some question types survive compaction much better than others. Coreference and basic supporting facts sometimes survive. Exact objects and locations often do not.

But none of this yet tells us **why** this happens or **what to do about it**.

---

## The question we still need to answer

> If we change what gets compressed and preserved, does the agent remember the right things more often?

Paras was right: the results are hard to interpret without a clearer mechanism. Right now we only know that the agent fails. We do not yet know if a different compression policy would help.

So the next step is to test that.

---

## What we will actually do next

### Step 1: Make tiny synthetic tasks

These are short, controlled tasks that isolate one thing.

| Task | What it tests |
|---|---|
| Stale update | Does the model remember the latest value, or an old one? |
| Entity binding | Does the model remember which ID belongs to which project? |
| Counting | Can the model count events across a long context? |

We keep these tiny so results are easy to understand.

### Step 2: Compare compression policies

We take the same raw context and compress it in different ways before giving it to Codex.

| Policy | What it does |
|---|---|
| Raw (no compression) | Give the model everything and let it auto-compact |
| Static compression | Keep facts in a simple structured format |
| Entropy compression | Keep facts that look rare, novel, or important |

We test both cases: one where the compressor sees the question and one where it does not.

Seeing the question is easier. Not seeing the question is closer to real agent work.

### Step 3: Track what actually happened

For each run, we check:

- Did the answer match the correct answer?
- Did the important fact survive in the compressed version?
- How much was the context compressed?
- Which task types improved? Which got worse?

### Step 4: Decide what to do next

If compression helps: we sharpen the question and try DSPy/GEPA optimization later.

If compression does nothing: we stop and reconsider.

If compression helps some tasks but hurts others: we pivot and study which tasks are compressible.

---

## Why this order

We are not starting with DSPy or GEPA right away. We are not building a full memory system.

We are starting with one simple comparison:

```text
raw context + auto-compaction
vs
compressed context + auto-compaction
```

If that comparison shows nothing, then fancy optimization will not fix it. If it shows something, then we know there is a real effect worth optimizing.

---

## What we need to run it

- 3 tiny synthetic task types
- 3 compression policies
- 2 modes (query-aware, query-blind)
- maybe 5 samples each

That is about 30 to 90 small runs. Not a full benchmark sweep.

We do this on `gpt-5.4-mini` first because it is cheap and fast. If we see a clear signal, we add `gpt-5.4`.

---

## What we will have at the end

A simple answer to one question:

> Does changing how we compress context change what the model remembers?

Plus a decision:

- Yes → become a real research question
- No → shelve or try something else
- Yes but only for some tasks → study which tasks benefit

---

## Also still needed

These are things we know we need to fix, separate from the compression experiment:

1. **Rerun the broken BABILong qa11–q20 cells.** 66% of those runs hit usage limits. We cannot claim results from a batch that is mostly errors.

2. **Run OOLONG-real.** OOLONG-real uses real transcripts and is closer to real agent conversations. We have the code but not the full batch.

3. **Write one clean result memo.** The results are spread across many files. We need one document that anyone can read in 5 minutes.

These should happen after we get the first compression result, because the compression result is what makes the project a project and not just a collection of data.

---

## In short

The next step is not more sweeps. It is one small test of one simple idea:

> If we preserve different information, does the model perform differently?

If yes, the project has a clear direction. If no, we know that too.

Either way, we stop guessing and start knowing.
