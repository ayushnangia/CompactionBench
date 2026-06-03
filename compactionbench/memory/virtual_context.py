"""Transparent/system-managed virtual context memory.

This module is the OS-like counterpart to ``paged_context``.

``paged_context`` is model-visible: the model sees ``pager.py`` and chooses
which pages to search/load.  ``virtual_context`` is system-managed: the harness
acts like the memory kernel, retrieves a working set from the original paged
source, and gives the model an evidence packet.  The model does not see or call
paging tools.

This is still a research prototype, not a full virtual-memory subsystem.  The
important architectural property is that page selection happens outside the
model and is recorded in metadata.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..core.chunking import estimate_tokens
from .paged_context import PagedMemory, PageRecord, benchmark_hint


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    title: str
    text: str
    score: float
    page_ids: tuple[int, ...] = ()
    reason: str = ""

    @property
    def tokens_est(self) -> int:
        return estimate_tokens(self.text)

    def metadata(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "score": self.score,
            "page_ids": list(self.page_ids),
            "tokens_est": self.tokens_est,
            "preview": _preview(self.text, 240),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VirtualContextPacket:
    strategy: str
    budget_tokens: int
    source_tokens_est: int
    page_count: int
    evidence_text: str
    evidence_tokens_est: int
    items: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    selected_page_ids: tuple[int, ...] = field(default_factory=tuple)

    def metadata(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "budget_tokens": self.budget_tokens,
            "source_tokens_est": self.source_tokens_est,
            "page_count": self.page_count,
            "evidence_tokens_est": self.evidence_tokens_est,
            "selected_page_ids": list(self.selected_page_ids),
            "selected_page_count": len(set(self.selected_page_ids)),
            "item_count": len(self.items),
            "items": [item.metadata() for item in self.items],
        }


@dataclass(frozen=True)
class VirtualContextConfig:
    budget_tokens: int = 24000
    max_items: int = 42
    max_item_tokens: int = 1800
    neighbor_radius: int = 1


@dataclass(frozen=True)
class RlmContextConfig:
    """Pseudo-relevance-feedback retrieval config.

    This is a classical relevance-language-model / RM3-style variant: retrieve
    initially from the question, estimate expansion terms from top pages, then
    retrieve the resident evidence set with the expanded query. It is system-
    managed and transparent to the model.
    """

    budget_tokens: int = 24000
    initial_top_k: int = 12
    expansion_terms: int = 24
    final_top_k: int = 32
    original_query_weight: float = 0.65
    max_item_tokens: int = 1400


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "did",
    "do",
    "does",
    "end",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "not",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

BABI_NAMES = ("Mary", "John", "Sandra", "Daniel", "Fred", "Bill", "Jeff", "Julie")
BABI_LOCS = ("bathroom", "bedroom", "garden", "hallway", "kitchen", "office", "school", "cinema", "park")
BABI_OBJECTS = ("football", "apple", "milk")
BABI_DIRECTIONS = ("north", "south", "east", "west")


def build_virtual_context_packet(
    memory: PagedMemory,
    question: str,
    *,
    source_benchmark: str,
    source_task: str,
    config: VirtualContextConfig | None = None,
) -> VirtualContextPacket:
    """Build the model's resident working set from paged source memory."""

    cfg = config or VirtualContextConfig()
    items: list[EvidenceItem] = []
    strategy_parts = ["transparent_virtual_context", source_benchmark]

    if source_benchmark == "babilong":
        strategy_parts.append("babi_event_trace")
        items.extend(_babilong_items(memory, question))
        # If the BABI event trace exists, it is usually cleaner than raw carrier
        # prose pages that reuse names like Mary/John for unrelated novel plots.
        if not items:
            items.extend(_generic_page_items(memory, question, source_benchmark=source_benchmark, source_task=source_task, config=cfg))
    elif source_benchmark == "oolong":
        strategy_parts.append("oolong_keyword_event_windows")
        items.extend(_oolong_items(memory, question, source_task))
        items.extend(_generic_page_items(memory, question, source_benchmark=source_benchmark, source_task=source_task, config=cfg))
    else:
        strategy_parts.append("generic_page_scoring")
        items.extend(_generic_page_items(memory, question, source_benchmark=source_benchmark, source_task=source_task, config=cfg))
    selected = _select_items(items, cfg)
    evidence_text = _render_packet_text(
        selected,
        question=question,
        source_benchmark=source_benchmark,
        source_task=source_task,
        memory=memory,
    )
    selected_pages: list[int] = []
    for item in selected:
        selected_pages.extend(item.page_ids)
    return VirtualContextPacket(
        strategy="+".join(strategy_parts),
        budget_tokens=cfg.budget_tokens,
        source_tokens_est=memory.total_tokens_est,
        page_count=memory.page_count,
        evidence_text=evidence_text,
        evidence_tokens_est=estimate_tokens(evidence_text),
        items=tuple(selected),
        selected_page_ids=tuple(sorted(set(selected_pages))),
    )


