# Results so far

This file is a compact human-readable summary of the main runs completed so far.

## What has been completed

### 1. BABILong qa1-qa10 Codex auto-compaction sweep
Batch:
- `artifacts/batches/babilong_codex_auto_high_models_parallel/20260422-123112`

Settings:
- models: `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`
- lengths: `128k`, `256k`, `512k`, `1M`
- condition: `auto`
- explicit compaction threshold: `150000`

Key takeaways:
- compaction starts around `256k`
- exact deterministic accuracy is very low
- judge-adjusted accuracy is much higher, meaning many failures are close but not exact
- compaction is heaviest at `1M`

Main numbers:
- total runs: `120`
- deterministic accuracy: `8.3%`
- judge-adjusted accuracy: `39.2%`
- runs with any compaction: `90/120`
- avg compaction events per run: `3.62`

More detail:
- `artifacts/batches/babilong_codex_auto_high_models_parallel/20260422-123112/analysis/report.md`

### 2. BABILong qa11-qa20 Codex auto-compaction extension
Batch:
- `artifacts/batches/babilong_codex_auto_high_models_qa11_to_20_s3/20260422-095719`

This run added reasoning families such as:
- coreference
- time reasoning
- deduction / induction
- positional reasoning
- path finding
- motivations

Important caveat:
- many later runs were hit by usage-limit failures
- so the raw total accuracy is not the cleanest view
- the resolved-only subset is more informative

Main numbers:
- total runs: `360`
- resolved runs: `123`
- deterministic accuracy: `14.7%` total, `43.1%` on resolved runs
- judge-adjusted accuracy: `28.3%` total, `82.9%` on resolved runs
- usage-limit failures: `237/360`

Resolved-only task highlights:
- stronger: `qa13`, `qa15`, `qa11`, `qa16`
- weaker: `qa19`, `qa17`, `qa20`, `qa14`

More detail:
- `artifacts/batches/babilong_codex_auto_high_models_qa11_to_20_s3/20260422-095719/analysis/report.md`

### 3. OOLONG-synth Codex auto-compaction sweep
Batch:
- `artifacts/batches/oolong_synth_codex_auto_high_models/20260423-173654`

Settings mirrored the BABILong Codex runs:
- same 3 models
- same lengths
- same `auto` condition
- same explicit compaction threshold

Task groups:
- `counting`
- `user`
- `timeline`

Key takeaways:
- the run completed cleanly
- compaction again begins at `256k`
- aggregation is easier than strict exact symbolic memory
- counting is easiest, user-linked aggregation is hardest

Main numbers:
- total runs: `108`
- resolved runs: `107`
- deterministic accuracy: `46.3%`
- runs with any compaction: `81/108`
- avg compaction events per run: `2.55`

By task group:
- counting: `58.3%`
- timeline: `44.4%`
- user: `37.1%`

More detail:
- `artifacts/batches/oolong_synth_codex_auto_high_models/20260423-173654/analysis/report.md`

## Cross-benchmark readout

A good simple summary is:

- **BABILong** is the better probe for exact fact survival under compaction.
- **OOLONG-synth** is the better probe for aggregation under compaction.
- Together they give a more useful picture than either benchmark alone.

Comparison files:
- `artifacts/analysis/oolong_vs_babilong/report.md`
- `artifacts/analysis/oolong_vs_babilong/summary.md`

## What to be careful about

- The large `artifacts/` directories are intentionally **not committed** to GitHub.
- The repo contains the code, specs, tests, and analysis scripts needed to reproduce the workflow, but not all heavyweight run outputs.
- The current prepared OOLONG long set was built from one reliable OOLONG subset (`negation`) to keep the first sweep stable.
