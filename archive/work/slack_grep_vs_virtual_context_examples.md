Quick clarification on grep vs “grep + notes”

I agree the important distinction is **not** whether grep output stays in the model context vs gets written into `notes.md`. A notes file by itself is not magic.

The cleaner distinction is:

> **agent-controlled grep** vs **system-built**

On the 250-task real BABILong + OOLONG panel, grep is strong, but the system-built evidence arms are better:

- `grep_file`: **52/250** strict
- `structured_notes_prompt`: **54/250** strict
- `virtual_context_8k/24k/48k`: **59–62/250** strict
- `RLM depth-0`: **74/250** strict

So I don’t think the takeaway is “grep is enough.” I think the takeaway is: grep is a strong baseline, but the agent often fails at evidence selection, state tracking, ordering, or counting.

Some qualitative examples where grep-only failed but virtual/system evidence fixed it:

### 1. Grep follows the wrong Mary

**Question:** Where is Mary?
**Gold:** `bathroom`

- grep-only: `on the bed in her room`
- virtual context: `bathroom`

Grep found carrier-prose text about a different Mary. Virtual context extracted only the inserted BABI-style state-change fact like `Mary journeyed to the bathroom`.

### 2. Grep finds object mentions but not the state chain

**Question:** Where is the milk?
**Gold:** `garden`

- grep-only: `At Bellevue, across the river.`
- structured notes / virtual context: `garden`

Grep saw raw `milk` lines but did not resolve `there` through the movement chain. The system evidence gave a chronological trace of movement + object events.

### 3. Grep confuses holder with location

**Question:** Where was the football before the hallway?
**Gold:** `office`

- grep-only: `with Daniel`
- virtual context: `office`

The question asks for the football’s previous location, not who had it. Virtual context had the event chain needed to infer location.

### 4. Grep uses stale object state

**Question:** What is Daniel carrying?
**Gold:** `nothing`

- grep-only: `milk`
- virtual context: `nothing`

Grep found the earlier `Daniel grabbed the milk` line but missed/failed to apply the later `Daniel dropped the milk` update.

### 5. OOLONG: grep counts surface words, not roll events

**Question:** What is the most common roll type across all episodes?
**Gold:** `Attack`

- grep-only: `check`
- virtual context: `attack`

Grep counted literal transcript terms like “check,” but “check” appears conversationally. The task needs classification of actual roll events.

### 6. OOLONG: grep gets episode ordering wrong

**Question:** Last spell cast by Keyleth in each episode?
**Gold:** `Cure Wounds, Transport Via Plants`

- grep-only: `Cure Wounds, Plant Growth`
- structured notes / virtual context: `Cure Wounds, Transport Via Plants`

This needs episode boundaries + last relevant spell cast per episode. Raw grep found spell mentions but picked the wrong late event.

So I’d reframe the method as **system-side evidence construction**, not “notes.”

If the agent searches perfectly, grep and notes should collapse. But when grep-only fails because of distractors, stale state, ordering, or counting, a virtual-context/evidence packet can recover some of those failures.
