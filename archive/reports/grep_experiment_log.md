# Grep Experiment Log

## Design

9 conditions on BABILong qa1 256k. Tests whether compression hints and grep strategies affect accuracy.

| # | Condition | Hint during compression? | Use grep to answer? | Result |
|---|---:|---:|---:|---|
| 1 | no_hint_memory | No | No | Running |
| 2 | hint_memory | Yes — "keep grep-friendly terms" | No | Running |
| 3 | no_hint_grep | No | Yes | Running |
| 4 | hint_grep | Yes | Yes | Running |
| 5 | strategy_context | No | Yes — grep -C 5 | Running |
| 6 | strategy_count | No | Yes — count first | Running |
| 7 | strategy_exact | No | Yes — exact phrase | Running |
| 8 | strategy_recursive | No | Yes — recursive search | Running |
| 9 | strategy_invert | No | Yes — grep -v | Running |

## Results so far (from earlier experiments)

### Grep vs raw context on qa1
| Length | Raw context | Grep original file |
|---|---:|---:|
| 256k | ✗ "not mentioned in context" | ✓ "bathroom" |
| 512k | ✗ "not stated" | ✓ "bathroom" |

### Grep hint backfires (first attempt)
| Condition | Answer | Correct? |
|---|---|---|
| No hint + cbench | "the bathroom" | ✓ |
| Grep hint + cbench | "Not found in the provided chunks" | ✗ |

The hint added text that the compressor kept instead of the answer. Hint backfired.

### Grep on all BABILong qa1-10
| Task set | Raw context | Grep |
|---|---:|---:|
| qa1-10 128k | 43% | 60% |
| qa11-20 128k | 83% | 90% |

### Grep strategy variants (qa1 256k, 512k)
All five strategies worked (basic, -C 3, -i, -w, count first). 100% correct. Strategy doesn't matter for easy tasks.

### Claude vs Codex grep
Claude + grep: ✓ "Bathroom"
Codex + grep: ✗ "house" (picked wrong Mary mention)

## Key findings

1. **Grep beats context injection.** 60% vs 43% on qa1-10.
2. **Grep hint during compression backfires.** Model keeps the hint, drops the answer.
3. **Strategy doesn't matter for easy tasks.** Any grep variant works.
4. **Claude greps better than Codex.** Claude finds the right mention, Codex picks wrong one.
5. **Timeout at extreme lengths.** 128k and 1M files cause timeouts.
