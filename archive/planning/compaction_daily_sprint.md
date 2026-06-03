# Compaction Improvement — Daily Sprint Plan

## The core question

Can we make long-running agents remember what matters by improving compression, tool access, and relevance signals?

## Sprint goal

Ship one technical report with:
1. A diagnosis: what compaction destroys and why
2. A fix: tool-accessible compression that recovers accuracy
3. A metric: the retention-accuracy gap as a diagnostic for other researchers

---

## Week 1: Tool-accessible compression

### Monday AM — Baseline the grep experiment
- [ ] Run grep experiment on ALL BABILong tasks (qa1-20, all lengths: 128k, 256k, 512k, 1M)
- [ ] Record accuracy per task per length
- [ ] Compare: raw context injection vs grep on original file
- **Deliverable:** Table of grep accuracy by length

### Monday PM — Understand grep failures
- [ ] For each grep failure, check: did the model NOT run grep? Or run wrong command? Or pick wrong result?
- [ ] Categorize failures: no grep, wrong grep, wrong selection
- [ ] Write the diagnosis: "Grep fails because..."
- **Deliverable:** Failure taxonomy for grep experiment

### Tuesday AM — Build compressed ledger format
- [ ] For each BABILong task, extract: entities, locations, key facts, file paths (simulated)
- [ ] Store as structured JSON: `{"entities": [...], "locations": [...], "facts": [...]}`
- [ ] Test: can the model answer from the ledger alone?
- **Deliverable:** Compressed ledger generator

### Tuesday PM — Ledger vs raw baseline
- [ ] Run BABILong with ledger compression
- [ ] Compare: raw context vs grep vs ledger
- [ ] Hypothesis: ledger beats grep because facts are pre-extracted
- **Deliverable:** Three-way comparison table

### Wednesday AM — Build grep hint compression
- [ ] During compression, record: "grep -i 'mary.*bathroom' → line 4154"
- [ ] Store these hints in the compressed context
- [ ] Test: does the model use the hints?
- **Deliverable:** Hint-enabled compression

### Wednesday PM — Hint vs no-hint comparison
- [ ] Run all BABILong tasks with and without grep hints
- [ ] Measure: accuracy, hint usage rate, time to answer
- **Deliverable:** Hint effectiveness table

### Thursday AM — Scale to OOLONG
- [ ] Adapt grep experiment for OOLONG-synth tasks
- [ ] OOLONG needs aggregation (counting, timeline) — grep is less natural
- [ ] Test: can grep help with aggregation tasks?
- **Deliverable:** OOLONG grep baseline

### Thursday PM — SWE-chat grep experiment
- [ ] Write full conversation to file, tell model to grep for answers
- [ ] Test on 5 SWE-chat 1M tasks
- [ ] Measure: does grep fix the "model gives up 40%" problem?
- **Deliverable:** SWE-chat grep results

### Friday AM — Budget sweep
- [ ] Compress BABILong at: 50, 100, 200, 500, 1000, 2000, 5000 tokens
- [ ] Measure accuracy at each budget
- [ ] Find the inflection point where accuracy recovers
- **Deliverable:** Accuracy vs budget curve

### Friday PM — Week 1 synthesis
- [ ] Write one-page summary: what we learned about tool-accessible compression
- [ ] Best approach: ledger? hints? grep? combination?
- **Deliverable:** Week 1 findings doc

---

## Week 2: Relevance signals

### Monday AM — Task-type classifier
- [ ] Build a simple classifier: given a question, predict the task type
- [ ] Categories: location, entity, count, yes/no, path, temporal
- [ ] Test accuracy on BABILong questions
- **Deliverable:** Task classifier

### Monday PM — Weak-hint scaling
- [ ] Run weak-hint compression on 50 recalibrated tasks
- [ ] Compare: query-blind vs weak-hint vs query-aware
- [ ] Does weak-hint consistently match query-aware?
- **Deliverable:** Weak-hint at scale results

### Tuesday AM — Dynamic hint selection
- [ ] Instead of fixed task labels, let the compressor pick the most relevant hint
- [ ] "This is about locations" vs "Find current values" vs "Count occurrences"
- [ ] Test: does dynamic hint beat static hint?
- **Deliverable:** Dynamic vs static hint comparison

### Tuesday PM — Hint from conversation context
- [ ] Extract hints from the conversation itself: "the user keeps asking about file paths"
- [ ] Use conversation turns preceding the question as hint source
- [ ] Test: does conversation-derived hint work?
- **Deliverable:** Conversation-context hint results

