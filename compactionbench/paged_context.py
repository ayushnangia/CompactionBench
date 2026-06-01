"""Paged external memory for long-context experiments.

The goal of this module is to make an "infinite context" style arm that is
more disciplined than handing the agent one giant text file.  The original
source is split into stable pages, a small page table is provided in the prompt,
and a tiny standalone ``pager.py`` tool lets the agent search and load pages on
demand.

This intentionally resembles an operating-system memory hierarchy:

- model context window: RAM / working set
- page files: disk-backed source of truth
- pager.py search/show/grep: page-fault handler
- page table: compact map of the external memory

The implementation is deterministic and local.  It does not summarize or delete
content; it only changes how the agent can access the content.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from .chunking import CHARS_PER_TOKEN, estimate_tokens


@dataclass(frozen=True)
class PageRecord:
    page_id: int
    file: str
    char_start: int
    char_end: int
    line_start: int
    line_end: int
    tokens_est: int
    chars: int
    preview: str


@dataclass(frozen=True)
class PagedMemory:
    root: Path
    page_tokens: int
    overlap_tokens: int
    total_chars: int
    total_tokens_est: int
    pages: tuple[PageRecord, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def manifest(self) -> dict[str, object]:
        return {
            "format": "compactionbench.paged_context.v1",
            "page_tokens": self.page_tokens,
            "overlap_tokens": self.overlap_tokens,
            "total_chars": self.total_chars,
            "total_tokens_est": self.total_tokens_est,
            "page_count": self.page_count,
        }


def write_paged_memory(
    context: str,
    root: Path,
    *,
    page_tokens: int = 1200,
    overlap_tokens: int = 120,
    write_tool: bool = True,
) -> PagedMemory:
    """Write a paged representation of ``context`` under ``root``.

    Files written:

    - ``pages/page_000001.txt`` ... exact source page text
    - ``page_index.jsonl`` one JSON record per page
    - ``manifest.json`` metadata
    - ``page_table.md`` compact human-readable map
    - ``pager.py`` standalone search/show helper, if ``write_tool`` is true
    """

    if page_tokens <= 0:
        raise ValueError("page_tokens must be > 0")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be >= 0")
    if overlap_tokens >= page_tokens:
        raise ValueError("overlap_tokens must be smaller than page_tokens")

    root.mkdir(parents=True, exist_ok=True)
    pages_dir = root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    chunks = _chunk_with_overlap(context, page_tokens=page_tokens, overlap_tokens=overlap_tokens)
    records: list[PageRecord] = []
    for idx, (start, end, text) in enumerate(chunks, start=1):
        filename = f"pages/page_{idx:06d}.txt"
        (root / filename).write_text(text)
        line_start = context.count("\n", 0, start) + 1
        line_end = context.count("\n", 0, max(start, end - 1)) + 1
        records.append(
            PageRecord(
                page_id=idx,
                file=filename,
                char_start=start,
                char_end=end,
                line_start=line_start,
                line_end=line_end,
                tokens_est=estimate_tokens(text),
                chars=len(text),
                preview=_preview(text),
            )
        )

    memory = PagedMemory(
        root=root,
        page_tokens=page_tokens,
        overlap_tokens=overlap_tokens,
        total_chars=len(context),
        total_tokens_est=estimate_tokens(context),
        pages=tuple(records),
    )

    (root / "manifest.json").write_text(json.dumps(memory.manifest(), indent=2))
    with (root / "page_index.jsonl").open("w") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False))
            f.write("\n")
    (root / "page_table.md").write_text(render_page_table(memory))
    if write_tool:
        tool_path = root / "pager.py"
        tool_path.write_text(PAGER_TOOL)
        tool_path.chmod(0o755)
    return memory


def render_page_table(memory: PagedMemory, *, max_rows: int = 80) -> str:
    """Render a compact page table suitable for the initial prompt."""

    lines = [
        "# Paged memory table",
        "",
        f"- pages: {memory.page_count}",
        f"- estimated source tokens: {memory.total_tokens_est}",
        f"- page size: about {memory.page_tokens} tokens",
        f"- overlap: about {memory.overlap_tokens} tokens",
        "",
        "Use `python memory/pager.py search \"terms\"` to find pages and `python memory/pager.py show PAGE_ID` to load them.",
        "",
        "| page | lines | tokens | preview |",
        "|---:|---:|---:|---|",
    ]
    shown = _evenly_sample(memory.pages, max_rows)
    shown_ids = {p.page_id for p in shown}
    for page in memory.pages:
        if page.page_id not in shown_ids:
            continue
        preview = page.preview.replace("|", "\\|")
        lines.append(f"| {page.page_id} | {page.line_start}-{page.line_end} | {page.tokens_est} | {preview} |")
    if len(memory.pages) > len(shown):
        lines.append("")
        lines.append(f"_Showing {len(shown)} representative pages out of {len(memory.pages)}. The full index is in `memory/page_index.jsonl`._")
    return "\n".join(lines) + "\n"


def build_paged_prompt(
    question: str,
    *,
    memory: PagedMemory,
    include_page_table: bool = True,
    include_initial_working_set: bool = True,
    source_benchmark: str | None = None,
    source_task: str | None = None,
) -> str:
    """Prompt for the paged-context experiment arm."""

    page_table = render_page_table(memory, max_rows=50) if include_page_table else ""
    working_set = render_initial_working_set(memory, question, max_pages=8) if include_initial_working_set else ""
    task_hint = benchmark_hint(source_benchmark, source_task)
    return (
        "You are answering with PAGED EXTERNAL MEMORY, like an infinite-context system.\n"
        "The original source text is not in this prompt as one giant block. Instead it has been split into stable pages under ./memory/pages/.\n"
        "Use ./memory/pager.py as the page-fault handler: search for likely pages, load the page text, then answer from the loaded evidence.\n"
        "Do not use the web. Do not rely on prior memory. Do not guess if you have not loaded enough evidence.\n"
        "For exact names/numbers/options, use exact search. For short fact questions, search both the full question and the key entity plus event words (for example: `Mary journeyed travelled moved went`). For counting or aggregation, inspect all matching pages and verify counts.\n"
        f"{task_hint}"
        "Useful commands:\n"
        "  python memory/pager.py stats\n"
        "  python memory/pager.py search \"full question or important terms\" --top-k 8\n"
        "  python memory/pager.py grep \"exact phrase\" --ignore-case --context 2\n"
        "  python memory/pager.py show 12 --radius 1\n"
        "Return exactly one JSON object with one field: {\"answer\": \"...\"}. Do not include extra text.\n\n"
        f"{page_table}\n"
        f"{working_set}\n"
        f"Question:\n{question}\n"
    )


def benchmark_hint(source_benchmark: str | None, source_task: str | None) -> str:
    if source_benchmark == "babilong":
        return (
            "Benchmark hint: this is BABILong. The source may contain long carrier prose plus concise inserted story facts. "
            "Answer about the synthetic first-name story entity in those concise facts, not about unrelated carrier-novel characters with full names such as `Mary Linden`. "
            "Prefer concise state-change lines such as `Mary journeyed to the bathroom` or `Fred gave the apple to Bill` over unrelated novel passages that merely reuse the same names.\n"
        )
    if source_benchmark == "oolong":
        return "Benchmark hint: this is OOLONG-real. Answers often require aggregating D&D transcript/event evidence across one or more episodes; do not stop at the first local match.\n"
    if source_benchmark == "lme":
        return "Benchmark hint: this is LongMemEval rendered web-agent memory. Answers usually come from UI labels, procedure steps, or observed browser state in the rendered trace.\n"
    if source_benchmark == "swe_chat":
        return "Benchmark hint: this is SWE-chat. Preserve the coding conversation intent; exact string matching is less important than the requested assistant behavior.\n"
    return ""


def render_initial_working_set(memory: PagedMemory, question: str, *, max_pages: int = 8, max_chars_per_page: int = 900) -> str:
    """Render a small deterministic question-aware prefetch.

    This is the pager's initial cache, not a lossy summary. The agent can and
    should still load more pages if these candidates are insufficient.
    """

    scored: list[tuple[float, PageRecord, str]] = []
    terms = _question_terms(question)
    focus_entities = _focus_entities(question)
    qlow = question.lower()
    for page in memory.pages:
        text = (memory.root / page.file).read_text(errors="replace")
        score = _score_page_for_question(text, terms=terms, focus_entities=focus_entities, question_lower=qlow)
        if score <= 0:
            continue
        snippet = _best_snippet(text, terms=terms, focus_entities=focus_entities, max_chars=max_chars_per_page)
        scored.append((score, page, snippet))
    scored.sort(key=lambda item: (-item[0], item[1].page_id))
    if not scored:
        return ""

    lines = [
        "# Initial working set",
        "",
        "The pager preloaded these candidate pages using only the question text. Verify by loading pages if needed.",
        "",
    ]
    for score, page, snippet in scored[:max_pages]:
        lines.append(f"## Candidate page {page.page_id} score={score:.1f} lines={page.line_start}-{page.line_end}")
        lines.append(snippet.strip()[:max_chars_per_page])
        lines.append("")
    return "\n".join(lines)


_QUESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
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

_STRONG_EVENT_WORDS = {
    "journeyed",
    "travelled",
    "traveled",
    "moved",
    "grabbed",
    "picked",
    "discarded",
    "dropped",
    "handed",
    "gave",
    "passed",
    "received",
    "took",
    "put",
    "carried",
}
_WEAK_EVENT_WORDS = {"went", "go", "goes", "left", "entered", "opened", "closed", "submitted", "created", "assigned", "changed", "updated"}
_COMMON_LOCATION_WORDS = {"bathroom", "bedroom", "garden", "hallway", "kitchen", "office", "school", "cinema", "park"}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_'-]*|\d+(?:\.\d+)?", text.lower())


def _question_terms(question: str) -> list[str]:
    terms = [tok for tok in _tokenize(question) if tok not in _QUESTION_STOPWORDS]
    qlow = question.lower()
    # Keep terms literal. Event/location vocabulary is handled as a proximity
    # boost in _score_page_for_question; adding every event word as a normal
    # term makes unrelated narrative pages look relevant.
    return terms


def _focus_entities(question: str) -> list[str]:
    entities = [m.group(0).lower() for m in re.finditer(r"\b[A-Z][a-z]+\b", question)]
    # Common benchmark names are often capitalized at sentence start; keep all
    # capitalized one-word entities and de-duplicate in order.
    out: list[str] = []
    for ent in entities:
        if ent not in out and ent not in _QUESTION_STOPWORDS:
            out.append(ent)
    return out


def _score_page_for_question(text: str, *, terms: list[str], focus_entities: list[str], question_lower: str) -> float:
    low = text.lower()
    score = 0.0
    for term in terms:
        score += min(6, low.count(term))
    if question_lower and question_lower in low:
        score += 25.0
    for entity in focus_entities:
        if entity not in low:
            continue
        score += 6.0
        if "where" in question_lower and re.search(
            rf"\b{re.escape(entity)}\b.{{0,140}}\b(journeyed|travelled|traveled|moved|went)\b.{{0,140}}\b(bathroom|bedroom|garden|hallway|kitchen|office|school|cinema|park)\b",
            low,
        ):
            score += 45.0
        for verb in _STRONG_EVENT_WORDS:
            if re.search(rf"\b{re.escape(entity)}\b.{{0,120}}\b{verb}\b|\b{verb}\b.{{0,120}}\b{re.escape(entity)}\b", low):
                score += 35.0
                break
        for verb in _WEAK_EVENT_WORDS:
            if re.search(rf"\b{re.escape(entity)}\b.{{0,100}}\b{verb}\b|\b{verb}\b.{{0,100}}\b{re.escape(entity)}\b", low):
                score += 8.0
                break
    if "where" in question_lower and any(loc in low for loc in _COMMON_LOCATION_WORDS):
        score += 4.0
    if any(word in question_lower for word in ("count", "total", "how many", "percentage", "percent")) and re.search(r"\b\d+\b", text):
        score += 8.0
    return score


def _best_snippet(text: str, *, terms: list[str], focus_entities: list[str], max_chars: int) -> str:
    lines = text.splitlines() or [text]
    term_set = {term.lower() for term in terms if len(term) >= 3}
    entity_set = set(focus_entities)
    scored_lines: list[tuple[float, int]] = []
    for idx, line in enumerate(lines):
        low = line.lower()
        score = 0.0
        if any(ent in low for ent in entity_set):
            score += 10.0
        if any(term in low for term in term_set):
            score += 2.0
        if any(verb in low for verb in _STRONG_EVENT_WORDS):
            score += 8.0
        if any(verb in low for verb in _WEAK_EVENT_WORDS):
            score += 2.0
        if any(loc in low for loc in _COMMON_LOCATION_WORDS):
            score += 2.0
        if score > 0:
            scored_lines.append((score, idx))
    if not scored_lines:
        return text[:max_chars]
    scored_lines.sort(key=lambda item: (-item[0], item[1]))
    chosen = sorted({idx for _, idx in scored_lines[:4]})
    blocks: list[str] = []
    for idx in chosen:
        start = max(0, idx - 1)
        end = min(len(lines), idx + 2)
        block = "\n".join(f"{line_no + 1}: {lines[line_no]}" for line_no in range(start, end))
        blocks.append(block)
    out = "\n---\n".join(blocks)
    return out[:max_chars]


def _chunk_with_overlap(context: str, *, page_tokens: int, overlap_tokens: int) -> list[tuple[int, int, str]]:
    if not context:
        return [(0, 0, "")]
    page_chars = max(1, page_tokens * CHARS_PER_TOKEN)
    overlap_chars = max(0, overlap_tokens * CHARS_PER_TOKEN)
    step = max(1, page_chars - overlap_chars)
    chunks: list[tuple[int, int, str]] = []
    start = 0
    n = len(context)
    while start < n:
        target_end = min(n, start + page_chars)
        end = _snap_end(context, start, target_end, max_end=min(n, start + int(page_chars * 1.15)))
        if end <= start:
            end = target_end
        chunks.append((start, end, context[start:end]))
        if end >= n:
            break
        start = max(0, end - overlap_chars)
    return chunks


def _snap_end(context: str, start: int, target_end: int, *, max_end: int) -> int:
    """Prefer ending pages on paragraph/newline/sentence boundaries near target."""

    if target_end >= len(context):
        return len(context)
    window = context[target_end:max_end]
    for pattern in ("\n\n", "\n", ". ", "? ", "! "):
        pos = window.find(pattern)
        if pos != -1:
            return target_end + pos + len(pattern)
    # Avoid a very short trailing fragment before the next newline.
    back_window = context[max(start, target_end - 300):target_end]
    pos = back_window.rfind("\n")
    if pos != -1 and len(back_window) - pos < 180:
        return max(start + 1, target_end - (len(back_window) - pos - 1))
    return target_end


def _preview(text: str, max_chars: int = 180) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max_chars - 1].rstrip() + "…"


def _evenly_sample(items: Iterable[PageRecord], max_rows: int) -> list[PageRecord]:
    seq = list(items)
    if len(seq) <= max_rows:
        return seq
    if max_rows <= 0:
        return []
    if max_rows == 1:
        return [seq[0]]
    idxs = sorted({round(i * (len(seq) - 1) / (max_rows - 1)) for i in range(max_rows)})
    return [seq[i] for i in idxs]


PAGER_TOOL = textwrap.dedent(
    r'''#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "page_index.jsonl"
PAGES = ROOT / "pages"

# Generic high-signal event words. These are not answers; they help rank pages
# that contain concrete state changes rather than incidental mentions.
STRONG_EVENT_VERBS = {
    "journeyed", "travelled", "traveled", "moved", "grabbed", "picked", "discarded",
    "dropped", "handed", "gave", "passed", "received", "took", "put", "carried",
}
WEAK_EVENT_VERBS = {"went", "go", "goes", "left", "entered", "opened", "closed", "submitted", "created", "assigned", "changed", "updated"}
COMMON_LOCATIONS = {"bathroom", "bedroom", "garden", "hallway", "kitchen", "office", "school", "cinema", "park"}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "did", "do", "does", "for", "from",
    "how", "i", "in", "is", "it", "of", "on", "or", "the", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "with",
}


def load_index():
    rows = []
    with INDEX.open() as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def page_path(page_id):
    return PAGES / f"page_{int(page_id):06d}.txt"


def read_page(page_id):
    return page_path(page_id).read_text(errors="replace")


def tokenize(text):
    return re.findall(r"[A-Za-z][A-Za-z0-9_'-]*|\d+(?:\.\d+)?", text.lower())


def stats(_args):
    manifest = json.loads((ROOT / "manifest.json").read_text())
    print(json.dumps(manifest, indent=2))


def event_boost(low_text, terms, query):
    """Boost pages with concrete state-change events involving query terms."""
    boost = 0.0
    term_set = {t for t in terms if len(t) >= 3}
    if not term_set:
        return 0.0
    for term in term_set:
        if term not in low_text:
            continue
        # For location questions, heavily prefer entity -> movement -> location.
        if "where" in query.lower() and re.search(
            rf"\b{re.escape(term)}\b.{{0,140}}\b(journeyed|travelled|traveled|moved|went)\b.{{0,140}}\b(bathroom|bedroom|garden|hallway|kitchen|office|school|cinema|park)\b",
            low_text,
        ):
            boost += 45.0
        # Strong verbs near the queried entity are often the actual memory event.
        for verb in STRONG_EVENT_VERBS:
            if re.search(rf"\b{re.escape(term)}\b.{{0,120}}\b{verb}\b|\b{verb}\b.{{0,120}}\b{re.escape(term)}\b", low_text):
                boost += 35.0
                break
        for verb in WEAK_EVENT_VERBS:
            if re.search(rf"\b{re.escape(term)}\b.{{0,100}}\b{verb}\b|\b{verb}\b.{{0,100}}\b{re.escape(term)}\b", low_text):
                boost += 8.0
                break
        if any(loc in low_text for loc in COMMON_LOCATIONS):
            boost += 4.0
    return boost


def search(args):
    query = args.query
    terms = [tok for tok in tokenize(query) if tok not in STOPWORDS]
    quoted = re.findall(r'"([^"]+)"', query)
    rows = load_index()
    scored = []
    for row in rows:
        text = read_page(row["page_id"])
        low = text.lower()
        toks = tokenize(text)
        tok_counts = {}
        for tok in toks:
            tok_counts[tok] = tok_counts.get(tok, 0) + 1
        score = 0.0
        for term in terms:
            score += min(8, tok_counts.get(term, 0))
        for phrase in quoted:
            score += 12 * low.count(phrase.lower())
        # Also reward unquoted multi-word exact phrase if present.
        if len(query.strip()) >= 4 and query.lower() in low:
            score += 20
        score += event_boost(low, terms, query)
        if score > 0:
            scored.append((score, row, snippets(text, terms, quoted, limit=args.snippets)))
    scored.sort(key=lambda x: (-x[0], x[1]["page_id"]))
    for score, row, snips in scored[: args.top_k]:
        print(f"\n=== page {row['page_id']} score={score:g} lines={row['line_start']}-{row['line_end']} file={row['file']} ===")
        print(f"preview: {row['preview']}")
        for snip in snips:
            print(snip)
    if not scored:
        print("No matching pages.")


def snippets(text, terms, phrases, limit=3, context=1):
    lines = text.splitlines()
    want = []
    low_terms = [t.lower() for t in terms]
    low_phrases = [p.lower() for p in phrases]
    for i, line in enumerate(lines):
        low = line.lower()
        if any(t in low for t in low_terms) or any(p in low for p in low_phrases):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            block = []
            for j in range(start, end):
                block.append(f"  {j+1}: {lines[j]}")
            want.append("\n".join(block))
            if len(want) >= limit:
                break
    if not want and lines:
        want.append("\n".join(f"  {j+1}: {line}" for j, line in enumerate(lines[: min(5, len(lines))])))
    return want


def grep(args):
    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        pat = re.compile(args.pattern, flags)
    except re.error:
        pat = re.compile(re.escape(args.pattern), flags)
    rows = load_index()
    hits = 0
    for row in rows:
        lines = read_page(row["page_id"]).splitlines()
        matched = [i for i, line in enumerate(lines) if pat.search(line)]
        if not matched:
            continue
        print(f"\n=== page {row['page_id']} lines={row['line_start']}-{row['line_end']} file={row['file']} ===")
        shown = set()
        for i in matched[: args.max_hits_per_page]:
            for j in range(max(0, i - args.context), min(len(lines), i + args.context + 1)):
                if j in shown:
                    continue
                shown.add(j)
                marker = ">" if j == i else " "
                print(f"{marker} {j+1}: {lines[j]}")
            hits += 1
        if hits >= args.max_hits:
            break
    if hits == 0:
        print("No grep matches.")


def show(args):
    rows = {row["page_id"]: row for row in load_index()}
    start = max(1, args.page_id - args.radius)
    end = min(max(rows), args.page_id + args.radius)
    for page_id in range(start, end + 1):
        row = rows.get(page_id)
        if not row:
            continue
        print(f"\n=== page {page_id} lines={row['line_start']}-{row['line_end']} file={row['file']} ===")
        text = read_page(page_id)
        if args.line_numbers:
            for i, line in enumerate(text.splitlines(), start=1):
                print(f"{i}: {line}")
        else:
            print(text)


def table(args):
    rows = load_index()
    for row in rows[: args.limit]:
        print(f"{row['page_id']:>5} lines={row['line_start']}-{row['line_end']} tokens={row['tokens_est']} preview={row['preview']}")
    if len(rows) > args.limit:
        print(f"... {len(rows)-args.limit} more pages. Use --limit to show more.")


def main():
    p = argparse.ArgumentParser(description="Search and load CompactionBench paged memory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stats")
    s.set_defaults(func=stats)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--top-k", type=int, default=8)
    s.add_argument("--snippets", type=int, default=3)
    s.set_defaults(func=search)

    s = sub.add_parser("grep")
    s.add_argument("pattern")
    s.add_argument("--ignore-case", "-i", action="store_true")
    s.add_argument("--context", "-C", type=int, default=1)
    s.add_argument("--max-hits", type=int, default=40)
    s.add_argument("--max-hits-per-page", type=int, default=5)
    s.set_defaults(func=grep)

    s = sub.add_parser("show")
    s.add_argument("page_id", type=int)
    s.add_argument("--radius", type=int, default=0)
    s.add_argument("--line-numbers", action="store_true")
    s.set_defaults(func=show)

    s = sub.add_parser("table")
    s.add_argument("--limit", type=int, default=80)
    s.set_defaults(func=table)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
'''
)
