# No-hardcoding bidirectional memory final conclusion

Date: 2026-06-03

## What was built

I added a generic `bidirectional_proof` arm and a `bidirectional_proof_repair` arm.

The rule was strict: no benchmark-specific semantic categories in the prompt or code path. No BABILong locations, no OOLONG roll/spell categories, no dinner/project/preference schemas.

Allowed hardcoding was only protocol/infrastructure:

- save raw context to `context.txt`,
- ask the model to induce a task-local query contract,
- search the source,
- write `proof_packet.json`,
- optionally write `proof_audit.json`,
- validate whether quoted spans appear in the raw context,
- return the final JSON answer.

## What was tested

### OOLONG canary

Panel:

- `data/benchmarks/generic_bidirectional_oolong_canary_6.jsonl`
- 6 tasks: OOLONG synthetic counting/timeline/user and OOLONG-real roll/spell cumulative counts.

First generic proof result:

| Arm | Strict |
|---|---:|
| `bidirectional_proof` | 3/6 |
| `grep_file` | 2/6 |
| `virtual_context` | 1/6 |

The generic proof arm solved the synthetic aggregate tasks but failed real cumulative roll/spell counts.

### Cross-benchmark canary

Panel:

- `data/benchmarks/generic_bidirectional_cross_benchmark_canary_9.jsonl`
- 9 tasks across OOLONG, BABILong, synthetic hierarchy, LME, and SWE-chat.

Result:

| Arm | Strict | Relaxed |
|---|---:|---:|
| `bidirectional_proof` | 2/9 | 4/9 |
| `grep_file` | 3/9 | 5/9 |

The generic proof arm was not stronger than grep on this mixed canary.

### Stricter proof/audit protocol

I then tightened the protocol without adding semantic categories:

- require exhaustive source-derived scripts for totals/frequencies/order/extrema,
- require `proof_audit.json`,
- record quote/provenance checks,
- require explicit unresolved-risk reporting.

V2 OOLONG result stayed the same:

| Arm | Strict | Avg tools | Avg duration |
|---|---:|---:|---:|
| `bidirectional_proof` v2 | 3/6 | 9.83 | 109s |

Accuracy did not improve; cost increased.

### Independent proof-repair pass

I added `bidirectional_proof_repair`, a second independent model call that reads the first proof/audit and tries to repair it.

Repair canary on the three real OOLONG cumulative roll/spell tasks:

| Arm | Strict | Avg tools | Avg duration |
|---|---:|---:|---:|
| `bidirectional_proof_repair` | 0/3 | 19.67 | 133s |

The repair pass still failed all real OOLONG cumulative count tasks and became much more expensive.

## Conclusion

No-hardcoding is the right scientific constraint, but the current generic model-driven proof-search protocol is not sufficient.

The honest finding is:

> Removing benchmark-specific categories makes the method cleaner, but a single generic proof prompt — even with an audit and repair pass — does not reliably solve real long-context aggregate/counting tasks like OOLONG-real.

The method can induce useful structure for simpler synthetic aggregate tasks. It does not yet replace task-specific state/counter operators for hard real benchmarks.

## What not to claim

Do not claim:

- generic bidirectional memory beats grep,
- generic bidirectional memory solves OOLONG,
- hierarchy is generic without operators,
- the repair pass fixed the no-hardcoding problem.

## What to claim

The defensible claim is narrower:

> The no-hardcoding prototype is a diagnostic negative result. Generic schema/proof induction is possible on simple tasks, but real OOLONG-style counting still needs better generic scaffolding/checking. The next step is not semantic hardcoding; it is stronger generic computation/provenance infrastructure.

## Next direction without semantic hardcoding

If continuing, do not add OOLONG/BABILong categories. Instead add generic infrastructure:

1. source segmentation primitives that expose line ranges/chunks without semantic labels,
2. generic table/record induction from repeated text patterns,
3. generic count reconciliation across independent scripts,
4. proof invariants like coverage, disjointness, duplicate handling, and boundary checks,
5. verifier-driven repair based on failed invariants, not benchmark labels,
6. multiple independent proof attempts with consensus.

This keeps the protocol generic while making it less dependent on one model prompt doing all reasoning correctly.

## Pushed commits

- `6505f5d` — add generic bidirectional proof canary
- `d45d6f7` — tighten generic proof protocol
- `619d3d4` — add generic proof-repair canary

Related summary:

- `archive/work/generic_bidirectional_memory_canary_2026-06-03.md`
