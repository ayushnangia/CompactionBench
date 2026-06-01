# Paras follow-up: grep vs grep+notes ablation

## Question

Paras's concern: if the model greps, ingests grep results, and reasons, why should `grep + notes` differ from grep-only? Also, whether grep results stay in context or are summarized into a separate file should not matter much.

## Experiment design

Panel: `data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl` (5 tasks)

Base model/harness: Codex CLI, `gpt-5.4-mini`, reasoning effort `low`, no compaction (`model_auto_compact_token_limit=2000000000`).

Arms:

| Arm | Who chooses searches? | Where is evidence? | Does answerer see full source? |
|---|---|---|---|
| `grep_file` | model | grep/tool outputs in session | yes, `full_context.txt` |
| `raw_snippets_prompt` | harness | raw grep-like snippets pasted | no |
| `raw_snippets_file` | harness | same raw snippets in `notes.md` | no |
| `structured_notes_prompt` | harness | structured virtual-context notes pasted | no |
| `structured_notes_file` | harness | same structured notes in `notes.md` | no |
| `cli_notes_same_session` | model | model writes `notes.md`, answers same session | yes |
| `cli_notes_two_stage` | model | stage 1 writes `notes.md`; fresh stage 2 answers only from notes | stage 2 no |

The new key arms are the two CLI-notes arms. They satisfy the requested setup: the CLI/model itself makes the notes with the question available.

## Commands

Harness notes / file-vs-prompt ablation:

```bash
uv run python scripts/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl \
  --root-dir artifacts/batches/paras_grep_notes_ablation_5task \
  --arm grep_file \
  --arm raw_snippets_prompt \
  --arm raw_snippets_file \
  --arm structured_notes_prompt \
  --arm structured_notes_file \
  --model gpt-5.4-mini \
  --reasoning-effort low \
  --verbosity low \
  --timeout-s 300 \
  --max-workers 5
```

CLI-made notes:

```bash
uv run python scripts/run_lossless_vs_grep_codex_parallel.py \
  --tasks data/benchmarks/confirmation/oolong_question_types_synth-256k_real-6ep.jsonl \
  --root-dir artifacts/batches/paras_cli_notes_ablation_5task \
  --arm cli_notes_same_session \
  --arm cli_notes_two_stage \
  --model gpt-5.4-mini \
  --reasoning-effort low \
  --verbosity low \
  --timeout-s 300 \
  --max-workers 2
```

Merged analysis:

```bash
uv run python scripts/analyze_lossless_vs_grep.py \
  --runs-root artifacts/batches/paras_grep_notes_ablation_5task/runs \
  --runs-root artifacts/batches/paras_cli_notes_ablation_5task/runs \
  --out-dir artifacts/analysis/paras_grep_notes_cli_ablation_5task \
  --title 'Paras grep vs notes vs CLI-made notes ablation' \
  --baseline-arm grep_file
```

## Results

Artifacts:

- `artifacts/batches/paras_grep_notes_ablation_5task/`
- `artifacts/batches/paras_cli_notes_ablation_5task/`
- `artifacts/analysis/paras_grep_notes_cli_ablation_5task/report.md`

Summary:

| Arm | Strict correct | Avg tools/run | Avg duration |
|---|---:|---:|---:|
| `grep_file` | 3/5 | 6.0 | 36.6s |
| `cli_notes_same_session` | 3/5 | 7.8 | 40.9s |
| `cli_notes_two_stage` | 3/5 | 7.4 | 53.0s |
| `raw_snippets_prompt` | 1/5 | 0.0 | 16.4s |
| `raw_snippets_file` | 1/5 | 3.2 | 22.4s |
| `structured_notes_prompt` | 1/5 | 0.0 | 12.8s |
| `structured_notes_file` | 1/5 | 5.6 | 28.0s |

Task-level highlights:

- Synthetic OOLONG tasks:
  - `grep_file`: 3/3
  - `cli_notes_same_session`: 3/3
  - `cli_notes_two_stage`: 3/3
  - harness notes: only 1/3
- Real D&D OOLONG tasks:
  - all arms failed strict, but grep was closest on rolls (`110` vs gold `114`), while CLI notes improved spells relative to grep (`36` / `34` vs grep `16`, gold `49`).

## Readout

Paras is basically right for the agentic version: when the model itself makes the notes, `grep_file`, `cli_notes_same_session`, and `cli_notes_two_stage` collapse to the same strict accuracy on this canary (3/5). The separate file itself is not the magic.

What changed in the earlier `grep + notes` result is not "notes file vs grep output in context". It is **who controls evidence selection and what evidence gets selected**:

- model-controlled grep + model-made notes behaves like grep-only here;
- harness-made raw/structured notes can be worse if the retriever misses or under-specifies evidence;
- for counting/aggregation, the important thing is not notes as a storage medium but a correct extraction/counting policy.

Better wording going forward:

> `grep + notes` should not be framed as fundamentally different from Claude Code-style grep-and-reason. It is a controlled ablation where retrieval/evidence construction is moved from the agent into the harness. If the agent makes equally good notes/searches itself, performance should match grep-only. The useful research question is which evidence-selection/counting policy is reliable, not whether notes are in a file.

## Suggested Slack reply

I think you're right — the clean distinction is not "grep output in context vs notes in a file." I ran a small ablation where Codex itself had the question, searched `full_context.txt`, wrote `notes.md`, and then answered. I also ran a two-stage version where a fresh Codex instance answered from only that self-made `notes.md`.

On the 5-task OOLONG canary:

- grep-only: 3/5
- CLI makes notes + answers same session: 3/5
- CLI makes notes, fresh CLI answers from notes only: 3/5
- harness-made raw/structured notes: 1/5

So for this canary, self-made notes basically collapse to grep-only. The separate file is not doing magic. The real variable is who selects/structures evidence. If the agent searches well, notes don't add much; if the harness gives bad/incomplete notes, it can hurt. For aggregation tasks, what we actually need is a reliable extraction/counting policy, not just "notes."