def build_rlm_context_packet(
    memory: PagedMemory,
    question: str,
    *,
    source_benchmark: str,
    source_task: str,
    config: RlmContextConfig | None = None,
) -> VirtualContextPacket:
    """Build a transparent virtual-context packet with RLM/RM3 retrieval.

    Unlike the typed virtual context, this arm is intentionally generic: it uses
    pseudo-relevance feedback over source pages instead of benchmark-specific
    event extractors. It tests whether a research-standard IR retrieval model is
    enough as the memory kernel.
    """

    cfg = config or RlmContextConfig()
    page_stats = _page_term_stats(memory)
    original_terms = [tok for tok in _tokens(question) if tok not in STOPWORDS and len(tok) >= 2]
    # Preserve useful capitalized multiword entities by adding their component tokens.
    for term in _capitalized_terms(question):
        original_terms.extend(tok for tok in _tokens(term) if tok not in STOPWORDS)
    if not original_terms:
        original_terms = [tok for tok in _tokens(question) if tok not in STOPWORDS]
    original_terms = _add_light_morph_variants(original_terms)

    original_weights = Counter(original_terms)
    initial = _rank_pages_with_weights(page_stats, original_weights)
    expansion_weights = _estimate_rlm_expansion(initial[: cfg.initial_top_k], page_stats, cfg)
    final_weights = _rm3_mix(original_weights, expansion_weights, original_query_weight=cfg.original_query_weight)
    final_ranked = _rank_pages_with_weights(page_stats, final_weights)

    top_expansion = [term for term, _ in expansion_weights.most_common(cfg.expansion_terms)]
    final_terms = set(term for term, _ in final_weights.most_common(max(12, cfg.expansion_terms)))
    items: list[EvidenceItem] = [
        EvidenceItem(
            kind="rlm_query_model",
            title="RLM/RM3 expanded query model",
            text=(
                "Original query terms: " + ", ".join(original_terms[:40]) + "\n"
                "Expansion terms from top pages: " + ", ".join(top_expansion) + "\n"
                "This expansion was estimated without the gold answer."
            ),
            score=100.0,
            page_ids=(),
            reason="Pseudo-relevance feedback query model.",
        )
    ]
    for rank, (score, page, text, _counter) in enumerate(final_ranked[: cfg.final_top_k], start=1):
        snippet = _best_page_snippet(text, final_terms, max_chars=cfg.max_item_tokens * 4)
        items.append(
            EvidenceItem(
                kind="rlm_page",
                title=f"RLM-ranked page {page.page_id} (rank {rank})",
                text=f"[page {page.page_id} lines {page.line_start}-{page.line_end} | RLM score {score:.3f}]\n{snippet}",
                score=score,
                page_ids=(page.page_id,),
                reason="Ranked by RM3-style expanded query over hidden page index.",
            )
        )

    selected = _select_items(
        items,
        VirtualContextConfig(
            budget_tokens=cfg.budget_tokens,
            max_items=cfg.final_top_k + 1,
            max_item_tokens=cfg.max_item_tokens,
            neighbor_radius=0,
        ),
    )
    evidence_text = _render_packet_text(
        selected,
        question=question,
        source_benchmark=source_benchmark,
        source_task=source_task,
        memory=memory,
    )
    selected_pages: list[int] = []
    for item in selected:
        selected_pages.extend(item.page_ids)
    return VirtualContextPacket(
        strategy="transparent_virtual_context+rlm_rm3",
        budget_tokens=cfg.budget_tokens,
        source_tokens_est=memory.total_tokens_est,
        page_count=memory.page_count,
        evidence_text=evidence_text,
        evidence_tokens_est=estimate_tokens(evidence_text),
        items=tuple(selected),
        selected_page_ids=tuple(sorted(set(selected_pages))),
    )


