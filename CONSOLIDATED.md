# CompactionBench Consolidated Summary

This is the simple project readout. It is meant to replace the scattered sprint notes, HTML reports, and one-off experiment logs.

## One Sentence

Long AI agent conversations do not fail evenly when compressed: exact details break first, while broad summaries and simple aggregates survive better.

## The Main Result

| Evidence | What happened | What it means |
|---|---:|---|
| BABILong qa1-10 | answer visible 45.8%, correct 8.3% | exact facts are hard to recover |
| BABILong qa11-20 | answer visible 41.9%, correct 14.7% | same pattern, but this batch has usage-limit caveats |
| OOLONG-synth | answer visible 54.6%, correct 46.3% | aggregation survives better |

The useful metric is the gap between "the answer is still there" and "the model answered correctly."

## What We Can Say Confidently

1. Exact details are the weak point.
   Names, locations, values, object bindings, and scattered counts fail before general understanding does.

2. Blind compression keeps the wrong stuff.
   If the compressor has no clue what matters, it often saves filler instead of the answer.

3. A weak hint can be enough.
   The compressor does not always need the exact question. A simple hint like "find the current value" helped preserve the right fact.

4. Bigger models do not fix deleted information.
   In one counting task, `gpt-5.4` counted perfectly with raw context but failed after compression because most events were gone.

5. Task type matters.
   Stale updates, entity binding, and counting behave differently. Do not report one overall compression score as if it explains everything.

6. Search is useful but not universal.
   File search helps exact lookup. Full context can still be better for broad reading and aggregation. The honest claim is mixed, not "grep always wins."

7. Hierarchical memory is the cleanest newer win.
   For tasks where the answer is a maintained state across many events, a compact state packet beat raw flat packets.

## Current Experiment Families

| Group | Status | Keep using? | Plain readout |
|---|---|---|---|
| 648-run compression sprint | solid | yes | main result: exact memory breaks more than aggregation |
| Retention vs accuracy | solid | yes | best metric in the repo |
| Full context vs file search | useful but nuanced | yes, with caveats | exact scoring favors search; relaxed scoring weakens that claim |
| Search + notes / virtual context | promising | yes, with caveats | helps BABILong lookup; does not solve OOLONG counting |
| RLM depth-0 | useful | yes | best strict score on fixed 250-task panel, but slow |
| RLM depth-1 recursive | negative | yes, as a negative result | worked technically, but was slower and worse |
| PEEK context map | wired, not headline | yes, with caveats | useful related baseline; current panels are not a clean repeated-context test |
| Hierarchical memory | strong newer result | yes | best result for compact maintained state |
| BABILong state-table hierarchy | strong but narrow | yes | 48/48 on qa11-qa14, but task-specific |
| Generic bidirectional proof | negative | archive as lesson | did not beat grep; real OOLONG counting still failed |
| SWE-chat / LongMemEval | partial | not for headline | integration exists; scoring is not final |

## Do Not Claim

- Do not say search always beats full context.
- Do not say virtual context solves long memory.
- Do not say recursive RLM is better.
- Do not say our PEEK runs reproduce the PEEK paper.
- Do not cite BABILong qa11-20 as a clean full sweep without mentioning usage-limit failures.
- Do not mix strict exact scoring with relaxed scoring without labeling which one is used.
- Do not treat old sprint notes as the current project story.

## Best Headline

> Compaction does not just shorten memory. It changes what kind of memory survives. Exact details fail first; aggregate understanding survives better.

## Best Next Step

Turn the retention-vs-answer gap into the main paper/blog result. Use the other experiments as support:

- search as a baseline,
- virtual context as a retrieval probe,
- RLM depth-0 as an external-memory baseline,
- hierarchy as evidence that maintained state can beat raw recall,
- bidirectional proof as a negative result showing generic prompts are not enough.

## Current Supporting Files

- `RESULTS.md`
- `docs/current/after_the_sprint.md`
- `docs/current/hierarchical_memory_final_summary_2026-06-02.md`
- `docs/current/final_rlm_virtual_context_comparison.html`
- `docs/current/no_hardcoding_bidirectional_memory_final_2026-06-03.md`
- `docs/current/literature_alignment.md`

Everything else is either raw data, code, or archived context in `archive/`.
