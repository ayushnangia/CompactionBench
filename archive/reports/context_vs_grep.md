# Context Injection vs Grep — Step by step

Same question: "Where is Mary?" Same text: 130,000 words. Same model: gpt-5.4-mini.

## Context Injection (cbench)

Step 1: The 130k-word text is split into 18 chunks of ~8k words each.

Step 2: Chunk 1 is sent to Codex as a user message. "Context chunk 1/18. Store this for later."

Step 3: Codex says "OK."

Step 4: Chunk 2 sent. "OK."

...

Step 18: Chunk 18 sent. "OK."

Step 19: But Codex's context window is full. Its auto-compaction has already summarized chunks 1 through 10 into a vague paragraph. The sentence "Mary journeyed to the bathroom" was in chunk 10. It is now gone.

Step 20: "Now answer: Where is Mary?"

Step 21: Codex searches its compacted memory. Finds: "Mary was discussed in several locations." Answers: "Not mentioned in the provided context."

Result: Wrong.

---

## Grep

Step 1: The 130k-word text is saved as a file: full_context.txt.

Step 2: Codex is asked: "Use grep on full_context.txt. Where is Mary?"

Step 3: Codex runs: `grep -i mary full_context.txt`

Step 4: The result is a few lines containing Mary. One of them: "Mary journeyed to the bathroom."

Step 5: Codex answers: "bathroom."

Result: Correct.

---

## Why the difference

In context injection, the model must hold 130k words in memory. The system silently compacts the beginning. The answer gets lost.

In grep, the model runs one command. Returns only the matching lines. The answer is never compacted. It is found fresh each time.

The model is not smarter with grep. It is searching a smaller, more relevant set of text — the grep output instead of the full book.