def build_virtual_context_prompt(
    question: str,
    *,
    packet: VirtualContextPacket,
    source_benchmark: str,
    source_task: str,
) -> str:
    """Prompt for the transparent virtual-context arm.

    The prompt deliberately omits page-tool instructions.  The model receives a
    resident evidence packet and answers from it.
    """

    return (
        "You are answering from TRANSPARENT VIRTUAL CONTEXT.\n"
        "A system memory kernel has already retrieved the relevant source pages and evidence.\n"
        "You do not need to search files, run shell commands, load pages, or use the web. Do not use tools.\n"
        "Answer only from the evidence packet below. If several pieces of evidence conflict, prefer the benchmark-specific guidance and the most directly relevant evidence.\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n"
        f"{benchmark_hint(source_benchmark, source_task)}\n"
        "<VIRTUAL_CONTEXT_EVIDENCE>\n"
        f"{packet.evidence_text}\n"
        "</VIRTUAL_CONTEXT_EVIDENCE>\n\n"
        f"Question:\n{question}\n"
    )


def _babilong_items(memory: PagedMemory, question: str) -> list[EvidenceItem]:
    q_terms = set(_tokens(question)) - STOPWORDS
    q_names = {name.lower() for name in BABI_NAMES if re.search(rf"\b{name}\b", question)}
    q_locs = {loc for loc in BABI_LOCS if loc in question.lower()}
    q_objs = {obj for obj in BABI_OBJECTS if obj in question.lower()}
    q_dirs = {direction for direction in BABI_DIRECTIONS if direction in question.lower()}

    facts: list[tuple[float, int, str, int]] = []
    for page in memory.pages:
        text = _read_page(memory, page)
        for sent in _sentence_units(text):
            fact_kind = _babi_fact_kind(sent)
            if not fact_kind:
                continue
            low = sent.lower()
            score = 15.0
            score += 8.0 * len(q_names & set(_tokens(low)))
            score += 7.0 * len(q_locs & set(_tokens(low)))
            score += 7.0 * len(q_objs & set(_tokens(low)))
            score += 5.0 * len(q_dirs & set(_tokens(low)))
            score += 2.0 * len(q_terms & set(_tokens(low)))
            # Concise injected facts are more valuable than prose-like carrier sentences.
            if len(sent) < 180:
                score += 5.0
            facts.append((score, page.page_id, sent.strip(), len(facts) + 1))

    if not facts:
        return []

    # Keep a chronological trace, but trim very low-signal facts if unusually large.
    facts_sorted = sorted(facts, key=lambda x: x[3])
    if len(facts_sorted) > 220:
        top_ids = {idx for _, _, _, idx in sorted(facts, key=lambda x: (-x[0], x[3]))[:220]}
        facts_sorted = [fact for fact in facts_sorted if fact[3] in top_ids]

    lines = ["BABILong extracted event trace (chronological, selected without gold answer):"]
    page_ids: list[int] = []
    for score, page_id, sent, idx in facts_sorted:
        page_ids.append(page_id)
        lines.append(f"[{idx:03d} | page {page_id} | score {score:.1f}] {sent}")
    max_score = max(score for score, *_ in facts_sorted)
    return [
        EvidenceItem(
            kind="structured_trace",
            title="BABILong concise event trace",
            text="\n".join(lines),
            score=max_score + 50.0,
            page_ids=tuple(sorted(set(page_ids))),
            reason="Extracted BABI-like movement/object/transfer/spatial facts and ignored unrelated carrier prose.",
        )
    ]


def _babi_fact_kind(sentence: str) -> str | None:
    names = "|".join(BABI_NAMES)
    locs = "|".join(BABI_LOCS)
    objs = "|".join(BABI_OBJECTS)
    dirs = "|".join(BABI_DIRECTIONS)
    s = sentence.strip()
    if re.search(rf"\b({names})\s+(journeyed|travelled|traveled|moved|went)\s+to\s+the\s+({locs})\b", s, re.I):
        return "movement"
    if re.search(rf"\b({names})\s+(picked up|grabbed|got|took)\s+the\s+({objs})\b", s, re.I):
        return "pickup"
    if re.search(rf"\b({names})\s+(dropped|discarded|put down|left)\s+the\s+({objs})\b", s, re.I):
        return "drop"
    if re.search(rf"\b({names})\s+(gave|handed|passed)\s+the\s+({objs})\s+to\s+({names})\b", s, re.I):
        return "transfer"
    if re.search(rf"\b({locs})\b.*\b({dirs})\s+of\s+the\s+({locs})\b", s, re.I):
        return "spatial"
    return None


