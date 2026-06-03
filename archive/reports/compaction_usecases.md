# 10 Real-World Use Cases for Context Compaction

## 1. Coding Agents (SWE-bench / SWE-chat)

**Dataset:** SWE-chat (6,000+ real Codex sessions, 63,000 user prompts, 355,000 tool calls)
**Link:** huggingface.co/datasets/SALT-NLP/SWE-chat

**Why compaction matters:** Developers have 260-290 turn conversations. After ~150k tokens, Codex auto-compacts. If compaction drops file paths, variable names, or error messages, the agent makes wrong edits.

**Our data:** At 1M tokens, model gives up 40% of the time. With compression and a goal, drops to 0%.

---

## 2. Long Document QA (BABILong)

**Dataset:** BABILong (20 reasoning tasks, up to 10M tokens)
**Link:** huggingface.co/datasets/RMT-team/babilong

**Why compaction matters:** Single facts hidden in book-length text. Exact retrieval needed for names, locations, objects.

**Our data:** 43% raw accuracy, 60% with grep. 37 point retention-accuracy gap.

---

## 3. Multi-Document Aggregation (OOLONG)

**Dataset:** OOLONG (synthetic + real, aggregation over many local facts)
**Link:** huggingface.co/datasets/oolongbench/oolong-synth

**Why compaction matters:** Counting events, tracking timelines, comparing users across long transcripts. Each local fact is small. Dropping any destroys the aggregate.

**Our data:** 46% accuracy. 8 point gap — aggregation survives better than exact facts.

---

## 4. Continual Learning / Domain Adaptation (CLB)

**Dataset:** Continual Learning Bench (6 task types, multi-episode)
**Link:** github.com/pgasawa/continual-learning-bench

**Why compaction matters:** Agent fixes a bug in episode 1. Episode 2 needs that knowledge. If compaction drops it, the agent starts from scratch.

**Our data:** Sequential PRs on same repo. 8 tasks integrated. Semantic scores 12-24%.

---

## 5. Customer Support (Multi-turn Chat)

**Dataset:** MultiWOZ, Taskmaster, real support logs

**Why compaction matters:** Long support conversations. Agent needs to remember: user's account, previous solutions tried, specific error messages. Compaction drops details, agent repeats itself.

**Data point:** No direct experiment yet. Known failure mode from chatbot research.

---

## 6. Research Literature Review

**Dataset:** arXiv, Semantic Scholar, paper corpora

**Why compaction matters:** Reading 50+ papers for a lit review. Compaction summarizes each paper but may drop the one key number, method detail, or contradictory finding.

**Data point:** Our lit review comparison doc (outputs/optimized-compaction-memory-comparison.md) used compaction implicitly.

---

## 7. Legal Document Review

**Dataset:** LegalBench, Cuad, contract review datasets

**Why compaction matters:** 200-page contracts. Compaction to fit context window. If it drops a clause number or liability amount, the review is wrong.

**Data point:** No direct experiment yet. Known from legal NLP research.

---

## 8. Medical Record Analysis

**Dataset:** MIMIC, clinical notes

**Why compaction matters:** Patient history across years. Compaction summarizes but may drop: specific lab value, medication change date, allergy. Life-critical.

**Data point:** No direct experiment yet. Referenced in medical AI safety research.

---

## 9. Code Review (SWE-Pruner)

**Paper:** SWE-Pruner: Self-Adaptive Context Pruning for Coding Agents (arXiv:2601.16746)

**Why compaction matters:** Code review diffs are long. Context pruning decides what parts of the codebase to keep. Wrong pruning = missed bugs.

**Data point:** SWE-Pruner paper shows context pruning directly affects bug detection.

---

## 11. Debugging Sessions

**Real use:** Developer pastes error, AI suggests fix, error changes, repeat 20 times. Context = all previous errors + fixes.

**Why compaction matters:** Compaction drops earlier fixes. AI suggests an already-tried solution. Developer loses trust.

**Evidence:** SWE-chat traces show this pattern in real sessions.

---

## 12. Data Analysis Notebooks

**Real use:** AI writes pandas/SQL across 30 Jupyter cells. Context = all previous cells + outputs.

**Why compaction matters:** Compaction drops column names. AI references a deleted column. Entire analysis breaks.

**Evidence:** Kaggle, Colab, Jupyter AI assistants. Common failure mode.

---

## 13. Code Review Chains

**Real use:** PR has 15 review comments. AI addresses each one. Context = all comments + fixes.

**Why compaction matters:** Compaction drops comment 3. AI's fix for comment 12 breaks what comment 3 requested.

**Evidence:** SWE-Pruner paper. Real PRs on GitHub.

---

## 14. Meeting Summarization

**Real use:** AI transcribes 2-hour meeting. Summarizes action items. Context = full transcript.

**Why compaction matters:** Compaction drops action item #4. Follow-up email misses it. Someone is not assigned work.

**Evidence:** Otter.ai, Fireflies, Zoom AI Companion.

---

## 15. Project Onboarding

**Real use:** New developer asks AI about codebase. 100+ questions over days. Context = all Q&A.

**Why compaction matters:** Compaction drops early answers. AI repeats itself. Developer wastes time.

**Evidence:** Common in coding agent usage. SWE-chat has multi-session traces.

---

## 10. Agent Orchestration (Multi-Agent)

**Dataset:** SWE-chat orchestration traces, AutoGen, CrewAI logs

**Why compaction matters:** One agent delegates to another. The orchestrator compacts the subtask result. If it drops the error message or output format, the next agent acts on wrong information.

**Data point:** Our SWE-chat 1M tasks are orchestration traces: "worker-1 idle, read messages, assign next step."
