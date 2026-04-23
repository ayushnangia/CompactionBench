# Simple long-context harness compaction experiment

Status: draft v1
Date: 2026-04-21

## 1. Goal

Measure one simple question:

> If a long-context benchmark sample is injected into an agentic harness over many chat turns, does the harness still let the model answer correctly when compaction is **off** vs **auto**?

This spec intentionally avoids file-based task fixtures, `docs/` directories, and `.md` chunk reading. The benchmark context is injected directly into the harness conversation as repeated user messages.

The objective is to test **agent-harness memory behavior**, not file navigation and not the model's raw ability to open files or use tools.

---

## 2. Why this needs 1M+ context

Current target harness/model setups in this environment are already large-context:

- Claude Code with `claude-opus-4-7`, `claude-sonnet-4-6`, and `claude-haiku-4-5` reports a **200k-token** context window.
- Codex model metadata in the local CLI cache reports:
  - `gpt-5.4`: **272k** context window
  - `gpt-5.4-mini`: **272k** context window
  - `gpt-5.3-codex`: **272k** context window
  - `gpt-5.3-codex-spark`: **128k** context window

Therefore, if the task context is only 100k-200k, a large fraction of runs may never trigger meaningful harness compaction. To make compaction load-bearing, the main benchmark contexts should be **well above the raw model context window**, with **1M+ tokens** as the primary target.

---

## 3. Design principles

1. **Test harness compaction, not file navigation.**
   The agent should not need to read local benchmark files or use retrieval tools to access the task context.
2. **Keep the protocol minimal.**
   The primary comparison is only `off` vs `auto`.
3. **Prefer benchmarks where failure is attributable to length / memory pressure.**
   Synthetic or semi-synthetic retrieval-style benchmarks are better primary probes than deeply reasoning-heavy tasks.
4. **Inject context over many turns.**
   The conversation history itself should carry the long context so compaction matters.
5. **Keep everything else fixed.**
   Same task, same model, same prompts, same chunking; only compaction mode changes.
6. **Reject tool-assisted recoveries.**
   If the agent reaches out to tools or files to reconstruct context, that run is no longer a clean conversation-memory measurement.

---

## 4. Scope

### In scope for v1

- Direct multi-turn context injection into the harness conversation
- Conditions:
  - `off`
  - `auto`
- Harnesses:
  - Claude Code
  - Codex CLI
- Primary benchmarks:
  - RULER
  - BABILong
- Secondary realism benchmark:
  - LongBench v2, but only as a later realism slice rather than the primary metric
- Small, interpretable pilots first
- Accuracy as the main metric
- Logging whether compaction fired and whether the agent used tools

### Out of scope for v1

- File-based fixtures (`README.md`, `docs/chunk_XX.md`)
- Manual compaction conditions (`manual_generic`, `manual_preserving`)
- Source-broken / compression-broken variants
- Distractor padding machinery
- Large model × harness × condition sweeps before the simple path works
- Any benchmark that mainly tests tool use rather than conversation memory

---

## 5. Target harnesses, models, and settings

## 5.1 Claude Code

Recommended primary model:

- `claude-sonnet-4-6`

Recommended robustness models:

- `claude-opus-4-7`
- `claude-haiku-4-5` if a cheaper / weaker contrast is wanted

Recommended settings for this experiment:

- Use print mode with session persistence:
  - first turn via `--session-id <uuid>`
  - later turns via `--resume <uuid>`
- Use `--bare` for clean isolation from local hooks, plugins, CLAUDE.md discovery, and other user-environment effects.
- Output mode:
  - `-p --output-format stream-json`
- Disable tools completely:
  - `--tools ""`
- Keep reasoning pressure low because the task should be simple retrieval / retention:
  - `--effort low`
- Keep the working directory empty or irrelevant.

Compaction mapping:

- `off`: set environment variable `DISABLE_AUTOCOMPACT=1`
- `auto`: leave `DISABLE_AUTOCOMPACT` unset

This gives a clean off/auto switch for Claude Code.

Authentication note:

- In documented Claude Code behavior, `--bare` does **not** read local OAuth or keychain auth.
- Therefore, strict benchmark runs need either:
  - `ANTHROPIC_API_KEY`, or
  - `--settings` with an `apiKeyHelper`-based auth setup
