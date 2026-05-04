# Weekly Update

## Link to channel and RQ/exploration doc (constant, no need to change)
Trying to understand and explore compaction for large context 128k to 1M+ and beyond. How it affects the ability of model to answer questions post-compaction, and metrics that can tell the quality of compaction (i.e. Shannon entropy).

https://github.com/microsoft/memento/blob/main/docs/memento.pdf
https://docs.google.com/document/d/1QZ9XwTSXI7V1IPJa5N0fzIWX3kJuqs0GarGc4pfwB7Q/edit?usp=sharing

---

## What did you get done last week

- Built a compression pipeline for the benchmark. Synthetic task generation covering entity binding, counting, and stale updates. Offline entropy and static compression that plugs into the existing Codex harness without changes.
- Ran comparisons: gpt-5.4-mini and gpt-5.4 across five conditions (auto_raw, entropy query-aware, entropy query-blind, static query-aware, static query-blind) on entity binding, counting, and stale-update tasks, plus BABILong and OOLONG transfer.
- Fixed the broken BABILong qa11-20 pipeline with Codex. Reran 256k and 512k. All 60 clean.

---

## Summary of key experiments/results

When AI context gets compressed, exact facts, names, numbers, places, disappear faster. There is a selective destruction of states while keeping vague information. This might explain why coding agents suddenly forget which file they were editing but still sound confident. (https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777033684252529)

When the compressor did not know the question, it kept the wrong facts every time (0 out of 5 correct). When it knew the explicit instruction of what we want, it kept the right facts and improved performance (3 out of 5 correct). (https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777455915871779)

GPT-5.4 recalls perfectly with full context. After compression, it fails. Similar with gpt-5.4 mini. (Maybe a good direction to study if more MMLU Pro score means more compression resilience.)

---

## How fast are you going (1–5, where 5 is your personal best in a long time)? What would accelerate your progress?

2–4. Experiments are quick. Reading papers and thinking about what matters takes time. Mostly 2 when reading and going through other work.

---

## Specific areas where you want input from others (optional)

None right now.

---

## Status of pending preprints/papers/blog posts

Nothing as of yet. Will make a .md for review before first check-in (30/04/26).
