# Latest continual learning papers for language models (2025-2026)

This note is about recent work, not the older continual learning canon. The question here is simpler: if someone asks what people are trying right now for continual learning in language models, which papers are actually worth reading first?

I checked the links and code status on March 11, 2026 using arXiv pages, ACL Anthology pages, paper PDFs, and public project pages or GitHub repos where they existed.

## What seems to be happening

The field is pulling in a few directions at once.

One cluster is trying to make sequential fine-tuning less destructive without adding much machinery. That is where the self-distillation and self-augmentation papers fit. Another cluster is still using replay, but in a more deliberate way: replay based on forgetting curves, replay based on which parts of instructions carry the real task signal, and so on.

At the same time, LoRA has turned into more than an efficiency trick. Several of the recent papers treat it almost like a controlled memory layer or a constrained subspace for storing updates. There is also a separate line of work on model merging, which is interesting because it sidesteps the "one model keeps getting overwritten" picture. And then there is the memory side: RAG-like systems, structured external memory, and Engram-style lookup modules. Those papers are not always framed as continual learning papers, but they are clearly part of the same conversation.

## How I am labeling code status

`Repo found` means I found a public repo or project page with code.

`Claimed release` means the paper says code or data were released, but I could not recover a stable public repo URL in a quick public search.

`Not found` means I did not find a public code repo in a quick public search on March 11, 2026.

## Annotated reading list

### 1. [Continual Learning for Generative AI: From LLMs to MLLMs and Beyond](https://arxiv.org/abs/2506.13045)

`2025 arXiv survey`

If you only read one overview first, read this one. It covers continual learning across LLMs, MLLMs, diffusion models, and related generative settings, and it does a good job separating replay-based, regularization-based, and architecture-based approaches. I would not treat it as a substitute for the papers below, but it is the fastest way to get the map of the space straight in your head.

