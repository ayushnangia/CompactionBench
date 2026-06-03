https://x.com/omarsar0/status/2055317577031975269?s=20
thanks @Dhruv Trehan for sharing this seems relevant to our work so will go through it

// Is Grep All You Need? //

They find that grep-style text search, when wrapped in the right agent harness, matches or beats embedding-based retrieval on coding-agent tasks.
This is relevant to our work because we are testing whether long context should be handled by:
- stuffing everything in prompt
- grep/search over files
- paging the context into smaller files
- question-dependent search + notes
- RLM / code-over-context style memory

older slack context:
- here are the qa types from BABILong where grep was better
- done with LongMemEval and SWE-chat
- for SWE-chat we probably need a better judge because output can include code examples that do not match exact answer string but are semantically right
- running other grep variants over BABILong to see if there are improvements

updated slack message draft:

update: went deeper on this grep / long-context thing, and added paging too. paging here just means dividing the long context into smaller `.md` / page files. this felt relevant after that grep tweet.

quick explanations:
- full context = paste the whole long source into the model prompt
- file grep = save the source as one file and let the agent use grep/python search
- model picks pages = split the source into many small page files, give the model a page list, and make the model decide which pages to open
- search + notes = our code does grep-like search before the model answers. this is question-dependent: given the question, it finds best-matching lines/snippets/facts, makes a short note sheet, and then the model answers from that note sheet. model uses 0 tools here.

I also added RLM runs:
- RLM depth-0 = model gets the source outside the prompt and writes code/searches over it
- RLM depth-1 = same thing, but it also calls child RLMs on chunks

on the fixed real BABILong + OOLONG set, all without compaction:
- full context: 36/250 strict
- file grep: 52/250
- model picks pages: 37/250
- search + notes / old virtual context: 59-62/250 strict, best relaxed was 99/250
- RLM depth-0: 74/250 strict, best exact score
- RLM depth-1 recursive: 47/250, slower and worse

current read:
grep-style methods are definitely strong, but the best simple variant is more like question-conditioned grep + notes, where our code searches first and only gives the model useful snippets/facts. RLM depth-0 also helps a lot for exact lookup because it can write code over the external source. Recursive depth-1 did not help yet, especially on OOLONG, because child agents miscount D&D roll/spell events.

important clarification:
by “helper” I do not mean another model. I mean our benchmark code. The code searches the source first, builds the note sheet, and then the model answers. The model itself does not use tools in search + notes.

what the note sheet looks like:
- exact matching lines from the source
- nearby snippets around those lines
- extracted facts like “Mary moved to the bathroom”
- sometimes a small candidate event list/table
- it is not a generic summary of the whole source; it is built from the question

why this matters for RQ:
the grep question alone is too small. The bigger question is what kind of memory operation each task needs:
- exact lookup: grep/code search can be enough
- question-dependent fact lookup: search + notes helps
- choosing pages manually: model can pick wrong pages, so paging alone did not help
- counting/first-last/event questions: retrieval alone is not enough, need a structured counter
- coding chats: exact scoring is not enough, need semantic judge/state tracking

next steps:
- compare grep/BM25/embedding/hybrid under the same agent setup, since that is the real “Is Grep All You Need?” question
- make search + notes cleaner with ablations: raw snippets vs notes, 2k/8k/24k budgets, question-dependent vs generic
- make paging diagnostic: test oracle pages to see if failure is wrong-page selection or answer failure
- build an OOLONG roll/spell counter instead of asking the model to count from transcript snippets
- add semantic/judge scoring for SWE-chat
- connect this back to compaction: blind compaction vs question-aware compaction vs search + notes, and measure which answer-critical facts survive

for OOLONG I think we need a proper roll/spell counter, not just more retrieval / recursion.

currently going through RLM-related work too because RLM depth-0 seems to work out of the box in a similar spirit to grep/code-over-context.

extra context from #continualbench / broader RQ issue:
- there are many adjacent threads now: LoRA as knowledge memory, CapTrack/forgetting, Grow Don't Overwrite, MSSR replay, FALCON fast-weight memory, self-distillation/SDFT/SDPO, out-of-context reasoning, LongMemEval, SWE-chat, OOLONG, and Continual Learning Bench
- this makes the project objective a bit unclear: is the main story compaction failure, grep vs full context, agent memory operators, or continual learning?
- I made a separate context doc for asking an LLM to help sharpen the RQ:
  - `docs/work/project_context_for_rq_finding_20th_may.md`

message draft for #continualbench:

I pulled together the context from the compaction / grep / paging / RLM experiments and also the related continual-learning threads people have shared here. Right now I think the objective is still not crisp enough: it could be about compaction failure, grep vs full context, memory operators for agents, or broader continual learning.

My current best read is that the RQ should not just be “is grep better than full context?” It should be more like: what kind of memory operation does each task need — exact lookup, notes, paging, counting, code search, or parametric update?

I am going to use the context doc to ask an LLM to help propose/refine 3-5 concrete research questions and then pick the most testable one with our current benchmarks.
