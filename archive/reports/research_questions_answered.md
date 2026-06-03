# Research questions, current answers, and examples

This is the clean RQ map for the context-vs-search experiments. It separates three settings that are easy to confuse:

1. **Non-compacted full context**: the source is placed directly in one prompt.
2. **File search / grep**: the same source is saved as a file and the agent can search it.
3. **Long agent memory**: the source is injected over many chat turns and may be compacted.

## TL;DR

- **Do not say “grep always beats full context.”** The answer depends on scoring and task type.
- With strict exact scoring on the 500-run real-data control, file search looked better: **20% vs 16%**.
- But many “full context wrong” cases were harmless formatting differences like `the garden` vs `garden` or `No.` vs `No`.
- With a more forgiving normalization on BABILong/OOLONG, **full context is not worse and often looks better**.
- File search is most useful for **literal lookup** and **procedure retrieval**.
- Full context is often better for **aggregation, broad reading, and coding-style semantic replies**.
- The practical recommendation is not “replace context with grep”; it is **keep original sources searchable while also giving the model enough context to reason**.

---

## RQ1 — In a non-compacted setting, does file search beat direct full context?

**Question:** If the original source fits and no compaction happens, is searching a file better than putting the whole source in the prompt?

**Current answer:** **Mixed. Strict exact scoring says file search slightly wins, but normalized/semantic scoring weakens or reverses that claim.**

### Evidence: 500-run clean control

Run: `artifacts/batches/real_lossless_vs_grep_500/20260515-173440`

- 250 real tasks × 2 arms = **500 runs**
- Datasets: **BABILong 128k + OOLONG-real**
- Compaction events: **0**
- Run failures: **0**

Strict deterministic scoring:

| Arm | Correct | Accuracy |
|---|---:|---:|
| Full context | 40 / 250 | 16% |
| File search | 50 / 250 | 20% |

But after simple answer normalization for articles/punctuation/boxing:

| Dataset | Full context | File search | Read |
|---|---:|---:|---|
| BABILong | ~53 / 100 | ~45 / 100 | Full context better after removing formatting artifacts |
| OOLONG-real | ~35 / 150 | ~33 / 150 | Roughly tied |
| Overall relaxed short-answer score | ~97 / 250 | ~83 / 250 | Full context no longer loses |

**Interpretation:** the strict 20% vs 16% number is real under the current scorer, but it overstates grep because strict exact scoring punishes answers like `the garden` when the gold is `garden`.

### Interesting example: strict scorer makes grep look better, but both are semantically right

| Field | Value |
|---|---|
| Dataset | BABILong qa4 |
| Question | `What is the bedroom north of?` |
| Gold | `garden` |
| Full context | `the garden` |
| File search | `garden` |
| Strict score | full context wrong, grep right |
| Human read | both are right |

**Why this matters:** some apparent grep wins are formatting wins, not real reasoning wins.

---

## RQ2 — Does file search beat compacted long-agent memory?

**Question:** In a realistic long-running agent chat, where old messages can get compacted, does source search help?

**Current answer:** **Yes, this is the strongest qualitative claim, but we still need a fully paired compacted-vs-grep run at the same scale.**

### Evidence: 100-run agent-memory baseline

Run: `artifacts/batches/balanced_context_100/20260514-184008`

- 100 mixed tasks
- 68 / 100 runs had compaction
- 240 total compaction events
- Accuracy: 21%

This shows that long agent memory degrades under compaction. It does **not** by itself prove grep beats the same exact tasks in a paired setup, but earlier BABILong grep tests and the current clean controls support the mechanism: file search preserves exact source text while compacted chat memory may not.

### Interesting example: what compaction can do

In agent-memory mode, the source is fed as many chat messages:

```text
User: Context chunk 1/18: ...
Assistant: OK
User: Context chunk 2/18: ...
Assistant: OK
...
User: Now answer: Where is Mary?
```

If early chunks are compacted, the exact sentence may no longer be available. A file search can still run:

```bash
grep -n -i 'Mary' full_context.txt
```

and recover the exact line.

**Answer status:** partially answered; needs a paired compacted-agent-memory vs file-search run for final numbers.

---

## RQ3 — In what cases does file search help most?

**Question:** What task types are actually helped by file search?

**Current answer:** **Literal lookup and procedural retrieval.**

### Evidence: BABILong exact retrieval

Strict scoring showed file search ahead on BABILong:

| Dataset | Full context | File search |
|---|---:|---:|
| BABILong 128k strict | 7 / 100 | 17 / 100 |

But normalized scoring reduces this advantage:

| Dataset | Full context | File search |
|---|---:|---:|
| BABILong 128k normalized | ~53 / 100 | ~45 / 100 |

So file search helps, but many strict wins are formatting artifacts.

### Evidence: LongMemEval procedure questions

Run: `artifacts/batches/swe_lme_real_vs_grep_250/20260518-173038`

LME rendered context, corrected rough scoring:

| LME type | Full context | File search | Read |
|---|---:|---:|---|
| procedure | 4 / 11 | 6 / 11 | Search helped |
| dynamic-environment | 1 / 11 | 2 / 11 | Search helped slightly |
| static-environment | 2 / 11 | 3 / 11 | Search helped slightly |

### Interesting example: real grep-only win

| Field | Value |
|---|---|
| Dataset | LongMemEval procedure |
| Question | Which option contains only fields present on the Problem table for creating problem requests from incident-report results? |
| Gold | `G` |
| Full context | `C` |
| File search | `G` |
| Read | file search found the relevant procedure/table evidence |

**Answer:** file search is most useful when the answer is tied to an exact phrase, label, option, module name, field name, or procedure that can be searched.

---

## RQ4 — In what cases does full context help more?

