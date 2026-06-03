# Hierarchical memory budget-pressure result

Short version: hierarchy only starts to matter once the task needs compact derived state, not just finding one matching line.

On the earlier stale/update panel, flat retrieval and grep were strong. The useful separation came from aggregate memory questions where the answer is a small fact derived from many events.

## Budget-pressure aggregate subset

20 tasks: dinner-count + least-common-dinner across 10 synthetic memory streams, each with 180 days of events.

| Arm | Strict | Avg evidence | Notes |
|---|---:|---:|---|
| flat raw packet | 3/20 at 900-token budget | ~506 tok | raw top-k events do not contain enough global evidence |
| virtual context | 14/20 | ~9.1k tok | better, but still misses aggregate cases |
| hierarchy packet | 20/20 | ~142 tok | answers from consolidated L2 counts |

Budget sweep: hierarchy stayed 20/20 at 300, 600, 900, and 1800 token budgets. Flat raw retrieval stayed at 3/20 until 1800, where it reached 5/20.

## Mixed 5-stream panel

55 tasks across all query types: exact recall, stale/current state, aggregate counts, least-common aggregate, and abstention.

| Arm | Strict | Relaxed | Avg evidence | Avg duration |
|---|---:|---:|---:|---:|
| grep_file | 50/55 | 55/55 | tools | 12.6s |
| flat raw packet | 47/55 | 47/55 | ~602 tok | 6.8s |
| virtual context | 44/55 | 44/55 | ~8.4k tok | 10.9s |
| hierarchy packet | 55/55 | 55/55 | ~232 tok | 6.2s |

Main caveat: this is synthetic. The point is not “hierarchy beats grep everywhere.” Grep is still excellent when the answer can be found or computed from the file. The result supports a narrower claim: when the needed answer is consolidated state over many raw memories, a hierarchy/state table can be both smaller and more accurate than flat top-k evidence.

Shareable one-liner:

> On single-fact lookup, grep/flat retrieval is very hard to beat. But on aggregate memory under an equal packet budget, hierarchy separated cleanly: flat raw retrieval got 3–5/20, virtual context got 14/20 with ~9k evidence tokens, and the hierarchy packet got 20/20 with ~142 tokens by carrying consolidated L2 state.
