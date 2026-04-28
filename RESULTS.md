# CompactionBench — Results

## One finding

> **The gap between what the model has in context and what it can answer correctly is much larger for exact-memory tasks than for aggregation tasks.**

This gap is a metric researchers can use to diagnose whether their system loses information during compaction.

---

## The numbers

| Benchmark | Gold in context | Correct answer | Gap |
|---|---:|---:|---:|
| BABILong qa1-10 | 45.8% | 8.3% | **+37.5 points** |
| BABILong qa11-20 | 41.9% | 14.7% | **+27.2 points** |
| OOLONG-synth | 54.6% | 46.3% | **+8.3 points** |

For BABILong, the gold answer is present in the context nearly half the time. But the model only answers correctly 8% of the time. This means the model has the information but cannot extract it.

For OOLONG, the gap is small. When the information survives, the model uses it.

---

## What this means

Compaction does not affect all tasks equally.

For **exact-memory tasks** like BABILong, compaction may preserve the prose but degrade the exact word, number, or binding needed to answer.

For **aggregation tasks** like OOLONG, compaction seems to preserve enough local facts for the model to compute a correct global answer.

This is the **core finding**: exact symbolic memory degrades under compaction while broad aggregation survives.

---

## By context length

### BABILong qa1-10

| Length | Gold in context | Correct answer | Gap |
|---|---:|---:|---:|
| 128k | 53.3% | 10.0% | +43.3pp |
| 256k | 60.0% | 13.3% | +46.7pp |
| 512k | 46.7% | 10.0% | +36.7pp |
| 1M | 23.3% | 0.0% | +23.3pp |

The retention drop at 1M is steep: from 47-60% down to 23%.

### OOLONG-synth

| Length | Gold in context | Correct answer | Gap |
|---|---:|---:|---:|
| 128k | 48.1% | 37.0% | +11.1pp |
| 256k | 66.7% | 55.6% | +11.1pp |
| 512k | 44.4% | 37.0% | +7.4pp |
| 1M | 59.3% | 55.6% | +3.7pp |

OOLONG is stable. The gap stays small, even at 1M.

---

## Compaction events

Compaction becomes load-bearing around 256k tokens.

| Length | Runs with compaction | Avg compactions per run |
|---|---:|---:|
| 128k | 0/57 | 0.0 |
| 256k | 57/57 | 1.6 |
| 512k | 57/57 | 3.4 |
| 1M | 57/57 | 7.4 |

At 1M, the system compacts roughly seven times per run.

---

## Caveats

1. **BABILong qa11-20 is confounded.** 66% of those runs had usage-limit errors. The resolved subset is informative but the full batch cannot be cited as clean.

2. **OOLONG-real has no clean batch yet.** All results are from OOLONG-synth.

3. **All runs use Codex auto-compaction only.** No comparison with other compaction policies has been run yet.

4. **The retention metric uses a simple check:** does the gold answer string appear in any turn preview? This is a lower bound on actual information survival. The model may have access to the information in ways not captured by simple substring match.

---

## What was run

| Batch | Runs | Models | Clean? |
|---|---:|---|---|
| BABILong qa1-10 | 120 | gpt-5.4, gpt-5.4-mini, gpt-5.3-codex | Yes (98% resolved) |
| BABILong qa11-20 | 360 | gpt-5.4, gpt-5.4-mini, gpt-5.3-codex | No (34% resolved) |
| OOLONG-synth | 108 | gpt-5.4, gpt-5.4-mini, gpt-5.3-codex | Yes (99% resolved) |

All runs used:
- Codex auto-compaction with `model_auto_compact_limit=150000`
- reasoning effort: high
- verbosity: low
- web search: disabled

---

## What is next

1. Run the synthetic compression comparison to test whether explicit compression policies reduce the retention-accuracy gap.

2. Rerun the failed BABILong qa11-20 cells to get clean data.

3. Run a full OOLONG-real batch.

4. Test GEPA/DSPy-optimized compression after simple baselines show signal.

---

## Chart

![Retention vs Accuracy](artifacts/analysis/retention_metrics/retention_vs_accuracy.png)

Light bars: how often the gold answer appears in the context.  
Dark bars: how often the model answers correctly.

The gap is the difference. BABILong has a large gap. OOLONG does not.