### Wednesday AM — OOLONG hints
- [ ] Design task-type hints for OOLONG: "count events" vs "list timeline" vs "compare users"
- [ ] Run weak-hint on OOLONG-synth
- **Deliverable:** OOLONG hint results

### Wednesday PM — SWE-chat hints
- [ ] Design hints for SWE-chat: "next action" vs "code review" vs "debug"
- [ ] Run on SWE-chat 1M tasks
- **Deliverable:** SWE-chat hint results

### Thursday AM — Hint saturation
- [ ] Test: at what point does giving more hints stop helping?
- [ ] Vary hint specificity: none → task type → task subtype → exact topic
- [ ] Find the cheapest effective hint
- **Deliverable:** Hint saturation curve

### Thursday PM — Combine hints with grep
- [ ] "Compress with hint + grep recovery" on BABILong
- [ ] The hint helps the compressor. Grep helps the model.
- [ ] Test: combined approach accuracy
- **Deliverable:** Combined approach results

### Friday AM — Scoring pipeline
- [ ] Build automatic scorer selector: substring for BABILong, ROUGE for SWE-chat, numeric for OOLONG
- [ ] Apply to all existing batches
- [ ] Compare: binary vs semantic accuracy
- **Deliverable:** Scoring pipeline

### Friday PM — Week 2 synthesis
- [ ] Write one-page summary: what we learned about relevance signals
- [ ] Best hint strategy: task-type? conversation-derived? dynamic?
- **Deliverable:** Week 2 findings doc

---

## Week 3: Information-theoretic approach

### Monday AM — Token frequency analysis
- [ ] For each BABILong task, compute token frequency of answer-bearing sentence vs filler
- [ ] Hypothesis: answer tokens are rarer
- [ ] Test: does frequency predict survival after compression?
- **Deliverable:** Token frequency analysis

### Monday PM — Entropy-based selector improvement
- [ ] Current entropy uses: rarity, entities, numbers, updates
- [ ] Test each feature's contribution by ablating one at a time
- [ ] Find which features matter most
- **Deliverable:** Feature ablation results

### Tuesday AM — Small model selector
- [ ] Train a tiny classifier to predict "does this sentence contain the answer?"
- [ ] Use BABILong training tasks (qa1-10) to train, test on held-out (qa11-20)
- [ ] Compare against heuristic entropy
- **Deliverable:** Learned selector baseline

### Tuesday PM — Selector transfer
- [ ] Test: does the BABILong-trained selector work on OOLONG? SWE-chat?
- [ ] If not: fine-tune or train per-benchmark selectors
- **Deliverable:** Transfer results

### Wednesday AM — Budget optimality
- [ ] For each task, find the minimum budget that achieves 80% of raw accuracy
- [ ] Compare across tasks: which tasks need more budget?
- **Deliverable:** Optimal budget per task

### Wednesday PM — Budget allocation
- [ ] If total budget is fixed, how should it be split across turns?
- [ ] Uniform? More to early turns? More to recent turns?
- [ ] Test different allocation strategies
- **Deliverable:** Budget allocation results

### Thursday AM — Combine all improvements
- [ ] Best compressor: learned selector + task hints + grep recovery hints
- [ ] Run on BABILong, OOLONG, SWE-chat
- [ ] Compare against raw context and naive compression
- **Deliverable:** Best compressor results

### Thursday PM — Ablation study
- [ ] Remove each component one at a time
- [ ] Measure impact on accuracy
- [ ] Find the most important component
- **Deliverable:** Ablation table

### Friday — Write technical report
- [ ] Consolidate all findings into one document
- [ ] Motivation → Method → Results → Discussion
- [ ] Ready for review
- **Deliverable:** First draft of tech report

---

## Week 4: Polish and ship

### Monday — Internal review
- [ ] Share draft with team
- [ ] Collect feedback
- [ ] Identify gaps

### Tuesday — Address gaps
- [ ] Run missing experiments
- [ ] Fix weak claims
- [ ] Add error bars / confidence intervals

### Wednesday — Visual polish
- [ ] Update HTML slides with final results
- [ ] Create one clean summary chart
- [ ] Write tweet-length summary

### Thursday — External review
- [ ] Share with one external researcher for feedback
- [ ] Collect "what would make this publishable?"

### Friday — Ship
- [ ] Final README update
- [ ] Push to GitHub
- [ ] Share on Slack / Twitter
