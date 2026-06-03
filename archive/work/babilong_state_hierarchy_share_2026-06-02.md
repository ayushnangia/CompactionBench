# BABILong state-table hierarchy result

Short version: BABILong is a better real-benchmark check for the hierarchy idea than the synthetic lookup panel, because the task is mostly state tracking inside huge distractor text.

I added a deterministic `babilong_state_packet` arm:

- extracts BABI-style movement/object events from the raw context,
- drops isolated carrier-prose false matches,
- builds a compact current-state table,
- answers from a small state/evidence packet with no tools.

## Scaled qa11-qa14 result

48 tasks: qa11-qa14 × 3 samples × 4 lengths (`128k`, `256k`, `512k`, `1M`).

| Arm | Strict | Relaxed | Avg evidence | Avg duration |
|---|---:|---:|---:|---:|
| `babilong_state_packet` | 48/48 | 48/48 | ~208 tok | 6.2s |
| `grep_file` | 12/48 | 47/48 | tools | 11.8s |
| `virtual_context` | 7/48 | 18/48 | ~279 tok | 11.7s |

Interpretation:

- The hierarchy/state-table arm is strict-clean and tool-free on qa11-qa14.
- Grep is semantically strong under relaxed scoring, but strict answers often include article/preamble variants; it also uses tools and takes ~2× longer.
- Generic virtual context is not enough here: BABILong needs explicit state extraction, not just evidence windows.

Caveat: this only covers qa11-qa14 movement/coreference/time-reasoning tasks. It does not yet cover qa15-qa20, which need other operators.

Shareable one-liner:

> On BABILong qa11-qa14 across 128k–1M contexts, a deterministic state-table hierarchy got 48/48 strict with a ~208-token packet and no tools. Generic virtual context got 7/48 strict, while grep was mostly semantically right under relaxed scoring but only 12/48 strict and slower.
