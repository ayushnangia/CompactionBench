# Literature Alignment

This note keeps the paper names, citations, and experiment claims straight.

## Short Version

PEEK is relevant and should be cited, but our runs are not a full PEEK paper reproduction.

Our PEEK runner is best described as a PEEK-style context-map baseline for CompactionBench. It checks whether a small reused map helps on our panels. It does not exactly match the paper setup, and most of our current panels do not give PEEK the repeated-context setting where it is strongest.

## Correct Citations

Use these IDs:

| Name | Full name | Correct citation |
|---|---|---|
| PEEK | PEEK: Context Map as an Orientation Cache for Long-Context LLM Agents | arXiv:2605.19932 |
| ACE | Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models | arXiv:2510.04618 |
| ACON | ACON: Optimizing Context Compression for Long-horizon LLM Agents | arXiv:2510.00615 |

Do not copy the local upstream PEEK clone metadata blindly. In this workspace, `artifacts/repos/peek/CITATION.cff` and `artifacts/repos/peek/pyproject.toml` point the paper URL at `2510.04618`, which is ACE, not PEEK. The local upstream README mostly uses the right PEEK ID, but its paper-preview image link also points at `2510.04618`. The public PEEK citation and arXiv page use `2605.19932`.

BibTeX for PEEK:

```bibtex
@misc{gu2026peekcontextmaporientation,
  title={PEEK: Context Map as an Orientation Cache for Long-Context LLM Agents},
  author={Zhuohan Gu and Qizheng Zhang and Omar Khattab and Samuel Madden},
  year={2026},
  eprint={2605.19932},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2605.19932}
}
```

## What PEEK Actually Claims

PEEK keeps a small context map inside the prompt for recurring external context, such as the same corpus, repo, or dataset queried many times.

The blog frames this as a grounded-reasoning problem: agents repeatedly work against external material that is too large to keep in the model window, but the same external material comes back across many tasks. The missing piece is not more raw context, and not only retrieval. It is a durable map of what the agent has learned about that external material.

The motivating example is an analyst repeatedly querying a large feedback corpus. A human would keep a lightweight table of contents, notes on key entities, useful constants, inspected regions, and common intermediate results. PEEK tries to give an agent that kind of reusable orientation aid.

The map stores reusable orientation knowledge:

- what the context contains,
- how it is organized,
- useful schemas, constants, labels, and entities,
- where useful evidence tends to live.

The paper's cache policy has three pieces:

- Distiller: extracts reusable knowledge from a run.
- Cartographer: turns that into structured map edits.
- Evictor: keeps the map under a fixed token budget.

Plain distinction:

- PEEK is active external-context state.
- ACE is an evolving task/playbook context.
- ACON is context compression for long-horizon agents.
- RAG/file search retrieves raw pieces for the current query.
- KV-cache work optimizes hidden model states, not what semantic facts the agent remembers.

## Blog-Specific Context

The blog is useful because it says the design problem in plainer terms:

1. Existing context tools preserve different things.
   Shared chat preserves prior trajectory, history compaction preserves a short task record, RAG/search preserves access to raw pieces, and prompt learning preserves task strategy. None of those is mainly a maintained artifact about the external context itself.

2. PEEK is not a KV cache.
   KV-cache methods work on model internals and serving efficiency. PEEK works at the agent level: a human-readable semantic artifact that says what the recurring context contains and how to use it.

3. PEEK is meant for repeated same-context workloads.
   The blog repeatedly stresses corpora, repos, enterprise records, and datasets that the agent queries again and again. This matters for our interpretation: panels with one question per context are bad tests of PEEK.

4. The context map should be structured and editable.
   The blog highlights stable map entries, structured sections, and an update policy. This is why a plain summary is not the same thing as PEEK.

5. More text in the prompt was not the winning idea.
   The PEEK authors report trying raw prefixes, sub-goal retrieval, retrieval over an ACE-style playbook, runtime feedback, and behavior-only instructions. Those variants were weaker or harmful on their subset. Their conclusion is that the agent needs a compact persistent understanding of the context, not just another chunk of text.

6. PEEK has a real limitation.
   If the agent's interactions do not reveal reusable context knowledge, the map has little to cache. Different agents may need different maps because they inspect and use context differently.

## Full Blog Outline

This is the full blog context, reduced to the actual claims and implications:

| Blog section | What it adds |
|---|---|
| tl;dr | PEEK targets grounded-reasoning agents over recurring external context. It uses a context map maintained by Distiller, Cartographer, and Evictor. |
| Prelude | The motivating systems idea is an agent-side semantic cache, not a vector DB and not a KV cache. |
| Analyst example | The recurring-context setting is like repeatedly querying one large feedback corpus; a human keeps notes about layout, entities, inspected regions, and reusable intermediate results. |
| What existing methods miss | Shared chat, history compaction, RAG/offloading/compaction, and prompt learning preserve useful things, but not a maintained artifact about the external context itself. |
| Context map | A context map is prompt-resident, bounded, persistent, editable, and human-readable. It is closer to a maintained table of contents/glossary/schema note than a conversation summary. |
| How PEEK works | Each query gets the current map. After the query, a policy reads the trajectory and edits the map for future queries. Updates can be online or frozen after enough warmup. |
| Main results | Paper setting is repeated questions per context on OOLONG and CL-bench. PEEK beats ACE in the reported paper results. |
| Cost and iterations | PEEK is presented as better quality with fewer iterations and lower cost than ACE in their setup. |
| Generalization | Paper/blog report gains across GPT-5.5, Qwen3-Coder-Next-FP8, and Codex, not just the default RLM setup. |
| Not KV cache | KV-cache methods reduce serving cost for fixed prompts. PEEK decides what semantic context knowledge should stay visible to the agent. |
| Failed variants | Raw prefix, sub-goal retrieval, ACE-playbook retrieval, runtime feedback, and behavior-only instructions were weaker or harmful. |
| Future work | Adaptive cache size, trained Distiller, other reusable artifacts, and collections of caches usable through programs or parallel agents. |
| Limitation | If the agent does not uncover transferable facts, there is little useful information to cache. |

