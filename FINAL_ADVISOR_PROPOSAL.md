# ContinualBENCH: A Unified Benchmark for Updating LLMs Over Time

## The Problem

The world changes every day but models are frozen at training time.

People fix this in three ways: continual pretraining (retrain on new data with some replay of old data), temporal RAG/memory/engram (don't update the model, just search fresh documents), or distillation/rl based methods (in recent times). All three are used in practice right now.

The problem: there is no good benchmark to compare them fairly.

Existing benchmarks each look at one slice of the problem:
- **FreshQA** tests whether a model knows recent facts, but it only measures retrieval/search capability. It does not test whether the model can retain old knowledge or reason across time.
- **PAT-Questions** tests present-anchored temporal QA, but focuses on in-context learning rather than evaluating actual model updates.
- **TimeBench** covers temporal reasoning broadly, but on static facts. It does not test what happens when you update a model with new data.
- **SealQA** tests retrieval robustness under noise, but does not measure forgetting or multi-hop reasoning over updated knowledge.
- **TiC-LM** built a time-ordered training corpus and measured perplexity over time. But perplexity does not tell you if the model can actually answer questions, reason across steps, or retain old knowledge.

None of them captures the full picture. We want to build a unified benchmark that presents a unified framework for continual learning, by building on top of these existing resources rather than starting from scratch.

## What We Measure

When you update a model with new information, three things can happen:

1. **Adaptation**: it learns the new stuff.
2. **Forgetting**: it loses old stuff that is still true.
3. **Temporal connectivity**: it loses the ability to use updated facts inside multi-step reasoning chains with older stable facts.

We want to make sure that ContinualBENCH measures all three dimensions effectively. 

## How We Use Existing Benchmarks

We take questions from FreshQA, PAT-Questions, TimeBench, and SealQA (all of these are being maintained and updated each month with new information, hence our benchmark can be dynamic) based on these we use the news-index/common-crawl for the approtiate date bucket (currenty in weeks) to train the model with the relevant fact that we map from these benchmarks.
Qur evaluation framework (adaptation, forgetting, temporal connectivity). We repurpose and extend their questions to test all three things together.

Where existing benchmarks have gaps (especially multi-hop temporal reasoning over updated facts), we generate new questions using the Infini-News corpus with strict chronological splits.

## Research Questions and Hypotheses

**RQ1: Does updating a model for temporal adaptation necessarily degrade retention and temporal connectivity?**

*Hypothesis*: Parametric update methods (full continual pretraining, LoRA with large data volumes) will show strong adaptation to new facts but suffer from catastrophic forgetting. The more new data you push into the model, the worse it gets at recalling older knowledge that is still true. Retrieval-based and in-context methods will preserve old knowledge but do not actually learn new facts into the model's parameters. A hybrid approach (parametric update + retrieval) can achieve the best balance: maximum new fact acquisition with highest retention of old knowledge.

**RQ2: Do retrieval-based methods and parametric methods fail in fundamentally different ways?**

*Hypothesis*: Parametric updates (continual pretraining, LoRA) will fail primarily through forgetting. The model overwrites old knowledge with new knowledge. Retrieval-based methods (temporal RAG) will fail differently. They will retrieve outdated documents or fail to compose retrieved facts across multiple reasoning steps. 