def _oolong_items(memory: PagedMemory, question: str, source_task: str) -> list[EvidenceItem]:
    terms = set(_tokens(question)) - STOPWORDS
    qlow = question.lower()
    domain_terms: set[str] = set()
    if "roll" in qlow or "nat" in qlow or "crit" in qlow or "natural" in qlow:
        domain_terms.update({"roll", "rolled", "rolls", "natural", "nat", "crit", "check", "attack", "save"})
    if "spell" in qlow or "cast" in qlow or "cantrip" in qlow or "level" in qlow:
        domain_terms.update({"spell", "spells", "cast", "casts", "casting", "cantrip", "level"})
    # Preserve named spells/types/characters from the question.
    domain_terms.update(tok for tok in _capitalized_terms(question) if len(tok) > 2)
    terms.update(tok.lower() for tok in domain_terms)

    hits: list[tuple[float, int, str, int]] = []
    for page in memory.pages:
        text = _read_page(memory, page)
        for idx, window in enumerate(_context_windows(text, terms=terms, max_windows=8), start=1):
            low = window.lower()
            score = 0.0
            for term in terms:
                score += min(5, low.count(term.lower()))
            if source_task and source_task.replace("_", " ").split()[0] in low:
                score += 3.0
            if "[start of episode]" in low or "[end of episode]" in low:
                score += 4.0
            if score > 0:
                hits.append((score, page.page_id, window.strip(), idx))

    if not hits:
        return []
    hits.sort(key=lambda item: (-item[0], item[1], item[3]))
    selected = hits[:80]
    selected.sort(key=lambda item: (item[1], item[3]))

    lines = ["OOLONG retrieved event windows (system-selected from question terms):"]
    page_ids: list[int] = []
    for score, page_id, window, _idx in selected:
        page_ids.append(page_id)
        lines.append(f"\n[page {page_id} | score {score:.1f}]\n{window}")
    return [
        EvidenceItem(
            kind="event_windows",
            title="OOLONG roll/spell/question-term windows",
            text="\n".join(lines),
            score=(selected[0][0] if selected else 0.0) + 25.0,
            page_ids=tuple(sorted(set(page_ids))),
            reason="Retrieved transcript windows around roll/spell/question terms before model call.",
        )
    ]


def _generic_page_items(
    memory: PagedMemory,
    question: str,
    *,
    source_benchmark: str,
    source_task: str,
    config: VirtualContextConfig,
) -> list[EvidenceItem]:
    q_terms = set(_tokens(question)) - STOPWORDS
    q_phrase = question.strip().lower()
    scored: list[tuple[float, PageRecord, str]] = []
    for page in memory.pages:
        text = _read_page(memory, page)
        low = text.lower()
        score = 0.0
        for term in q_terms:
            score += min(6, low.count(term))
        if q_phrase and q_phrase in low:
            score += 20.0
        # Prefer pages with concrete values for numeric/counting questions.
        if re.search(r"\b(count|total|how many|percentage|percent|number)\b", question, re.I) and re.search(r"\b\d+\b", text):
            score += 5.0
        # Pull in direct evidence around query terms instead of dumping whole pages.
        if score > 0:
            snippet = _best_page_snippet(text, q_terms, max_chars=config.max_item_tokens * 4)
            scored.append((score, page, snippet))

    scored.sort(key=lambda item: (-item[0], item[1].page_id))
    out: list[EvidenceItem] = []
    for score, page, snippet in scored[: config.max_items]:
        page_ids = _neighbor_page_ids(memory, page.page_id, radius=config.neighbor_radius if score >= 12 else 0)
        text_parts = [f"[page {page.page_id} lines {page.line_start}-{page.line_end}]", snippet]
        # Locality: if a page is very relevant, include short previews from neighbors.
        if len(page_ids) > 1:
            for neighbor_id in page_ids:
                if neighbor_id == page.page_id:
                    continue
                neighbor = memory.pages[neighbor_id - 1]
                neighbor_text = _read_page(memory, neighbor)
                text_parts.append(f"\n[neighbor page {neighbor_id} preview]\n{_preview(neighbor_text, 700)}")
        out.append(
            EvidenceItem(
                kind="page_snippet",
                title=f"question-term page {page.page_id}",
                text="\n".join(text_parts),
                score=score,
                page_ids=tuple(page_ids),
                reason="Generic scored page snippet based on question terms and locality.",
            )
        )
    return out