## Related Work Mentioned By The Blog

The blog situates PEEK around these systems/papers:

| Area | Items mentioned | Why it matters here |
|---|---|---|
| Agent backbones | Claude Code, Codex CLI, RLM, Hermes Agent | PEEK is intended to sit above different agents, not only one scaffold. |
| Grounded reasoning | OfficeQA Pro | Names the broader problem: agents answer using large external material. |
| Passive external context | RAG, MemAgent, Context-Folding, ReSum | These keep access to raw/condensed material but do not maintain a map about the context. |
| Prompt/context learning | ACE, GEPA, Dynamic Cheatsheet, Reflexion | These preserve strategies or playbooks, not necessarily reusable external-context knowledge. |
| Benchmarks | OOLONG, CL-bench | PEEK paper uses repeated tasks over shared contexts, which is the key evaluation condition. |
| Model/generalization checks | GPT-5.5, Qwen3-Coder-Next-FP8, Codex | PEEK is claimed to generalize across base LMs and agent architectures. |

## Upstream Implementation Context

Local clone: `artifacts/repos/peek`.

Package shape:

- install name: `peek-ai`
- core dependency: `tiktoken`
- optional provider extras: `openai`, `anthropic`, `gemini`, `all`
- main public API: `CachePolicy`, `ContextMap`, `Distiller`, `Cartographer`, `evict`, `LMClient`
- map operations: `ADD`, `DELETE`, `REPLACE`
- item tags: `helpful`, `harmful`, `neutral`, `stale`
- default map sections: `context_roadmap`, `context_understanding`, `domain_constants`, `parsing_schema`, `reusable_results`

Policy behavior:

- `CachePolicy.update(...)` takes the latest trajectory and question.
- It updates only for the first `evolve_steps` calls unless `evolve_steps` is unlimited.
- The Distiller analyzes orientation vs question-specific work.
- The Cartographer converts the analysis into map edits.
- The Evictor keeps the map under `token_budget`.
- Eviction uses accumulated item scores: helpful increases score; harmful/stale decreases score; neutral leaves score unchanged.

The upstream prompts make the core rule explicit in implementation terms: cache understanding, not answers. High-value map entries are structural understanding, exact domain constants, entity/concept inventories, global summaries, and reusable aggregate results. Low-value or forbidden entries are one-off answers, raw dumps, long excerpts, generic advice, and brittle surface-count results.

## Our PEEK Setup

Runner:

```bash
uv run python scripts/run/run_peek_codex_sequential.py ...
```

What it does:

- groups tasks by exact context hash,
- keeps one context map per group,
- writes the full context to `context.txt`,
- adds the current map to the Codex prompt,
- uses upstream `peek.CachePolicy` when available,
- updates the map with `--peek-updater codex` by default.

Important difference from the paper:

- The paper's main experiments use RLM with GPT-5-mini and report OOLONG plus CL-bench.
- Our default updater uses Codex CLI, not the paper's OpenAI chat-completions client.
- Our panels often have too few repeated questions per exact context.
- So the right claim is "PEEK-style baseline wired and tested", not "PEEK reproduced".

## Our Results So Far

| Run | Result | Readout |
|---|---:|---|
| 2-task OOLONG smoke | 2/2 correct | plumbing works; map cached useful layout |
| 5-task OOLONG canary | 3/5 correct | synthetic shared context worked; real D&D count tasks failed |
| 20-task cross-benchmark panel | 6/20 correct | poor PEEK test because 17 contexts for 20 tasks |
| 250-task real lossless panel | 46/250 strict | below grep_file 52/250 and virtual_context_24k 62/250 |
| hierarchy canary | 20/20 | too easy; not evidence that PEEK beats anything |

Best interpretation:

PEEK is mechanically integrated, but our existing panels are not a clean test of the paper's central advantage. The next fair PEEK test should use many questions over the same few contexts and compare warmup counts.

The blog makes this caveat stronger, not weaker. A fair PEEK evaluation should be designed around recurring-context use, because that is the setting the system is built for.

## What To Claim

Safe:

- PEEK is directly related because it maintains a prompt-resident map for repeated external contexts.
- Our runner implements a PEEK-style context-map arm with upstream `peek.CachePolicy`.
- On our current 250-task real panel, PEEK did not beat file search or virtual context on strict accuracy.
- PEEK needs a repeated-context stress test before being used as a headline comparison.

Avoid:

- Do not say our PEEK results reproduce the paper.
- Do not say PEEK failed in general; our panels are not the paper's ideal setting.
- Do not cite `2510.04618` as PEEK. That is ACE.
- Do not treat ACON as the same thing as PEEK or ACE.

## Sources

- PEEK arXiv: https://arxiv.org/abs/2605.19932
- PEEK blog: https://zhuohangu.github.io/blog-post-peek/
- PEEK blog bibliography: https://zhuohangu.github.io/assets/bibliography/peek.bib
- PEEK repo: https://github.com/zhuohangu/peek
- ACE arXiv: https://arxiv.org/abs/2510.04618
- ACON arXiv: https://arxiv.org/abs/2510.00615
- Local PEEK paper text: `artifacts/papers/peek_2605.19932v1.txt`
- Local PEEK upstream clone: `artifacts/repos/peek`
- Local PEEK run notes: `archive/work/peek_context_map_update_2026-05-25.md`
- Local 250-task PEEK run notes: `archive/work/peek_real_lossless_250_run_2026-05-25.md`
