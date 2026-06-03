# TLDR: long-context / grep / paging / RLM setup

## One-line takeaway

Grep-style memory is a strong baseline, but just splitting context into pages is not enough. The best results came from question-dependent search + notes and RLM depth-0, so the real RQ should be: what memory operation does each task need — lookup, notes, counting, or code search?

## What I am testing

I am testing different ways an agent can use very long context without just trusting one giant prompt.

Main question:

> When the source is huge, should the model read everything, search it, page through it, get pre-made notes, or write code over it?

This connects back to compaction because compaction is also a memory system: it keeps some state and destroys other state. The useful question is not only “how many tokens did we keep?” but “did we keep the facts needed for the future question?”

## Methods / arms

### 1. Full context

Paste the whole long source into the model prompt.

Simple version:

> give the model the whole book and ask the question.

### 2. File grep

Save the whole source as one file and let the agent use grep/python search.

Simple version:

> give the model a searchable file instead of pasting the whole book.

### 3. Model picks pages / paging

Split the source into many smaller `.md` page files. Give the model a page list. The model decides which pages to open.

Simple version:

> cut the book into pages and ask the model to choose the right pages.

This was meant to test if paging alone helps. It mostly did not.

### 4. Search + notes / old virtual context

Our code searches before the model answers. This is question-dependent.

Process:

1. Take the question.
2. Search the long source for likely relevant lines/snippets/facts.
3. Build a short note sheet from those matches.
4. Give only that note sheet to the model.
5. Model answers with 0 tool calls.

Simple version:

> grep + note-taking before the model sees anything.

Important: by “helper” I mean our benchmark code, not another model.

The note sheet can include:
- exact matching lines
- nearby snippets
- extracted facts like “Mary moved to the bathroom”
- candidate event lists/tables

It is not a generic summary. It is built from the question.

### 5. RLM depth-0

Recursive Language Model scaffold, but with no child calls. The source lives outside the prompt in a REPL, and the model writes code/searches over it.

Simple version:

> the model can write Python over the source instead of reading the whole source in prompt.

### 6. RLM depth-1 recursive

Same as RLM depth-0, but the model can call child RLMs on chunks/pieces of the source.

Simple version:

> the model can ask smaller model-workers to inspect pieces, then combine their answers.

This worked technically but did not improve results here.

## Main fixed result

Dataset: real BABILong + OOLONG panel, 250 tasks total.

Important: these runs are **without compaction**. This means this is testing memory access/search behavior, not compressed context behavior.

| Method | Strict score | Short read |
|---|---:|---|
| Full context | 36/250 | prompt stuffing baseline |
| File grep | 52/250 | strong simple baseline |
| Model picks pages | 37/250 | paging alone did not help |
| Search + notes | 59-62/250 | best non-RLM strict; best relaxed was 99/250 |
| RLM depth-0 | 74/250 | best exact score |
| RLM depth-1 recursive | 47/250 | slower and worse |

## What happened

- File grep was better than full context on this fixed setup.
- Paging was not enough. The model often has to choose the right pages, and that adds another failure point.
- Search + notes worked better because the search happens before the model answers, and the model only sees useful snippets/facts.
- RLM depth-0 worked best for exact lookup because it can write code/search over the source outside the prompt.
- RLM depth-1 recursion technically worked, but child calls often miscounted OOLONG D&D roll/spell events, so it got slower and worse.

## SWE-chat / LongMemEval status

- LongMemEval rendered tasks ran, but raw trajectories are too large for honest full-context/lossless claims.
- SWE-chat needs semantic/judge scoring. Exact string scoring is too harsh because answers can include different code examples while still being semantically correct.

## Why this matters for the RQ

The RQ should not just be:

> is grep better than full context?

That is too small.

Better RQ:

> what memory operation does each task type need?

Possible task types:

- exact lookup → grep/code search may be enough
- question-dependent fact lookup → search + notes helps
- first/last event questions → need event tracking
- counting questions → need structured counters
- coding chat questions → need semantic judge + file/state tracking
- compressed context questions → need to know which answer-critical facts survive compaction

## Main research hypothesis now

Long-context memory is not one thing.

Different tasks need different memory operations:

- lookup
- notes
- pages
- counters
- code search
- semantic judging

Compaction, retrieval, and paging are all lossy in different ways. The key is measuring which answer-critical state gets lost.

## What to explore next

### 1. Make retrieval comparison fair

Compare under the same agent setup:

- grep
- BM25
- embeddings/vector DB
- hybrid search

This connects directly to “Is Grep All You Need?”

### 2. Improve search + notes

Ablations:

- raw snippets vs cleaned notes
- 2k / 8k / 24k / 48k budgets
- question-dependent search vs generic summary
- with vs without nearby context
- with vs without reranking

### 3. Diagnose paging

Add oracle page experiments:

> if we give the model the correct page, can it answer?

This separates:

- failure to pick the right page
- failure to answer after seeing the right page

### 4. Fix OOLONG with structured counters

For OOLONG, retrieval alone is not enough.

Need:

- roll/spell event extractor
- first/last spell logic
- numeric count verifier
- then compare counter + retrieval vs RLM vs full context

### 5. Fix SWE-chat scoring

Need semantic/judge scoring because exact string match misses correct answers with different code.

### 6. Connect back to compaction

Compare:

- blind compaction
- question-aware compaction
- search + notes
- full context
- grep/code memory

Measure:

- exact entity retention
- answer-critical fact retention
- state loss
- compression ratio vs accuracy

## Short Slack version

Takeaway: grep-style memory is a strong baseline, but just splitting context into pages is not enough. On real BABILong + OOLONG without compaction, file grep got 52/250, search + notes got 59-62/250, and RLM depth-0 got 74/250 strict. So the RQ should move beyond “grep vs full context” toward which memory operation each task needs: lookup, notes, counting, or code search.