**Question:** When is direct full-context reading better than file search?

**Current answer:** **Aggregation and broad reading.** Search can find local matches but still count or combine them incorrectly.

### Evidence: OOLONG-real exact accuracy tied

| Dataset | Full context | File search |
|---|---:|---:|
| OOLONG-real strict | 33 / 150 | 33 / 150 |
| OOLONG-real rough normalized | ~35 / 150 | ~33 / 150 |

Paired OOLONG outcomes:

| Outcome | Count |
|---|---:|
| Full-only correct | 13 |
| Search-only correct | 13 |
| Both correct | 20 |
| Both wrong | 104 |

### Interesting example: full-context win on counting

| Field | Value |
|---|---|
| Dataset | OOLONG-real multidoc_rolls |
| Question | `What is the total count of Nat20s across all episodes?` |
| Gold | `7` |
| Full context | `7` |
| File search | `6` |
| Read | search found many local clues but undercounted |

**Answer:** full context is better when the model must integrate many events, count, compare, or understand a broad transcript rather than retrieve one exact string.

---

## RQ5 — Does this hold for real coding-agent conversations?

**Question:** In SWE-chat real Codex sessions, does file search beat full context?

**Current answer:** **Not answered by deterministic exact scoring. Rough semantic scoring currently favors full context, but we need judge scoring.**

### Evidence: SWE-chat 50-task paired run

Run: `artifacts/batches/swe_lme_real_vs_grep_250/20260518-173038`

Strict substring scoring:

| Arm | Correct |
|---|---:|
| Full context | 0 / 50 |
| File search | 0 / 50 |

This is expected because SWE-chat gold answers are long assistant replies, not short factual answers.

Rough semantic overlap on parsed answers:

| Arm | Average semantic score | Median | Count ≥ 0.2 |
|---|---:|---:|---:|
| Full context | ~0.196 | ~0.200 | 19 |
| File search | ~0.139 | ~0.129 | 12 |

**Interpretation:** for coding conversations, file search does not obviously help under rough semantic scoring. Full context may be better because the answer often depends on conversational intent, not just finding a line.

**Answer status:** needs LLM judge/semantic scoring before making a strong claim.

---

## RQ6 — What happens on LongMemEval real web-agent memory?

**Question:** Does source search help on real web/enterprise agent memory tasks?

**Current answer:** **Yes, on rendered LongMemEval context, file search is modestly better.**

Run: `artifacts/batches/swe_lme_real_vs_grep_250/20260518-173038`

Important caveat: LME is **rendered/clipped browser trajectories**, not raw lossless trajectory JSON. Do not mix it with the clean lossless control without labeling it.

Rough corrected scoring:

| Arm | Correct |
|---|---:|
| Full context | ~7 / 75 |
| File search | ~12 / 75 |

Strict current scorer showed:

| Arm | Correct |
|---|---:|
| Full context | 8 / 75 |
| File search | 12 / 75 |

### Interesting example: both methods found the same dynamic fact

| Field | Value |
|---|---|
| Dataset | LongMemEval dynamic-environment |
| Question | If Impact is Low and Urgency is Low, what Priority appears? |
| Gold | `5 - Planning` |
| Full context | `5 - Planning` |
| File search | `5 - Planning` |

### Interesting example: full-context only win

| Field | Value |
|---|---|
| Dataset | LongMemEval static-environment |
| Question | What extra button appears on the incident page but not the change-request form? |
| Gold | `Resolve` |
| Full context | `Resolve` |
| File search | `Create Change Request` |

**Answer:** file search helps on some procedural LME questions, but it can still pick the wrong local match.

---

## RQ7 — What should agent systems do with long sources?

**Question:** What is the product/design takeaway?

**Current answer:** **Do both: keep original sources searchable and provide enough context for reasoning.**

Do not rely only on:

- giant prompts,
- compressed chat memory,
- or blind grep.

Best design pattern:

1. Keep source files/transcripts/logs accessible in a stable location.
2. Let the agent search them with tools.
3. Also provide a concise summary or relevant context for reasoning.
4. Use task-aware scoring/evaluation: exact scoring for short facts, semantic/judge scoring for coding conversations.

---

## Current answer matrix

| RQ | Status | Short answer |
|---|---|---|
| RQ1: non-compacted full context vs file search | Answered with caveat | Strict score favors search; normalized score does not. |
| RQ2: compacted agent memory vs search | Partially answered | Compaction hurts; need paired run for final numbers. |
| RQ3: where search helps | Answered | Literal lookup and procedures. |
| RQ4: where full context helps | Answered | Aggregation, broad reading, semantic coding replies. |
| RQ5: SWE-chat coding sessions | Needs judge | Exact scoring unusable; rough semantic favors full context. |
| RQ6: LongMemEval web-agent memory | Tentatively answered | Search modestly helps on rendered LME, especially procedures. |
| RQ7: system recommendation | Answered | Preserve searchable source + context, not one or the other. |

---

## Artifact map

| Artifact | Path |
|---|---|
| Clean 500-run full-context vs grep report | `artifacts/batches/real_lossless_vs_grep_500/20260515-173440/analysis/report.md` |
| Clean 500-run rows | `artifacts/batches/real_lossless_vs_grep_500/20260515-173440/analysis/rows.csv` |
| SWE-chat + LME 250-run report | `artifacts/batches/swe_lme_real_vs_grep_250/20260518-173038/analysis/report.md` |
| SWE-chat + LME rows | `artifacts/batches/swe_lme_real_vs_grep_250/20260518-173038/analysis/rows.csv` |
| Agent-memory 100-run report | `artifacts/batches/balanced_context_100/20260514-184008/analysis/report.md` |
| Plain-English HTML | `docs/real_full_context_vs_grep_500.html` |
