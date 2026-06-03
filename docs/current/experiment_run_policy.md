# Experiment run policy

User preference: **do not re-run completed baseline arms unless explicitly requested.**

For future experiments:

1. If `full_context` and/or `grep_file` already exist for the same task panel, model, and settings, reuse those results in analysis instead of launching them again.
2. New batches should normally run only the new arms, e.g.:
   - `paged_context`
   - `virtual_context_8k`
   - `virtual_context_24k`
   - `virtual_context_48k`
   - future transparent/system paging variants
3. Combine old baseline rows with new-arm rows offline in the report.
4. Re-run baselines only when one of these changes:
   - task panel changes,
   - model changes,
   - prompt/protocol changes in a way that affects the baseline,
   - user explicitly asks for same-batch baselines.

Current note: The 1500-run OS-level batch includes baseline re-runs. Treat this as a mistake/overrun unless the user decides to keep it for same-batch comparison.