- If only local OAuth is available, that is suitable for manual/dev usage but not for the clean benchmark mode because local user environment state is no longer fully isolated.

## 5.2 Codex CLI

Recommended primary model:

- `gpt-5.4`

Recommended secondary models:

- `gpt-5.4-mini`
- `gpt-5.3-codex`

Do **not** use `gpt-5.3-codex-spark` in the first pass because its 128k context window makes it a different regime.

Recommended settings for this experiment:

- Use non-interactive session mode:
  - first turn via `codex exec`
  - later turns via `codex exec resume <thread_id>`
- Output mode:
  - `--json`
- Run outside a git repo or in an empty temp dir:
  - `--skip-git-repo-check`
- Use a read-only sandbox:
  - `--sandbox read-only`
- Disable approvals at the CLI layer:
  - top-level `-a never`
- Keep live web search off:
  - do not pass `--search`
  - optionally force config override `-c web_search="disabled"`
- Keep model-side verbosity / reasoning low:
  - `-c model_reasoning_effort="low"`
  - `-c model_verbosity="low"`

Compaction mapping:

- `off`: set `-c model_auto_compact_token_limit=<very large number>` so the threshold is above the largest tested task
- `auto`: use default Codex behavior, or explicitly set the normal threshold if we later decide to pin it

Important note:

- Codex has built-in history compaction and a `model_auto_compact_token_limit` config field, so an off/auto experiment is plausible.
- When `model_auto_compact_token_limit` is unset, the docs say Codex uses model defaults, but we do **not** have a documented numeric threshold for those defaults.
- What we do know from the local Codex model cache is model metadata such as context window size; for example `gpt-5.4`, `gpt-5.4-mini`, and `gpt-5.3-codex` report a `272000` token context window, while `gpt-5.3-codex-spark` reports `128000`.
- Therefore, benchmark runs should prefer an explicit pinned threshold rather than relying on the hidden default.
- Codex also does not expose as clean a “disable all tools” switch as Claude Code. To keep the comparison clean, we must additionally log tool events and reject or separately label any run that used tools.

## 5.3 Cross-harness fairness rules

To keep Claude Code and Codex comparable:

- Use the **same task rows**
- Use the **same chunking**
- Use the **same chunk prompt**
- Use the **same final answer format**
- Keep web search off in both harnesses
- Run in an empty temp directory
- Reject or separately analyze runs that used tools

---

## 6. Benchmark selection

## 6.1 Primary benchmark: RULER

Why it fits:

- RULER generates synthetic long-context tasks with configurable sequence length.
- It is specifically designed for long-context evaluation.
- It supports simple retrieval-style tasks such as needle-in-a-haystack, which are well aligned with harness-memory testing.

How to use it here:

- Prefer simple tasks such as:
  - `niah_single_1`
  - `niah_multikey_1`
  - similar low-reasoning retrieval variants
- Generate contexts at:
  - `1M`
  - `2M`
  - optionally `512k` as a calibration point

Why it is primary:

- It minimizes model-reasoning confounds.
- It lets us attribute failures more directly to memory / compaction behavior.

## 6.2 Primary benchmark: BABILong

Why it fits:

- BABILong is explicitly a long-context benchmark with distributed facts hidden inside irrelevant background text.
- The released benchmark includes lengths up to:
  - `1M`
  - `10M`
- It is a very strong probe for “did the system preserve the relevant facts?” rather than “can the model solve a difficult novel reasoning problem?”

How to use it here:

- Use **`RMT-team/babilong`** as the source dataset for `1M` runs
- Do **not** use `RMT-team/babilong-1k-samples` for `1M`; it does not provide `1M` splits
- For the main Codex compaction sweep, start at `128k` and go upward, not at `4k`
- Start with the `1M` config for first stress validation
- Start with tasks `qa1`–`qa5` as the clean first pilot
- Extend to `qa6`–`qa10` after the basic path is stable
- Use `10M` only after the full pipeline is stable

Task-specific scoring notes:

- `qa1`–`qa7`, `qa9`, `qa10`: use `exact_ci`
- `qa8` (lists-sets): use a set-aware scorer because answers can be comma-separated sets such as `apple,football`

Why it is primary:

