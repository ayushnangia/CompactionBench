"""Offline context-compression policies for CompactionBench task rows.

These policies intentionally run before any live harness call. They turn a normal
TaskRow into another TaskRow whose context is a compressed artifact, so the rest
of the benchmark path can stay unchanged:

    raw JSONL -> compressed JSONL -> existing Codex/Claude runner -> scorer

The first policies are deterministic baselines. They are not meant to be a final
memory system; they give us something simple to compare against native auto
compaction before adding DSPy/GEPA-style prompt optimization.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.chunking import estimate_tokens
from ..core.schema import TaskRow, load_task_rows, write_task_rows

CompressionPolicyName = Literal[
    "none",
    "static-notebook",
    "static-heuristic",
    "entropy-notebook",
    "entropy",
]

_POLICY_ALIASES: dict[str, str] = {
    "none": "none",
    "static": "static-notebook",
    "static-notebook": "static-notebook",
    "static-heuristic": "static-notebook",
    "entropy": "entropy-notebook",
    "entropy-notebook": "entropy-notebook",
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "she",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "to",
    "was",
    "were",
    "with",
    "you",
    "what",
    "which",
    "who",
    "where",
    "when",
    "why",
    "how",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*|\d+(?:\.\d+)?")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_VALUE_RE = re.compile(
    r"(\b\d+(?:\.\d+)?\b|\b[A-Z]{2,}[-_A-Z0-9]*\d[-_A-Z0-9]*\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+|/[A-Za-z0-9._/:-]+|\b[A-Za-z]+[-_][A-Za-z0-9_-]+\b)"
)
_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b")
_UPDATE_RE = re.compile(
    r"\b(changed?|updated?|replaced?|renamed?|correct(?:ed|ion)?|latest|current|now|instead|no longer|should use|must use|final|confirmed|overrides?)\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"\b(count|total|sum|number of|how many|cumulative|cummulative|percentage|percent)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CompressionStats:
    policy: str
    budget_tokens: int
    query_aware: bool
    original_tokens_est: int
    compressed_tokens_est: int
    selected_units: int
    total_units: int

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens_est <= 0:
            return 1.0
        return self.compressed_tokens_est / self.original_tokens_est


@dataclass(frozen=True)
class CompressionResult:
    context: str
    stats: CompressionStats


@dataclass(frozen=True)
class Candidate:
    index: int
    text: str
    tokens: tuple[str, ...]
    tokens_est: int
    base_score: float


def normalize_policy_name(policy: str) -> str:
    key = policy.strip().lower()
    if key not in _POLICY_ALIASES:
        allowed = ", ".join(sorted(_POLICY_ALIASES))
        raise ValueError(f"Unknown compression policy {policy!r}; expected one of: {allowed}")
    return _POLICY_ALIASES[key]


def compress_task_row(
    row: TaskRow,
    *,
    policy: str,
    budget_tokens: int,
    query_aware: bool = False,
) -> TaskRow:
    """Return a validated compressed copy of ``row``.

    The gold answer and scorer are unchanged. The task id is suffixed so raw and
    compressed variants can coexist in the same batch without collisions.
    """

    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be > 0")
    normalized = normalize_policy_name(policy)
    result = compress_context(
        row.context,
        question=row.question if query_aware else None,
        policy=normalized,
        budget_tokens=budget_tokens,
        query_aware=query_aware,
    )
    suffix = f"{_sanitize_task_part(normalized)}-b{budget_tokens}"
    if query_aware:
        suffix += "-qaware"
    metadata = dict(row.metadata)
    metadata["compression"] = {
        "policy": result.stats.policy,
        "budget_tokens": result.stats.budget_tokens,
        "query_aware": result.stats.query_aware,
        "original_tokens_est": result.stats.original_tokens_est,
        "compressed_tokens_est": result.stats.compressed_tokens_est,
        "compression_ratio": result.stats.compression_ratio,
        "selected_units": result.stats.selected_units,
        "total_units": result.stats.total_units,
        "original_task_id": row.task_id,
    }
    return row.model_copy(
        update={
            "task_id": f"{row.task_id}--{suffix}",
            "context": result.context,
            "metadata": metadata,
        }
    )


def compress_context(
    context: str,
    *,
    question: str | None,
    policy: str,
    budget_tokens: int,
    query_aware: bool = False,
) -> CompressionResult:
    normalized = normalize_policy_name(policy)
    original_tokens = estimate_tokens(context)
    if normalized == "none":
        out = context
        stats = CompressionStats(
            policy=normalized,
            budget_tokens=budget_tokens,
            query_aware=query_aware,
            original_tokens_est=original_tokens,
            compressed_tokens_est=estimate_tokens(out),
            selected_units=0,
            total_units=len(_split_candidate_units(context)),
        )
        return CompressionResult(context=out, stats=stats)

    candidates = _build_candidates(context, question=question if query_aware else None)
    if normalized == "static-notebook":
        out, selected_count = _render_static_notebook(candidates, budget_tokens=budget_tokens, question=question if query_aware else None)
    elif normalized == "entropy-notebook":
        out, selected_count = _render_entropy_context(candidates, budget_tokens=budget_tokens, question=question if query_aware else None)
    else:  # pragma: no cover - normalize_policy_name should prevent this
        raise ValueError(f"Unhandled compression policy: {normalized}")

    stats = CompressionStats(
        policy=normalized,
        budget_tokens=budget_tokens,
        query_aware=query_aware,
        original_tokens_est=original_tokens,
        compressed_tokens_est=estimate_tokens(out),
        selected_units=selected_count,
        total_units=len(candidates),
    )
    return CompressionResult(context=out, stats=stats)


def compress_task_file(
    input_path: Path,
    output_path: Path,
    *,
    policy: str,
    budget_tokens: int,
    query_aware: bool = False,
    task_filter: set[str] | None = None,
) -> list[TaskRow]:
    rows = load_task_rows(input_path)
    if task_filter is not None:
        rows = [row for row in rows if row.task_id in task_filter]
    compressed = [
        compress_task_row(row, policy=policy, budget_tokens=budget_tokens, query_aware=query_aware)
        for row in rows
    ]
    write_task_rows(compressed, output_path)
    return compressed


def _build_candidates(context: str, *, question: str | None) -> list[Candidate]:
    units = _split_candidate_units(context)
    tokenized = [_tokenize(unit) for unit in units]
    freq = Counter(token for toks in tokenized for token in set(toks) if token not in _STOPWORDS)
    query_tokens = set(_tokenize(question or "")) - _STOPWORDS

    candidates: list[Candidate] = []
    for idx, (unit, toks) in enumerate(zip(units, tokenized), start=1):
        non_stop = [tok for tok in toks if tok not in _STOPWORDS]
        has_value = bool(_VALUE_RE.search(unit))
        entity_matches = [
            match for match in _ENTITY_RE.findall(unit)
            if match.split()[0].lower() not in _STOPWORDS
        ]
        has_entity = bool(entity_matches)
        # Avoid degenerate high-density snippets like "change." winning just
        # because they are short and rare. Keep very short units only if they
        # carry a concrete value/entity signal.
        if len(non_stop) < 3 and not (has_value or has_entity):
            continue
        rarity = sum(1.0 / math.sqrt(freq.get(tok, 1)) for tok in set(non_stop))
        rarity = rarity / max(1.0, math.sqrt(len(non_stop)))
        query_overlap = len(query_tokens.intersection(non_stop))
        value_bonus = 1.5 if has_value else 0.0
        entity_bonus = min(2.0, 0.4 * len(entity_matches))
        update_bonus = 2.5 if _UPDATE_RE.search(unit) and len(non_stop) >= 3 else 0.0
        count_bonus = 1.0 if _COUNT_RE.search(unit) else 0.0
        base_score = rarity + value_bonus + entity_bonus + update_bonus + count_bonus + 6.0 * query_overlap
        candidates.append(
            Candidate(
                index=idx,
                text=unit.strip(),
                tokens=tuple(non_stop),
                tokens_est=estimate_tokens(unit),
                base_score=base_score,
            )
        )
    return candidates


def _split_candidate_units(context: str) -> list[str]:
    # First split on paragraph/sentence boundaries. If a unit remains too large,
    # split it into conservative character windows so scoring remains tractable.
    raw_units = [unit.strip() for unit in _SENTENCE_BOUNDARY_RE.split(context) if unit.strip()]
    units: list[str] = []
    max_chars = 1200
    for unit in raw_units:
        if len(unit) <= max_chars:
            units.append(unit)
            continue
        for start in range(0, len(unit), max_chars):
            piece = unit[start : start + max_chars].strip()
            if piece:
                units.append(piece)
    return units or [context.strip()]


def _render_entropy_context(
    candidates: list[Candidate], *, budget_tokens: int, question: str | None) -> tuple[str, int]:
    selected = _select_candidates(candidates, budget_tokens=max(1, budget_tokens - 120), redundancy_penalty=0.45)
    selected = sorted(selected, key=lambda c: c.index)
    header = [
        "COMPRESSED CONTEXT",
        "Policy: entropy-notebook (extractive).",
        "The following snippets were selected for rarity, values/entities, updates, novelty, and optional query relevance.",
    ]
    if question:
        header.append(f"Compression question hint: {question}")
    body = [f"[source-unit {c.index}] {c.text}" for c in selected]
    if not body and candidates:
        best = max(candidates, key=lambda c: c.base_score)
        body = [f"[source-unit {best.index}] {best.text[: budget_tokens * 4]}"]
        selected = [best]
    return "\n".join(header + ["", *body]).strip(), len(selected)


def _render_static_notebook(candidates: list[Candidate], *, budget_tokens: int, question: str | None) -> tuple[str, int]:
    selected = _select_candidates(candidates, budget_tokens=max(1, budget_tokens - 180), redundancy_penalty=0.25)
    selected = sorted(selected, key=lambda c: (-_static_priority(c.text), c.index))

    sections: dict[str, list[str]] = {
        "Latest updates / corrections": [],
        "Numbers, dates, paths, and IDs": [],
        "Entity bindings": [],
        "Other high-signal facts": [],
    }
    for cand in selected:
        text = _trim_for_bullet(cand.text)
        if _UPDATE_RE.search(cand.text):
            sections["Latest updates / corrections"].append(text)
        elif _VALUE_RE.search(cand.text):
            sections["Numbers, dates, paths, and IDs"].append(text)
        elif _ENTITY_RE.search(cand.text):
            sections["Entity bindings"].append(text)
        else:
            sections["Other high-signal facts"].append(text)

    lines = [
        "COMPRESSED CONTEXT NOTE",
        "Policy: static-notebook (deterministic heuristic).",
        "Use this note as the compressed source context for answering the final question.",
    ]
    if question:
        lines.append(f"Compression question hint: {question}")
    lines.append("")

    selected_count = 0
    for title, facts in sections.items():
        if not facts:
            continue
        tentative = lines + [f"## {title}"]
        if estimate_tokens("\n".join(tentative)) > budget_tokens:
            break
        lines.append(f"## {title}")
        for fact in facts:
            tentative = lines + [f"- {fact}"]
            if estimate_tokens("\n".join(tentative)) > budget_tokens:
                break
            lines.append(f"- {fact}")
            selected_count += 1
        lines.append("")

    if selected_count == 0 and candidates:
        best = max(candidates, key=lambda c: c.base_score)
        lines.append("## Highest-signal fact")
        lines.append(f"- {_trim_for_bullet(best.text, max_chars=budget_tokens * 4)}")
        selected_count = 1
    return "\n".join(lines).strip(), selected_count


def _select_candidates(candidates: list[Candidate], *, budget_tokens: int, redundancy_penalty: float) -> list[Candidate]:
    if not candidates or budget_tokens <= 0:
        return []

    selected: list[Candidate] = []
    selected_tokens: set[str] = set()
    used_indices: set[int] = set()
    spent = 0

    while True:
        best: Candidate | None = None
        best_score = -1.0
        for cand in candidates:
            if cand.index in used_indices:
                continue
            if cand.tokens_est + spent > budget_tokens and selected:
                continue
            tok_set = set(cand.tokens)
            overlap = _jaccard(tok_set, selected_tokens) if selected_tokens else 0.0
            density = cand.base_score / max(1.0, math.sqrt(cand.tokens_est))
            adjusted = density * (1.0 - redundancy_penalty * overlap)
            if adjusted > best_score:
                best = cand
                best_score = adjusted
        if best is None:
            break
        selected.append(best)
        used_indices.add(best.index)
        selected_tokens.update(best.tokens)
        spent += best.tokens_est
        if spent >= budget_tokens:
            break
        if len(used_indices) == len(candidates):
            break
    return selected


def _static_priority(text: str) -> int:
    if _UPDATE_RE.search(text):
        return 4
    if _VALUE_RE.search(text):
        return 3
    if _ENTITY_RE.search(text):
        return 2
    if _COUNT_RE.search(text):
        return 1
    return 0


def _trim_for_bullet(text: str, max_chars: int = 320) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in _TOKEN_RE.findall(text)]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sanitize_task_part(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-")
