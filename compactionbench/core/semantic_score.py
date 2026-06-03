"""Semantic scoring for code/text generation tasks using ROUGE and BLEU.

Unlike exact/substring scoring, these give partial credit when the model
produces a reasonable answer that differs in formatting or specific details.

Used for tasks where the gold is a full code block (patch, SQL, prediction)
and the model output is a semantically similar but textually different answer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SemanticScore:
    rouge1_f: float   # unigram overlap F1
    rougeL_f: float   # longest common subsequence F1
    bleu: float       # BLEU-4 score
    keyword_recall: float  # fraction of gold keywords in answer
    combined: float   # weighted average, 0-1


def score_semantic(gold: str, answer: str) -> SemanticScore:
    """Score answer against gold using ROUGE, BLEU, and keyword overlap."""
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        raise ImportError("rouge-score required: uv add rouge-score")

    # ROUGE
    scorer = rouge_scorer.RougeScorer(["rouge1", "rougeL"], use_stemmer=False)
    rouge = scorer.score(gold, answer)

    # BLEU (simple implementation without nltk dependency)
    bleu = _compute_bleu(gold, answer)
    kw = _keyword_recall(gold, answer)

    # Combined: weighted average
    combined = (
        0.25 * rouge["rouge1"].fmeasure +
        0.25 * rouge["rougeL"].fmeasure +
        0.25 * bleu +
        0.25 * kw
    )

    return SemanticScore(
        rouge1_f=rouge["rouge1"].fmeasure,
        rougeL_f=rouge["rougeL"].fmeasure,
        bleu=bleu,
        keyword_recall=kw,
        combined=combined,
    )


def _compute_bleu(reference: str, candidate: str, n: int = 4) -> float:
    """Compute BLEU score without external dependencies."""
    import math, re

    def ngrams(text: str, n: int) -> list[tuple[str, ...]]:
        tokens = re.findall(r'\w+', text.lower())
        return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

    candidate_tokens = re.findall(r'\w+', candidate.lower())
    if len(candidate_tokens) < n:
        return 0.0

    precisions = []
    for i in range(1, n + 1):
        ref_ngrams = set(ngrams(reference, i))
        cand_ngrams = ngrams(candidate, i)
        if not cand_ngrams:
            precisions.append(0.0)
            continue
        matches = sum(1 for ng in cand_ngrams if ng in ref_ngrams)
        precisions.append(matches / len(cand_ngrams))

    if all(p == 0 for p in precisions):
        return 0.0

    # Brevity penalty
    ref_len = len(re.findall(r'\w+', reference.lower()))
    cand_len = len(candidate_tokens)
    bp = min(1.0, math.exp(1 - ref_len / max(cand_len, 1)))

    log_avg = sum(math.log(max(p, 1e-10)) for p in precisions) / n
    return bp * math.exp(log_avg)


def _keyword_recall(gold: str, answer: str) -> float:
    """Fraction of gold keywords that appear in the answer."""
    import re

    # Extract meaningful tokens from gold
    gold_tokens = set(re.findall(r'[a-z_]{3,}', gold.lower()))
    ans_tokens = set(re.findall(r'[a-z_]{3,}', answer.lower()))

    # Filter stopwords
    stopwords = {'the', 'and', 'for', 'from', 'this', 'that', 'with', 'was',
                 'are', 'not', 'but', 'has', 'had', 'have', 'can', 'all', 'will'}
    gold_tokens -= stopwords

    if not gold_tokens:
        return 0.0

    return len(gold_tokens & ans_tokens) / len(gold_tokens)