def _add_light_morph_variants(terms: list[str]) -> list[str]:
    out: list[str] = []
    for term in terms:
        out.append(term)
        if len(term) < 3:
            continue
        if term.endswith("s"):
            out.append(term[:-1])
        else:
            out.append(term + "s")
        if not term.endswith("ed"):
            out.append(term + "ed")
        if not term.endswith("ing"):
            out.append(term + "ing")
    # de-duplicate in order
    seen: set[str] = set()
    deduped: list[str] = []
    for term in out:
        if term and term not in seen:
            deduped.append(term)
            seen.add(term)
    return deduped


def _page_term_stats(memory: PagedMemory) -> list[tuple[PageRecord, str, Counter[str]]]:
    stats: list[tuple[PageRecord, str, Counter[str]]] = []
    for page in memory.pages:
        text = _read_page(memory, page)
        toks = [tok for tok in _tokens(text) if tok not in STOPWORDS and len(tok) >= 2]
        stats.append((page, text, Counter(toks)))
    return stats


def _rank_pages_with_weights(
    page_stats: list[tuple[PageRecord, str, Counter[str]]],
    weights: Counter[str],
) -> list[tuple[float, PageRecord, str, Counter[str]]]:
    if not page_stats:
        return []
    n_pages = len(page_stats)
    df: Counter[str] = Counter()
    for _page, _text, counter in page_stats:
        for term in counter:
            df[term] += 1

    ranked: list[tuple[float, PageRecord, str, Counter[str]]] = []
    for page, text, counter in page_stats:
        doc_len = sum(counter.values()) or 1
        score = 0.0
        for term, weight in weights.items():
            if term not in counter:
                continue
            # BM25-ish lexical score with query weights.
            tf = counter[term]
            idf = math.log((n_pages + 1) / (df[term] + 0.5)) + 1.0
            bm25_tf = (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * doc_len / 700.0))
            score += float(weight) * idf * bm25_tf
        if score > 0:
            ranked.append((score, page, text, counter))
    ranked.sort(key=lambda item: (-item[0], item[1].page_id))
    return ranked


def _estimate_rlm_expansion(
    top_ranked: list[tuple[float, PageRecord, str, Counter[str]]],
    page_stats: list[tuple[PageRecord, str, Counter[str]]],
    cfg: RlmContextConfig,
) -> Counter[str]:
    if not top_ranked:
        return Counter()
    n_pages = len(page_stats)
    df: Counter[str] = Counter()
    for _page, _text, counter in page_stats:
        for term in counter:
            df[term] += 1

    expansion: Counter[str] = Counter()
    max_score = max(score for score, *_ in top_ranked) or 1.0
    for rank, (score, _page, _text, counter) in enumerate(top_ranked, start=1):
        rel_weight = (score / max_score) / math.sqrt(rank)
        doc_len = sum(counter.values()) or 1
        for term, tf in counter.items():
            if term in STOPWORDS or len(term) < 3 or term.isdigit():
                continue
            # Avoid terms that appear in nearly every page; they are poor expanders.
            if df[term] / max(1, n_pages) > 0.55:
                continue
            idf = math.log((n_pages + 1) / (df[term] + 0.5)) + 1.0
            expansion[term] += rel_weight * min(tf / doc_len * 100.0, 5.0) * idf
    return Counter(dict(expansion.most_common(cfg.expansion_terms)))


def _rm3_mix(original: Counter[str], expansion: Counter[str], *, original_query_weight: float) -> Counter[str]:
    out: Counter[str] = Counter()
    total_orig = sum(original.values()) or 1.0
    total_exp = sum(expansion.values()) or 1.0
    for term, value in original.items():
        out[term] += original_query_weight * value / total_orig
    for term, value in expansion.items():
        out[term] += (1.0 - original_query_weight) * value / total_exp
    return out


