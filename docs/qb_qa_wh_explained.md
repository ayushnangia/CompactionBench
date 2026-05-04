# QB vs QA vs WH — What is the difference?

Three ways to compress the same long context into ~150 tokens.

## The task

Context (~158k tokens) contains a multi-step update about the default model:

```
Initially: gpt-5.4-mini
Changed to: gpt-5.3
Changed to: gpt-5.4
Final: claude-sonnet-4 ← this is the answer
```

Question: "What is the current default model?" Gold: `claude-sonnet-4`

## What each mode knows

| Mode | Compressor sees | What happens |
|---|---|---|
| **QB** (query-blind) | Just the raw text. No question. No hint. | Picks facts that look rare or novel. Keeps filler text like "someone mentioned a VSCode extension." Misses the update entirely. |
| **QA** (query-aware) | Raw text + exact question: "What is the current default model?" | Filters for model-related facts. Keeps the update chain. Preserves the answer. |
| **WH** (weak-hint) | Raw text + task type: "This is about a current value. Find the relevant value." | Filters for update-last-value facts. Keeps the answer without needing the exact question. |

## Scores on 50 recalibrated tasks (partial)

| Mode | Accuracy | N |
|---|---:|---:|
| Raw (no compression) | 61% | 31 |
| QB | 30% | 10 |
| QA | 50% | 10 |
| WH | 71% | 14 |

## The key insight

You do not need the exact question. A task-type hint ("find the current value") may be enough to guide compression. If this holds at scale, it means real agent compaction could work with coarse relevance signals — it does not need to know what you will ask later.