Code status: `Repo found` for the companion reading list, [Awesome-Continual-Learning-in-Generative-Models](https://github.com/Ghy0501/Awesome-Continual-Learning-in-Generative-Models). That repo is a literature collection, not an implementation release for a single method.

### 2. [Self-Distillation Enables Continual Learning](https://arxiv.org/abs/2601.19897)

`2026 arXiv`

This is one of the more interesting recent papers because it pushes against plain supervised fine-tuning. The method, SDFT, uses a demonstration-conditioned model as its own teacher and turns demonstration learning into something closer to on-policy distillation. The pitch is straightforward: keep more of the old behavior while still learning the new task. For a current paper, it feels unusually clean.

Code status: `Repo found`, [idanshen/Self-Distillation](https://github.com/idanshen/Self-Distillation). Project page: [SDFT](https://self-distillation.github.io/SDFT.html).

### 3. [Multi-Stage LLM Fine-Tuning with a Continual Learning Setting](https://aclanthology.org/2025.findings-naacl.303/)

`Findings of NAACL 2025`

This paper is about the very practical case where domain knowledge keeps changing and the model gets updated in stages. The authors combine a preference-based bias for conflict detection with self-distillation-based data augmentation, then evaluate the model over seven fine-tuning stages. What makes it useful is not that it solves everything, but that it looks much more like real sequential domain adaptation than many toy continual learning setups do.

Code status: `Claimed release`. The paper says the code and dataset were released as `Multi-Stage-Learning`, but I did not recover a stable public repo URL from the paper page or a quick public search.

### 4. [Talking to Yourself: Defying Forgetting in Large Language Models](https://arxiv.org/abs/2602.20162)

`2026 arXiv`

The idea here is pleasantly simple. Before fine-tuning, the model generates self-dialogues, and those self-authored examples are mixed back into training. No special optimizer, no separate memory bank, no complicated infrastructure. The paper argues that this self-augmentation reduces forgetting while keeping in-domain gains. Even if the final story ends up being more nuanced than that, it is exactly the kind of lightweight idea that people will test quickly.

Code status: `Not found`.

### 5. [FOREVER: Forgetting Curve-Inspired Memory Replay for Language Model Continual Learning](https://arxiv.org/abs/2601.03938)

`2026 arXiv`

Replay is not new. What is new here is the attempt to stop replay from being tied to arbitrary training-step schedules. FOREVER defines "model time" using the magnitude of optimizer updates and then schedules replay with a forgetting-curve intuition. That is a better framing than "replay every N steps" because N steps do not mean the same thing across runs or tasks.

Code status: `Not found`.

### 6. [Don't Half-listen: Capturing Key-part Information in Continual Instruction Tuning](https://aclanthology.org/2025.acl-long.1153/)

`ACL 2025`

This paper goes after a real weakness in continual instruction tuning: models often latch onto the surface form of instructions and lose the task-critical content. The proposed KPIG method tries to identify the parts of the instruction that actually matter and uses that signal to improve replay and the training objective. If your benchmark cares about instruction-following quality or held-out generalization, this paper is worth keeping close.

Code status: `Not found`.

### 7. [Spurious Forgetting in Continual Learning of Language Models](https://arxiv.org/abs/2501.13453)

`2025 arXiv`

I would definitely keep this one in the mix because it changes the way the rest of the literature reads. The paper argues that some of what looks like forgetting is really a loss of task alignment rather than total knowledge erasure. That distinction matters. If the diagnosis is wrong, the fix will be wrong too. The freezing result is not the whole story, but the paper is valuable because it sharpens the question.

Code status: `Repo found`, [zzz47zzz/spurious-forgetting](https://github.com/zzz47zzz/spurious-forgetting).

### 8. [What Does Loss Optimization Actually Teach, If Anything? Knowledge Dynamics in Continual Pre-training of LLMs](https://arxiv.org/abs/2601.03858)

`2026 arXiv`

This one is especially useful if you are thinking about benchmarks or evaluation design. The paper studies continual pre-training as a knowledge acquisition process instead of assuming that lower loss means successful knowledge update. The core result is uncomfortable in a good way: optimization keeps moving, but factual learning is unstable, narrow, and often non-monotonic, while out-of-domain skills can start slipping early.

Code status: `Not found`.

### 9. [Understanding LoRA as Knowledge Memory: An Empirical Analysis](https://arxiv.org/abs/2603.01097)

`2026 arXiv`

This paper is trying to answer a question a lot of people have been circling without stating directly: can LoRA act like a modular memory rather than just a cheap adaptation layer? The authors study storage capacity, composition, scaling across multiple modules, and the boundary between LoRA, RAG, and in-context learning. Even if you do not buy every framing choice, the paper is useful because it treats LoRA as a place where knowledge might actually live.

Code status: `Not found`.

### 10. [Continual Gradient Low-Rank Projection Fine-Tuning for LLMs](https://aclanthology.org/2025.acl-long.721/)

`ACL 2025`

GORP is one of the stronger recent PEFT papers in this area. It tries to escape the usual low-rank trade-off by combining full and low-rank parameters inside a shared low-rank gradient subspace. The point is not just efficiency. The point is to keep enough expressiveness to learn the new task without trashing what was learned before.

Code status: `Repo found`, [Wcxwcxw/GORP](https://github.com/Wcxwcxw/GORP).

### 11. [Controlled Low-Rank Adaptation with Subspace Regularization for Continued Training on Large Language Models](https://aclanthology.org/2025.acl-long.940/)

`ACL 2025`

CLoRA is another good example of where the field has gone with LoRA-based continual learning. The method constrains the update through subspace regularization, especially the null-space direction of the update matrix, with the goal of reducing output drift and forgetting while keeping enough room to adapt. It feels less flashy than some of the newer ideas, but that is part of the appeal. It is a clean method paper.

Code status: `Repo found`, [sutakori/CLoRA](https://github.com/sutakori/CLoRA).

### 12. [AIMMerging: Adaptive Iterative Model Merging Using Training Trajectories for Language Model Continual Learning](https://aclanthology.org/2025.emnlp-main.678/)

`EMNLP 2025`

If you want one paper that represents the model-merging direction clearly, this is the one I would use. AimMerging watches the training trajectory, estimates learning and forgetting signals, and uses them to decide when merges should happen and how often. That is a lot more convincing than a fixed merge schedule. It also reflects a broader shift in the literature: people are starting to ask whether sequential learning should really mean sequential overwriting.

Code status: `Repo found`, [WoodScene/AimMerging](https://github.com/WoodScene/AimMerging).

### 13. [From RAG to Memory: Non-Parametric Continual Learning for Large Language Models](https://arxiv.org/abs/2502.14802)

`2025 arXiv`

This is the memory paper I would add if the list needs one external-memory anchor. The argument is that plain vector RAG does not really behave like long-term memory, especially once you care about more than literal factual retrieval. The proposed HippoRAG 2 system tries to recover some structure, associativity, and sense-making. For continual learning, the obvious attraction is that it offers a way to keep adding knowledge without repeatedly editing the core model.

Code status: `Repo found`, [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG).

### 14. [Conditional Memory via Scalable Lookup: A New Axis of Sparsity for Large Language Models](https://arxiv.org/abs/2601.07372)

`2026 arXiv`

This is the Engram paper. It is not a standard continual learning benchmark paper, but it belongs in the conversation because it tackles the same underlying problem from a different angle. The claim is that transformers are wasting computation simulating knowledge lookup, and that a direct conditional memory module can take that role more seriously. If you care about persistent knowledge without constant weight rewriting, this paper is hard to ignore.

Code status: `Repo found`, [deepseek-ai/Engram](https://github.com/deepseek-ai/Engram).

## Where I would start

If I had to hand an advisor a short stack instead of the full list, I would start with these:

1. [Self-Distillation Enables Continual Learning](https://arxiv.org/abs/2601.19897)
2. [Talking to Yourself: Defying Forgetting in Large Language Models](https://arxiv.org/abs/2602.20162)
3. [FOREVER](https://arxiv.org/abs/2601.03938)
4. [What Does Loss Optimization Actually Teach, If Anything?](https://arxiv.org/abs/2601.03858)
5. [Continual Gradient Low-Rank Projection Fine-Tuning for LLMs](https://aclanthology.org/2025.acl-long.721/)
6. [AIMMerging](https://aclanthology.org/2025.emnlp-main.678/)
7. [From RAG to Memory](https://arxiv.org/abs/2502.14802)
8. [Conditional Memory via Scalable Lookup](https://arxiv.org/abs/2601.07372)

That set gives a pretty honest picture of what is happening right now: distillation, self-generated supervision, replay scheduling, PEFT-based continual tuning, model merging, and the move from plain RAG toward more explicit memory systems.

## Code snapshot

| Paper | Status | Link or note |
|---|---|---|
| Continual Learning for Generative AI | Repo found | [Awesome-Continual-Learning-in-Generative-Models](https://github.com/Ghy0501/Awesome-Continual-Learning-in-Generative-Models) |
| Self-Distillation Enables Continual Learning | Repo found | [idanshen/Self-Distillation](https://github.com/idanshen/Self-Distillation) |
| Multi-Stage LLM Fine-Tuning with a Continual Learning Setting | Claimed release | Paper says code and dataset were released as `Multi-Stage-Learning`, but I did not recover a stable public repo URL |
| Talking to Yourself | Not found | No public repo found in a quick public search |
| FOREVER | Not found | No public repo found in a quick public search |
| Don't Half-listen | Not found | No public repo found in a quick public search |
| Spurious Forgetting | Repo found | [zzz47zzz/spurious-forgetting](https://github.com/zzz47zzz/spurious-forgetting) |
| Knowledge Dynamics in Continual Pre-training | Not found | No public repo found in a quick public search |
| Understanding LoRA as Knowledge Memory | Not found | No public repo found in a quick public search |
| GORP | Repo found | [Wcxwcxw/GORP](https://github.com/Wcxwcxw/GORP) |
| CLoRA | Repo found | [sutakori/CLoRA](https://github.com/sutakori/CLoRA) |
| AIMMerging | Repo found | [WoodScene/AimMerging](https://github.com/WoodScene/AimMerging) |
| From RAG to Memory | Repo found | [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) |
| Conditional Memory via Scalable Lookup | Repo found | [deepseek-ai/Engram](https://github.com/deepseek-ai/Engram) |

## Final take

If I had to summarize the recent literature in one sentence, I would say this: the field is slowly moving away from the idea that continual learning is only about protecting a single parameter vector from forgetting. More of the interesting work now treats memory, replay, subspace control, and model composition as first-class design choices.

That is probably the most useful lens for reading these papers together.