- It creates exactly the memory stress we want
- It keeps the task itself relatively controlled

## 6.3 Secondary realism benchmark: LongBench v2

What the public README says:

- contexts range from `8k` to `2M words`
- the majority are under `128k`
- the benchmark is intentionally reasoning-heavy and difficult even for humans

Why it is **not** the primary benchmark here:

- It tests deep understanding and reasoning, not just retention
- If performance drops, it can be unclear whether the failure came from:
  - harness compaction
  - model reasoning limits
  - question difficulty

How to use it here:

- Later realism slice only
- Only use rows whose context is comfortably above 1M-token-equivalent scale
- Treat it as an appendix / secondary result, not the main decision criterion

## 6.4 Not selected as the main 1M+ benchmark: InfiniteBench

InfiniteBench is valuable because it was designed so degradation should come from length rather than task novelty, but its README emphasizes `100k+` contexts rather than guaranteed 1M+ contexts. That makes it a good optional mid-scale calibration benchmark, but not the main 1M+ stress benchmark for this spec.

---

## 7. Task data format

The task should be a single JSONL row per benchmark sample.

Every task row should be validated with **Pydantic** before it is written or consumed by a runner. The same rule applies to run artifacts: each per-run JSON file should be validated against a Pydantic `RunRecord` model before being saved.

### Canonical row shape

```json
{
  "task_id": "RULER-niah_single_1-0001",
  "source_benchmark": "ruler",
  "source_task": "niah_single_1",
  "source_sample_id": "0001",
  "context": "<full raw benchmark context>",
  "question": "What is the special magic number for elephant?",
  "gold_answer": "75128",
  "gold_answer_aliases": [],
  "scorer": "exact_ci",
  "metadata": {
    "upstream_length": 1000000,
    "difficulty": null,
    "length_bucket": null
  }
}
```

### Required fields

- `task_id`
- `source_benchmark`
- `source_task`
- `source_sample_id`
- `context`
- `question`
- `gold_answer`
- `gold_answer_aliases`
- `scorer`

### Notes

- Store the **full raw context** in the row.
- Chunking happens at run time.
- No per-task directory is needed.

---

## 8. Benchmark-specific row mapping

## 8.1 RULER

Mapping:

- `context`: RULER haystack text
- `question`: extracted final question
- `gold_answer`: first item in `outputs`
- `gold_answer_aliases`: remaining items in `outputs`
- `scorer`: task-dependent, usually `exact_ci` or `substring_ci`

## 8.2 BABILong

Mapping:

- `context`: full long background-plus-facts text
- `question`: benchmark question
- `gold_answer`: benchmark answer
- `gold_answer_aliases`: task-specific if needed, else `[]`
- `scorer`: usually exact or substring-based depending on task formatting

## 8.3 LongBench v2

Mapping:

- `context`: sample `context`
- `question`: formatted MCQ prompt including A/B/C/D options
- `gold_answer`: correct option letter
- `gold_answer_aliases`: `[]`
- `scorer`: `multiple_choice`

---

## 9. Run protocol

## 9.1 Chunking

At run time, split `context` into chunks of approximately `chunk_tokens` tokens.

Default starting point:

- `chunk_tokens = 4000`

This is small enough to create many turns but large enough to avoid excessive protocol overhead.

Token estimation can be coarse initially, e.g. `~4 chars/token`.

## 9.2 Per-chunk prompt

For chunk `i` of `N`, send:

```text
Context chunk i/N.
Store this for later. Do not answer the final question yet.
Do not use tools. Do not browse. Reply only with: OK

<chunk text>
```

Desired assistant reply:

```text
OK
```

## 9.3 Final question prompt

After all chunks are sent, ask:

```text
Now answer the following question using only the context chunks given earlier.
Do not use tools. Return exactly one JSON object with one field: {"answer": "..."}
Do not include any extra text.

Question:
<question>
```

## 9.4 Conditions

### `off`
- Disable or effectively neutralize auto-compaction in the harness
- Send all chunks
- Ask final question

### `auto`
- Use the harness's normal auto-compaction behavior
- Send all chunks
- Ask final question

No other protocol changes are allowed.

---

## 10. Logging and scoring

Primary metric: **answer accuracy**.

Scoring rules:

