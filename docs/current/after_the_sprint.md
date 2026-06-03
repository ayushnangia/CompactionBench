# AFTER THE SPRINT

## What we observed

- Compression helps exact updates (100%), destroys counting (5/5→0/5), neutral on binding (20%).
- Without the question, compression picks wrong facts every time (0/5). With it, matches raw (3/5).
- A weak hint ("find the current value") nearly matches knowing the full question.
- Smarter model does not recover deleted info. gpt-5.4 counts perfectly raw, fails compressed.
- BABILong has a 37pt gap between "answer is there" and "answer is correct." OOLONG: 8pt.

## Were expectations violated?

Yes. Weak-hint compression works nearly as well as knowing the full question. Did not expect that.

Also: task calibration was the real bottleneck. Original tasks were at 100%/0% ceiling/floor — hid all effects.

## Decision

**Graduate:** The retention-accuracy gap metric. Clean, replicated, useful.

**Shelve:** Explicit compression as a standalone method.

**Pivot:** Use compression to probe *why* the gap exists, not as a thing to publish.