def _select_items(items: list[EvidenceItem], cfg: VirtualContextConfig) -> tuple[EvidenceItem, ...]:
    # De-duplicate by text preview and page set.
    deduped: list[EvidenceItem] = []
    seen: set[tuple[str, tuple[int, ...]]] = set()
    for item in sorted(items, key=lambda item: (-item.score, item.kind, item.title)):
        key = (_preview(item.text, 120), item.page_ids)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    selected: list[EvidenceItem] = []
    used = 0
    header_allowance = 500
    for item in deduped:
        item_tokens = item.tokens_est
        if item_tokens > cfg.max_item_tokens and item.kind not in {"structured_trace", "event_windows"}:
            item = EvidenceItem(
                kind=item.kind,
                title=item.title,
                text=item.text[: cfg.max_item_tokens * 4],
                score=item.score,
                page_ids=item.page_ids,
                reason=item.reason + " (trimmed)",
            )
            item_tokens = item.tokens_est
        if used + item_tokens + header_allowance > cfg.budget_tokens and selected:
            continue
        selected.append(item)
        used += item_tokens
        if len(selected) >= cfg.max_items:
            break
    return tuple(selected)


def _render_packet_text(
    selected: Iterable[EvidenceItem],
    *,
    question: str,
    source_benchmark: str,
    source_task: str,
    memory: PagedMemory,
) -> str:
    lines = [
        "VIRTUAL CONTEXT MEMORY PACKET",
        f"Source benchmark: {source_benchmark}",
        f"Source task: {source_task}",
        f"Original source tokens estimated: {memory.total_tokens_est}",
        f"Original source pages: {memory.page_count}",
        f"Question used for retrieval: {question}",
        "This packet is the current resident working set selected by the system memory kernel.",
        "",
    ]
    for idx, item in enumerate(selected, start=1):
        pages = ", ".join(str(p) for p in item.page_ids) if item.page_ids else "n/a"
        lines.extend(
            [
                f"## Evidence {idx}: {item.title}",
                f"kind: {item.kind}; score: {item.score:.1f}; pages: {pages}; reason: {item.reason}",
                item.text.strip(),
                "",
            ]
        )
    if len(lines) <= 8:
        lines.append("No high-confidence evidence was selected; answer cautiously from the provided packet only.")
    return "\n".join(lines).strip()


def _read_page(memory: PagedMemory, page: PageRecord) -> str:
    return (memory.root / page.file).read_text(errors="replace")


def _neighbor_page_ids(memory: PagedMemory, page_id: int, *, radius: int) -> list[int]:
    start = max(1, page_id - radius)
    end = min(memory.page_count, page_id + radius)
    return list(range(start, end + 1))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9_'-]*|\d+(?:\.\d+)?", text.lower())


def _capitalized_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"\b[A-Z][A-Za-z'’]*(?:\s+[A-Z][A-Za-z'’]*){0,3}\b", text):
        term = match.group(0).strip()
        if term.lower() not in STOPWORDS:
            terms.append(term)
    return terms


def _sentence_units(text: str) -> list[str]:
    # Preserve the concise BABILong facts even when embedded in prose lines.
    units = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [unit.strip() for unit in units if unit.strip()]


def _context_windows(text: str, *, terms: set[str], max_windows: int, radius_chars: int = 650) -> list[str]:
    if not terms:
        return []
    low = text.lower()
    matches: list[tuple[int, int]] = []
    for term in sorted(terms, key=len, reverse=True):
        if len(term) < 2:
            continue
        for match in re.finditer(re.escape(term.lower()), low):
            matches.append((match.start(), match.end()))
            if len(matches) >= max_windows * 3:
                break
    if not matches:
        return []
    matches.sort()
    windows: list[str] = []
    used_ranges: list[tuple[int, int]] = []
    for start, end in matches:
        w_start = max(0, start - radius_chars)
        w_end = min(len(text), end + radius_chars)
        if any(not (w_end < a or w_start > b) for a, b in used_ranges):
            continue
        used_ranges.append((w_start, w_end))
        windows.append(text[w_start:w_end].strip())
        if len(windows) >= max_windows:
            break
    return windows


def _best_page_snippet(text: str, terms: set[str], *, max_chars: int) -> str:
    windows = _context_windows(text, terms=terms, max_windows=4, radius_chars=max(350, max_chars // 8))
    if not windows:
        return _preview(text, max_chars)
    snippet = "\n---\n".join(windows)
    if len(snippet) > max_chars:
        return snippet[: max_chars - 1].rstrip() + "…"
    return snippet


def _preview(text: str, max_chars: int = 180) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max_chars - 1].rstrip() + "…"
