Link to channel and RQ/exploration doc (constant, no need to change).

Trying to understand and explore compaction / long context memory for 128k to 1M+ and beyond. Main question is still: when context is compressed, searched, paged, or stored outside the prompt, what exact information survives and what disappears? Especially names, numbers, places, file/state info, and event counts.

Related background I am still connecting to this:
- Memento paper: https://github.com/microsoft/memento/blob/main/docs/memento.pdf
- “Is Grep All You Need?” discussion / tweet: grep-style search can be very strong when wrapped in the right agent setup, so this is relevant for agent memory and long-context retrieval.
- Recursive Language Models (RLMs): exploring because they work a bit like grep/code-over-context out of the box, with the source outside the prompt and the model writing code/search over it.

What did you get done last week (a couple of bullet points)
- Added more real task coverage beyond just BABILong:
  - SWE-chat from Hugging Face
  - LongMemEval tasks
  - OOLONG-real tasks
- Ran full context vs file grep on real BABILong + OOLONG.
- Added paging experiment:
  - source is split into many smaller `.md` / page files
  - model gets a page list
  - model decides which pages to open
  - simple name: model picks pages
- Added search + notes experiment:
  - our code does question-dependent grep-like search first
  - it pulls best-matching lines/snippets/facts
  - it makes a short note sheet
  - model only sees that note sheet and answers
  - model itself uses 0 tools here
- Added Recursive Language Model runs:
  - RLM depth-0: model gets source outside prompt and writes code/searches over it
  - RLM depth-1 recursive: same, but it also calls child RLMs on chunks

Summary of key experiments/results (a couple of bullets, link to Slack for details)

Older compaction finding still holds:
- When AI context gets compressed, exact facts, names, numbers, places disappear faster than vague meaning. There is selective destruction of state while keeping general-sounding information. This might explain why coding agents can forget which file they were editing but still sound confident.
  - https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777033684252529
- When the compressor did not know the question, it kept the wrong facts every time (0/5 correct). When it knew the explicit instruction of what we want, it kept the right facts and improved performance (3/5 correct).
  - https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777455915871779
- GPT-5.4 recalls perfectly with full context. After compression, it fails. Similar to gpt-5.4-mini. Possible direction: test whether stronger general benchmark score means more compression resilience.
- Same finding as previous week but with more rigor for experiments:
  - https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777906883653059
- Weak hints in prompt might be one of the easiest additions for better downstream results:
  - https://lossfunk.slack.com/archives/C0AJ17GPHNX/p1777906941848689

New grep / paging / RLM results:
- Fixed real BABILong + OOLONG panel, all without compaction:
  - full context: 36/250 strict
  - file grep: 52/250 strict
  - model picks pages: 37/250 strict
  - search + notes / old virtual context: 59-62/250 strict, best relaxed 99/250
  - RLM depth-0: 74/250 strict, best exact score
  - RLM depth-1 recursive: 47/250 strict, slower and worse
- Important interpretation:
  - file grep is a strong simple baseline
  - splitting into pages and asking the model to pick pages did not help
  - search + notes worked better because the search happens before the model answers, and the model sees only useful snippets/facts
  - RLM depth-0 worked best for exact lookup because it can write code/search over the source outside the prompt
  - RLM depth-1 recursion technically worked, but did not improve results here; child calls often miscounted D&D roll/spell events on OOLONG
- SWE-chat + LongMemEval status:
  - LongMemEval rendered tasks ran, but raw trajectories are too large for honest full-context/lossless claims
  - SWE-chat needs a better semantic/judge scorer because outputs can be correct in meaning but not exact string match, especially when code examples are involved

What this means for the RQ / what is still not solved
- The basic “grep vs full context” question is probably too small by itself. It is useful as a baseline, but not the full RQ.
- Better RQ framing:
  - What kind of memory operation is needed for each task type?
  - Exact lookup may need grep/code search.
  - Question-conditioned fact extraction may need search + notes.
  - Counting / first-last / event aggregation may need structured counters, not just retrieval.
  - Long coding chats may need semantic judging and state/file tracking, not exact string matching.
- Main current hypothesis:
  - Compaction and retrieval are both lossy memory systems.
  - The important thing is not only “did we keep enough tokens?” but “did we keep the right state for the future question?”
  - Question-aware memory beats blind compression, but only when the question exposes what state matters.
- Need to be careful not to overclaim:
  - Do not say grep universally beats full context.
  - Do not say vector DBs are useless.
  - Do not say recursive RLMs failed in general.
  - Current result is narrower: on our fixed real BABILong + OOLONG setup, grep-like/code-like memory access was often better than prompt stuffing, and generic recursion was not enough for counting-heavy OOLONG.

What more to explore next
- Make the RQ less “grep vs full context” and more about task classes:
  - exact lookup
  - multi-hop lookup
  - first/last event questions
  - counting questions
  - state tracking across edits/files
  - semantic coding answers
- Run ablations for search + notes:
  - raw grep snippets vs cleaned notes
  - different note budgets: 2k / 8k / 24k / 48k
  - question-dependent search vs generic summary
  - with/without nearby context around matched lines
  - with/without reranking
- Make paging more fair / diagnostic:
  - add oracle page upper bound: if the correct page is given, can the model answer?
  - add better page table / page previews
  - measure whether failure is from choosing wrong pages or answering wrong after finding right pages
- For OOLONG:
  - build a real roll/spell event extractor
  - count events with code instead of asking the model to count from transcript snippets
  - verify first/last spell logic and numeric answers
  - then test retrieval + structured counter vs RLM vs full context
- For SWE-chat:
  - add semantic/judge scoring
  - exact string scoring is too harsh because correct answers can include different code examples
- Compare grep/BM25/embedding/hybrid retrieval under the same agent setup:
  - this is the direct connection to “Is Grep All You Need?”
  - need same task panel, same budget, same model, same scoring
  - this would answer whether vector DB adds value beyond strong lexical search in our setting
- Connect back to compaction:
  - compare blind compaction vs question-aware compaction vs search + notes
  - track entity/state survival before and after compaction
  - possible metrics: exact entity retention, answer-critical fact retention, entropy/state loss, compression ratio vs answer accuracy
- Maybe still explore local activation/probe work, but only after the task-level behavior is cleaner:
  - linear probes / activation maps for local MLX models during compaction
  - question: can we see which facts/states are being dropped?

How fast are you going (1-5, where 5 is your personal best in a long time)? What would accelerate your progress?
3. More concrete progress this week because the benchmark arms are now running, but the RQ needs tightening. The fastest accelerator would be deciding whether the main story is:
- compaction destroys answer-critical state,
- grep/code memory is a strong baseline for long context,
- or different task types need different memory operators.

Specific areas where you want input from others (optional)
- Is the best next RQ framing “memory operators by task type” instead of just “grep vs full context”?
- For the vector DB angle: what embedding baseline should be considered fair against grep/BM25?
- For SWE-chat: what judge/scoring style should we trust for semantically correct but non-exact answers?

Status of pending preprints/papers/blog posts
Nothing as a paper yet. Current output is internal benchmark/report material. Possible blog angle later: “Long-context memory is not one thing: exact lookup, notes, pages, and counters fail differently.”
