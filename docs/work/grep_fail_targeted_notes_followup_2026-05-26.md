# Grep-fail targeted notes follow-up

## Why this exists

The 5-task canary was too small and made it sound like we were dropping `grep + notes`. We should not. The right question is conditional:

> When grep-only fails, can a notes/evidence pipeline recover the answer, and is that because of the note file or because of better evidence selection?

## Existing 250-task evidence

From `artifacts/batches/notes_ablation_1000/20260525-223108/analysis/report.md` on the fixed real BABILong + OOLONG 250 panel:

| Arm | Strict correct | Relaxed correct |
|---|---:|---:|
| `grep_file` | 52/250 | 93/250 |
| `structured_notes_prompt` | 54/250 | 97/250 |
| `virtual_context_8k` | 59/250 | 99/250 |
| `virtual_context_24k` | 62/250 | 98/250 |
| `virtual_context_48k` | 60/250 | 97/250 |

Pairwise vs grep:

| Compare arm | Compare-only correct when grep fails | Grep-only correct |
|---|---:|---:|
| `structured_notes_prompt` | 26 | 24 |
| `virtual_context_24k` | 28 | 18 |
| `virtual_context_48k` | 26 | 18 |
| `virtual_context_8k` | 25 | 18 |

So yes: there is real signal specifically on grep failures. System-side evidence packets recover ~25-28 grep-failed tasks on this panel.

## Targeted CLI-made-notes follow-up

I created a targeted subset of tasks where `grep_file` was wrong but at least one system evidence/notes arm was right:

- subset: `data/benchmarks/confirmation/grep_fail_notes_win_26.jsonl`
- candidates: 54 tasks
- metadata: `artifacts/analysis/paras_grep_fail_notes_win_candidates.json`

Then I ran CLI-made notes arms:

```bash
uv run python scripts/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/grep_fail_notes_win_26.jsonl \
  --root-dir artifacts/batches/grep_fail_notes_win_cli_notes_54 \
  --arm cli_notes_same_session \
  --arm cli_notes_two_stage \
  --model gpt-5.4-mini \
  --reasoning-effort low \
  --verbosity low \
  --timeout-s 300 \
  --max-workers 6
```

The full 108-job run timed out on slow OOLONG jobs, but 36 candidate tasks completed and are enough for a partial read:

- completed targeted candidates with usable pairs: 36
- `cli_notes_same_session`: 6/35 strict
- `cli_notes_two_stage`: 5/36 strict

Breakdown on completed candidate tasks:

| Candidate type | Completed | CLI same-session solved | CLI two-stage solved |
|---|---:|---:|---:|
| `structured_notes_prompt` was a winner | 18 | 2/17 | 2/18 |
| `virtual_context_24k` was a winner | 22 | 4/21 | 4/22 |
| `virtual_context_8k` was a winner | 17 | 3/16 | 4/17 |
| `virtual_context_48k` was a winner | 21 | 3/21 | 2/21 |

## Interpretation

This is the clean version of the story:

1. Paras is right that a note file alone is not magic. On the 5-task canary, CLI-made notes and grep-only tied.
2. But we also have real 250-task evidence that system-side evidence packets recover a meaningful number of grep-only failures.
3. On the targeted grep-fail/system-notes-win subset, asking Codex to make its own notes only recovers a small slice. This suggests the useful thing is not “notes in a file”; it is the evidence-selection/extraction policy that builds the notes.

So the project should not abandon grep+notes. It should rename and sharpen it:

> not “grep + notes” as a storage trick, but **system-side evidence construction** vs **agent-controlled grep**.

## Suggested reply to Paras

You’re right that “grep output in context vs notes in a file” is not the clean distinction. I ran that ablation and CLI-made notes basically tied grep-only on the small canary.

But I don’t think that means the notes/evidence idea is dead. On the full 250 real BABILong + OOLONG panel, the system-built evidence arms do recover grep failures:

- grep-only: 52/250 strict
- structured notes prompt: 54/250
- virtual-context/evidence packet: 59-62/250
- structured notes fixes 26 cases where grep was wrong
- virtual-context fixes 25-28 cases where grep was wrong

I also made a targeted subset of grep-fail / notes-win tasks and tried “CLI makes its own notes.” On the completed part, CLI-made notes recovered only ~5-6 of 36. So the file itself is not the mechanism; the mechanism is better evidence selection / extraction before answering.

So I’d reframe it as:

> agent-controlled grep vs system-side evidence construction.

If the agent searches perfectly, they collapse. But when grep-only fails because the agent picks bad terms, stops early, or miscounts, a system-side evidence packet can recover some of those failures. Next experiment should focus only on grep-fail cases and classify whether the win came from better search, better filtering, or better counting.
