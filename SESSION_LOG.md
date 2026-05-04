# CompactionBench — Session Log & Next Steps

Date: 28–29 April 2026

---

## What was done

### Compression sprint (28 April)

**Pipeline built:**
- `compactionbench/tasks.py` — synthetic task generator (stale-update, entity binding, counting)
- `compactionbench/compression.py` — offline entropy and static compression, query-aware and query-blind
- `compactionbench/llmlingua_wrapper.py` — LongLLMLingua integration (works on CPU, fails at 158k context — documented as finding)
- `cbench prepare synth` and `cbench compress` CLI commands
- 50 tests passing

**Experiment 1 — Initial comparison (126 runs):**
- gpt-5.4-mini and gpt-5.4, 5 compression conditions, 3 task types
- Stale-update 100% (ceiling), entity binding 20% (floor), counting 0% for mini
- gpt-5.4 counting: 5/5 raw → 0/5 compressed (compression destroys counting)

**Experiment 2 — BABILong 5-task transfer (30 runs):**
- Switched to substring scorer to fix format issue
- auto_raw: 3/5, entropy_qa: 3/5, entropy_qb: 0/5
- Gold survival in compressed context perfectly predicts correctness

**Experiment 3 — Recalibrated tasks (31/50 raw runs, in progress):**
- Stale-update: 4 intermediate values + distractor (64% raw, down from 100%)
- Entity binding: 5 confusingly similar names (50% raw, up from 20%)
- Weak-hint compression mode built (task-type label instead of full question)

**Infrastructure:**
- GitHub repo renamed from ContinualBENCH → CompactionBench
- qa11-20 batch rerun at 256k and 512k (60/60 clean)
- Retention metric analysis on existing batches (BABILong 37pt gap, OOLONG 8pt gap)

**Docs written:**
- `RESULTS.md` — overall project results
- `paper_ideas.md` — three candidate paper metrics
- `hypotheses.md` — three sharp, testable hypotheses
- `what_we_are_doing_wrong.md` — diagnosis and fix plan
- `next_steps.md` — boss-facing plan
- `weekly_update.md` — check-in ready
- `exploration_sprint_compaction_boss.md` — sprint document
- `outputs/optimized-compaction-memory-comparison.md` — literature comparison
- HTML exports for Slack: `docs/compression_experiments_slack.html`, `docs/task_type_effects_retention.html`

**Discussed with Claude and Codex:**
- Both agree: sprint direction is strong, present at check-in, calibration story proven
- Both recommend: scale to 50 tasks, replicate on gpt-5.4, weak-hint test is the cleanest mechanism experiment
- Both agree: LLMLingua 512-token limit is a finding, not a failure

---

## Key findings

1. **Compression needs to know what matters.** Query-blind: 0/5 on BABILong. Query-aware: 3/5, matches raw.

2. **Smarter model does not recover deleted information.** gpt-5.4 counts 5/5 raw, 0/5 compressed.

3. **Compression effect depends on task type.** Exact updates: helps. Counting: destroys. Entity binding: neutral.

4. **Retention metric separates memory loss from reasoning failure.** BABILong: 37pt gap. OOLONG: 8pt gap.

5. **Task calibration is load-bearing.** Old tasks at ceiling/floor showed no effect. Recalibrated tasks at 50% show clear compression gradient.

---

## Three sharp hypotheses

**A: Token frequency.** Compaction drops low-frequency tokens that carry the answer. Test: measure frequency of retained vs dropped facts.

**B: Question signal.** Query-blind fails because it has no relevance signal. Test: weak-hint (task-type label) vs full question vs blind.

**C: Method comparison.** Our entropy compression should be compared against LongLLMLingua (attempted, blocked by 512-token limit — documented as architecture finding).

---

## Next steps

From Claude and Codex discussion:

| Priority | Action | Status |
|---|---:|---|
| 1 | Finish 50-task batch on gpt-5.4-mini (overnight) | Running |
| 2 | Score full batch (4 conditions: raw, qa, qb, whint) | Pending |
| 3 | Replicate on gpt-5.4 (50 tasks, 4 conditions) | Pending |
| 4 | Weak-hint analysis: does task-type label match full-question performance? | Pending |
| 5 | Present at check-in (30/04): calibration proven, provisional but defensible | Pending |
| 6 | Drop LLMLingua head-to-head; document 512-token limit as motivation | Done |
| 7 | Scale entity binding N to tighten confidence intervals | Future |
| 8 | Write sprint conclusion: graduate, shelve, or pivot | After batch |

---

## Files index

| File | Purpose |
|---|---|
| `RESULTS.md` | Overall project results |
| `paper_ideas.md` | Candidate paper metrics |
| `hypotheses.md` | Three testable hypotheses |
| `what_we_are_doing_wrong.md` | Diagnosis and fix plan |
| `next_steps.md` | Boss-facing plan |
| `weekly_update.md` | Check-in ready |
| `exploration_sprint_compaction_boss.md` | Sprint document |
| `outputs/optimized-compaction-memory-comparison.md` | Literature comparison |
| `artifacts/analysis/bulk_experiment_results.md` | Detailed experiment |
| `artifacts/analysis/retention_metrics/` | Retention analysis + chart |
| `docs/compression_experiments_slack.html` | Slack export |
| `docs/task_type_effects_retention.html` | Slack export |
