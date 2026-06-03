# RQ3 Master Plan: Does position predict survival under compaction?

## The question

When Codex compacts conversation history, do facts at certain positions survive better than others? The "lost in the middle" paper showed models attend less to middle content. Does compaction amplify this — actively dropping middle content while preserving edges?

## The setup

Take LongMemEval-V2 sessions. Insert a controlled target fact at a known position. Compact. Test recall.

### Day 1: Build the position controller

**AM:** Write a fact injection tool that takes any context and inserts a synthetic fact at a specified position percentile (0%, 25%, 50%, 75%, 100%).

```python
def inject_fact(context, fact, position_pct):
    """Insert fact at position_pct (0.0 = start, 1.0 = end)"""
    words = context.split()
    idx = int(len(words) * position_pct)
    words.insert(idx, fact)
    return " ".join(words)
```

**PM:** Generate 50 tasks per position bucket. 5 positions × 50 tasks = 250 tasks. Use BABILong qa1 as base context with controlled facts.

### Day 2: Run the experiment

**AM:** Run all 250 tasks on gpt-5.4-mini with auto-compaction at 150k limit. Record accuracy per position.

**PM:** Replicate on gpt-5.4. Check if the position effect is consistent across models.

### Day 3: Analyze

**AM:** Plot survival rate vs position. Hypothesis: U-shaped curve, with middle positions showing lowest survival.

**PM:** Check if compaction events correlate with position. Do middle-position facts trigger more compactions? Are they dropped during compaction or never attended to?

### Day 4: LongMemEval-V2 variant

**AM:** Use LongMemEval-V2 sessions (real web agent trajectories) instead of BABILong. Insert controlled facts into real trajectories at different positions.

**PM:** Run 100 LME tasks with position-controlled facts. Compare against BABILong baseline.

### Day 5: Write-up

**AM:** "Position Matters: Where You Put Information Determines Whether Compaction Destroys It"

**PM:** Draft with figures: survival curve, compaction event correlation, model comparison.

## Combined Master Plan

### Phase 1: Tool-accessible compression (Week 1 — done)
- [x] Grep baseline on BABILong
- [x] Hint type experiments (39 hints tested)
- [x] LongMemEval-V2 integrated
- [ ] Finish 25-hint round 2 analysis
- [ ] Build compressed ledger format
- [ ] Ledger vs grep vs raw comparison

### Phase 2: Relevance signals (Week 2)
- [ ] Scale weak-hint to 50 tasks
- [ ] Task-type classifier
- [ ] Combined: hints + grep
- [ ] Hint placement study (beginning vs end)

### Phase 3: Position and mechanism (Week 3 — RQ3)
- [ ] Position controller tool
- [ ] 250-task position experiment
- [ ] LME position variant
- [ ] Survival curve analysis
- [ ] Attention comparison (Qwen open model)

### Phase 4: Polish and ship (Week 4)
- [ ] Consolidate all findings
- [ ] Write technical report
- [ ] Submit to ACL workshop
