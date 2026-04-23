# Exploration Sprint: Tiny notebook vs default compaction

## BEFORE YOU START

### The What-If
I wonder whether a tiny structured notebook inside the agent loop will rescue exact long-context memory much better than default auto-compaction does.

More simply:

> What would happen if the agent kept a tiny running note of "what matters now" while the harness compacts the rest?

### Why this, why now?
This came from our current results.

What we saw:
- **BABILong** is very bad under strict exact scoring.
- **OOLONG-synth** is much better and much cleaner operationally.
- Compaction clearly starts around **256k**.
- Many BABILong failures look like the system keeps the rough idea, but loses the exact symbolic answer.

That suggests default compaction may be better at keeping:
- gist,
- rough semantics,
- broad task structure,

than keeping:
- exact state,
- exact bindings,
- latest correction,
- exact entity-to-fact links.

So the next curiosity is:

> Maybe the problem is not that long context is impossible. Maybe the problem is that the memory format is wrong.

---

## EXPECTATIONS

### What do you expect to observe?
I expect that adding a tiny notebook will:

1. **Help BABILong more than OOLONG**
   - especially on tasks that need exact state
   - especially at `256k` and `1M`

2. **Help exact-memory tasks more than aggregation tasks**
   - biggest gains on:
     - single supporting fact / latest fact style tasks
     - coreference
     - time-update tasks
   - smaller gains on:
     - counting
     - broad aggregation
     - user grouping

3. **Not help everything**
   - I do **not** expect it to magically fix path finding or deep structured reasoning
   - I expect it to help most when the failure is memory loss, not when the failure is reasoning itself

### Why do you expect this?
Because our current results already hint at a split:
- **BABILong** says exact memory is brittle
- **OOLONG** says broader aggregation is more survivable

That suggests the system often remembers:
- a summary of what happened

but not:
- the exact piece of state we needed

A notebook is a simple way to test that idea.

If the notebook helps a lot, then the likely story is:
- the harness's default compaction keeps the wrong kind of memory

If it does not help, then the likely story is:
- the problem is deeper than memory format

Either way, we learn something useful.

### What would genuinely surprise you?
Two things would make me stop and say **"wait, that's weird."**

#### Surprise 1
**The notebook helps OOLONG a lot, but barely helps BABILong.**

That would be strange because I currently think the notebook should mostly help exact state.

If this happens, maybe the real issue is not exact symbolic loss, but better task decomposition or better stabilization of long reasoning.

#### Surprise 2
**The notebook hurts performance.**

That would also be very interesting.

Possible reason:
- the extra notebook tokens cause more compaction,
- or the model starts trusting the notebook too much and writes bad notes,
- or external notes interfere with internal reasoning.

That would open a different research direction:
- naive memory aids may backfire in agent systems.

---

## FRUITFULNESS PRE-CHECK

### If this surprises you, then what?
Best-case interesting outcome:

> A tiny notebook strongly improves exact-memory tasks at long lengths, while doing little or nothing for aggregation tasks.

If that happens, it opens a real research question:

> What kind of memory representation helps long-horizon agents most: free summary, structured note, or default compaction?

That is a real question, not just "huh, neat."

It could lead to:
- a better benchmark story,
- a simple but strong agent-memory paper,
- and concrete design advice for real harnesses.

### Who would care?
Specific groups who would care:
- people building **coding agents**
- people building **research agents**
- people working on **long-context evaluation**
- people working on **agent memory / context compression**
- researchers around:
  - **MemGPT**
  - **MEMENTO**
  - **ACON**
  - long-context benchmark work like:
    - **BABILong**
    - **OOLONG**
    - **LongMemEval**

Also, if collaborators are serious about an **InfiniNews-style** benchmark, they should care, because a news system also needs:
- corrections,
- updates,
- entity tracking,
- temporal memory,
- multi-hop linking.

### Does this connect to our research directions?
Yes, strongly.

This fits under:
- agent memory
- context management
- long-horizon reasoning
- evaluation for reliable agents

This is not a random side idea. It sits in the middle of agent reliability.

---

## TIME BOX

### Sprint duration
**■ 1 week**

Short enough to stay honest, long enough to implement one new condition and run a small matrix.

### Check-in date
**26 / 04 / 2026**

### Hard stop date
**30 / 04 / 2026**

No extension unless the result is clearly surprising.

---

## What “done” looks like
This must stay small.

This is a **scout mission**, not a campaign.

Minimum done:

### Build
Implement **one new condition**:
- `auto` = current default compaction
- `auto+notebook` = same run, but every few chunks the agent writes a tiny note in a fixed format

### Keep the notebook simple
Something like:
- latest known facts
- corrections
- key entities
- dates/times
- unresolved conflicts

Not a giant summary.
Not chain-of-thought.
Just a tiny working note.

### Run a small matrix
Use a small, revealing task set.

#### BABILong
Pick one easy exact-memory task, one coreference/update task, and one time-style task.

For example:
- `qa1`
- `qa11`
- `qa14`

#### OOLONG
Pick one aggregation task and one temporal aggregation task.

For example:
- `counting`
- `timeline`

### Lengths
- `256k`
- `1M`

These are the important lengths because:
- `128k` is mostly pre-compaction
- `256k+` is where compaction becomes real

### Models
- `gpt-5.4`
- `gpt-5.4-mini`

### Minimum success condition for the sprint
At the end of the week I want to know:

> Does the notebook create a clear, repeatable difference on exact-memory tasks?

If yes, we sharpen.
If no, we shelve or pivot.

---

## AFTER THE SPRINT

### What did you actually observe?
_To fill at the end._

### Were your expectations violated?
_To fill at the end._

---

## THE DECISION

### GRADUATE / SHELVE / PIVOT

#### Graduate if:
- the notebook clearly helps exact-memory tasks at long lengths
- and the effect is stronger than on aggregation tasks

That would be enough to justify a sharper research question.

#### Shelve if:
- the notebook gives no real difference
- or results are just noise
- or it only helps trivially on one weird case

That is fine. Most good explorations die honestly.

#### Pivot if:
- the notebook does not help exact memory
- but something strange shows up instead

For example:
- notebook hurts
- notebook mainly helps temporal aggregation
- notebook changes compaction frequency in an unexpected way

Then the new sprint would be about that.

### The new what-if this could lead to
If this sprint surprises us, the next sharper question is something like:

> Which memory policy is best for long-horizon agents under compaction: free summary, structured notebook, or model-native compaction alone?

That is a real paper question.

---

## Why I like this sprint
Because it is:
- simple,
- cheap,
- honest,
- and directly tied to what we already observed.

It is also "crazy" in the right way:
- not complicated,
- not bloated,
- just one sharp intervention that could reveal a lot.

In plain words:

> We already know the system struggles. Now we ask whether a tiny notebook can save it.

That is worth a week.
