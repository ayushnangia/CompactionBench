## Link to channel and RQ/exploration doc

https://docs.google.com/document/d/1QZ9XwTSXI7V1IPJa5N0fzIWX3kJuqs0GarGc4pfwB7Q/edit

---

## What did you get done last week

- Finished the compression sprint. 648 runs across 5 conditions, 2 models, 3 benchmarks.
- Found that weak-hint compression (task-type label only) nearly matches full question awareness. Did not expect this.
- Built SWE-chat integration — real coding agent conversations as compaction tasks. Transcript pipeline works with HF auth.
- Cleaned and published the repo: github.com/ayushnangia/CompactionBench

---

## Summary of key experiments/results

- Sprint complete. Retention-accuracy gap (37pt BABILong vs 8pt OOLONG) is the strongest finding.
- Query-blind compression = 0/5. Query-aware = 3/5. Weak-hint = nearly matches query-aware.
- gpt-5.4 counts perfectly raw, fails after compression. Intelligence does not recover deleted info.
- 184 failures categorized into 5 mechanisms: fact dropped, wrong location, counting error, stale value, other.

---

## Decision

Graduated the gap metric. Shelved explicit compression as a method. Pivoting compression into mechanism probes.

Next direction: attention patterns in open models (Qwen 3.6 27B) to understand *why* the model drops certain facts during compaction.

---

## How fast are you going (1–5)

3. Sprint finished. Pivot decision made. Next week: decide between sharpening RQ or exploring attention.

---

## Specific areas where you want input from others

Thinking about attention pattern analysis during compaction. Does this direction make sense vs sharpening the gap metric into a paper?

---

## Status of pending preprints/papers/blog posts

Nothing yet. docs/after_the_sprint.md written with full sprint conclusion.
