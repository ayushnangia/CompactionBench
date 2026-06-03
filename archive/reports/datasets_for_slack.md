Here are the real datasets and how each simulates actual agent usage.

**CODING AGENTS**

SWE-chat (6,000 real Codex sessions)
https://huggingface.co/datasets/SALT-NLP/SWE-chat
→ Real developers using Codex. 63k prompts, 355k tool calls. Sessions hit 260+ turns. This is exactly what happens when someone uses Codex for a full workday. Compaction fires silently mid-session. We already ran this at 1M tokens — model gives up 40% of the time.

SWE-bench (2,294 real GitHub issues)
https://huggingface.co/datasets/princeton-nlp/SWE-bench
→ Real bugs from real repos. An agent fixes the bug, the conversation grows, compaction kicks in. Does the agent still remember the file structure from 30 turns ago?

**LONG CONTEXT MEMORY**

BABILong (20 reasoning tasks, up to 10M tokens)
https://huggingface.co/datasets/RMT-team/babilong
→ A single fact hidden in book-length text. Simulates an agent searching a massive codebase or document. We found a 37 point gap between "answer is there" and "model gets it right."

OOLONG (synthetic + real, aggregation)
https://huggingface.co/datasets/oolongbench/oolong-synth
https://huggingface.co/datasets/oolongbench/oolong-real
→ Counting events across long transcripts. Simulates an agent aggregating logs, commit history, or metrics. Aggregation survives compaction better than exact facts.

LongMemEval (long-term chat memory)
https://huggingface.co/datasets/xiaowu0162/LongMemEval
→ Tests whether a chat assistant remembers user facts across sessions. Simulates a personal AI assistant that needs to remember your preferences from last week.

**ENTERPRISE / PROFESSIONAL**

LegalBench (legal reasoning)
https://huggingface.co/datasets/nguha/legalbench
→ Contract review, clause extraction, legal QA. Simulates a lawyer using an agent to review a 200-page contract. Compaction drops a liability clause → missed risk.

MS MARCO (1M+ real search queries)
https://huggingface.co/datasets/microsoft/ms_marco
→ Real Bing queries with answers. Simulates a research agent answering questions from a knowledge base. Long context = many documents retrieved.

DialogSum (13k real dialogues)
https://huggingface.co/datasets/knkarthick/dialogsum
→ Real conversations with summaries. Simulates a meeting agent that transcribes and summarizes. Compaction drops an action item → follow-up misses it.

**GATED (need account)**

MIMIC-IV (clinical notes)
https://huggingface.co/datasets/mimic-iv/mimic-iv
→ Real patient records across years. Simulates a medical AI reviewing patient history. Compaction drops a medication change date → wrong treatment.

Cuad (contract review)
https://huggingface.co/datasets/cuad/cuad
→ 500+ commercial contracts with labeled clauses. Simulates a legal agent extracting specific terms.

QMSum (meeting summarization)
https://huggingface.co/datasets/qmsum/qmsum
→ Real meeting transcripts with query-summary pairs. Simulates an agent that needs to answer "what did we decide about the budget?" from a long transcript.
