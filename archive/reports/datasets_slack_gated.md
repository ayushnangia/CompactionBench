Gated datasets that simulate real Codex/Claude Code usage.

**LongMemEval-V2 (long-term chat memory)**
https://github.com/xiaowu0162/LongMemEval-V2
→ Tests whether an agent remembers user facts across sessions. Simulates a personal assistant that needs to recall your project, preferences, and decisions from days ago. Runs 100+ turns. Direct compaction stress test.

**MIMIC-IV (clinical notes)**
https://huggingface.co/datasets/mimic-iv/mimic-iv
→ Real patient records spanning years. Simulates a medical AI reviewing patient history. Compaction drops a medication change → wrong treatment.

**MS MARCO (1M+ Bing queries)**
https://huggingface.co/datasets/microsoft/ms_marco
→ Real search queries with answers. Simulates a research agent retrieving from a large knowledge base. Many documents in context. Compaction drops the one with the answer.

**DialogSum (13k real dialogues)**
https://huggingface.co/datasets/knkarthick/dialogsum
→ Real conversations with summaries. Simulates a meeting agent. Transcript gets compacted. Action item #4 disappears.

**LegalBench**
https://huggingface.co/datasets/nguha/legalbench
→ Legal reasoning tasks. Simulates a lawyer agent reviewing contracts. Compaction drops a liability clause → missed risk.

**Cuad (contract review)**
https://huggingface.co/datasets/cuad/cuad
→ 500+ commercial contracts with labeled clauses. Simulates extracting specific terms from long legal documents.

**QMSum (meeting summarization)**
https://huggingface.co/datasets/qmsum/qmsum
→ Real meeting transcripts. Simulates an agent answering "what did we decide?" from a compacted transcript summary.