- `exact`
- `exact_ci`
- `substring_ci`
- `multiple_choice`

### Per-run fields

Each run artifact should be emitted from a validated Pydantic model and should record at least:

- `task_id`
- `source_benchmark`
- `harness`
- `model`
- `condition`
- `chunk_tokens`
- `chunk_count`
- `context_tokens_est`
- `final_answer_raw`
- `final_answer_parsed`
- `correct`
- `parse_ok`
- `error`
- `duration_s`
- `compaction_event_count`
- `tool_event_count`
- `tool_names_used`

### Clean-run rule

Any run with tool usage should be either:

- excluded from the main metric, or
- reported separately as a contaminated run

because the goal is to test conversation-memory compaction, not recovery via tools.

### Aggregate outputs

Minimum summaries:

- accuracy by `(harness, model, condition)`
- paired delta `accuracy(off) - accuracy(auto)`
- compaction event rate by condition
- contaminated-run rate by condition
- parse success rate by condition

---

## 11. Minimal pilot plan

## 11.1 First sanity pilot

One harness, one model, two conditions:

- Claude Code
- model: `claude-sonnet-4-6`
- conditions:
  - `off`
  - `auto`
- tasks:
  - 5 RULER rows at `1M`
  - 5 BABILong rows at `1M`

Purpose:

- verify multi-turn injection works
- verify compaction actually fires in `auto`
- verify tool usage stays at zero

## 11.2 Second sanity pilot

Repeat the same with Codex:

- Codex CLI
- model: `gpt-5.4`
- conditions:
  - `off`
  - `auto`
- same task rows

## 11.3 Expansion only after pilots are clean

Then expand to:

- Claude Code `claude-opus-4-7`
- Codex `gpt-5.4-mini`
- optional LongBench v2 realism slice

---

## 12. Interpretation

### If `off` > `auto`

That is evidence that harness compaction is dropping or distorting information needed for the answer.

### If `off` ≈ `auto`

Possible interpretations:

1. compaction preserved what mattered
2. the tasks still were not long enough to force important compression
3. the tasks were too easy
4. the model solved the task from local cues before memory pressure mattered

### If both are poor

Possible interpretations:

1. the benchmark itself is too hard
2. the question format is noisy
3. the task is testing model reasoning more than memory
4. the harness used tools or otherwise deviated from the clean protocol

---

## 13. Known confounds and guardrails

### Confound: contexts too short

If contexts are below the harness/model memory regime, compaction may not matter.

**Guardrail:** primary evaluation uses 1M+ contexts.

### Confound: benchmark is too reasoning-heavy

A difficult benchmark can make failures ambiguous.

**Guardrail:** use RULER and BABILong as primary, LongBench v2 only as secondary realism.

### Confound: one-turn prompting

That tests the model's native long-context ability more than harness memory.

**Guardrail:** always inject context over many turns.

### Confound: intermediate summarization

That creates a second memory channel.

**Guardrail:** intermediate reply is only `OK`.

### Confound: tool use

Tool use changes the task into retrieval / recovery.

**Guardrail:** disable tools where possible, discourage them in the prompt, log tool events, and exclude contaminated runs.

---

## 14. Implementation direction for this repo

Add a parallel simple path rather than extending the existing file-fixture path.

### New pieces

- `specs/simple_long_context_experiment.md` (this document)
- Pydantic direct-task and direct-run schemas
- loaders for RULER and BABILong first, LongBench v2 later
- Claude Code direct runner
- Codex direct runner
- scorer for direct run artifacts

### Existing pieces to reuse

- answer parsing logic
- scoring helpers
- summary/report logic where possible

### Existing pieces to ignore for this path

- `tasks/generated/`
- `README.md` task fixtures
- `docs/chunk_XX.md`
- distractor machinery
- manual compaction conditions

---

## 15. Immediate next implementation step

Implement the smallest clean end-to-end path in this order:

1. direct-task schema
2. RULER direct loader
3. Claude Code direct runner with `off` and `auto`
4. logging for tool usage and compaction events
5. scorer summary
6. Codex direct runner with the same task rows
7. BABILong loader

Do not expand to larger matrices or realism-heavy benchmarks until the simple 1M+ harness-memory path is working cleanly.
