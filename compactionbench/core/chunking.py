"""Simple chunking for direct context injection.

The earlier version normalized whitespace when merging paragraphs and when
splitting long paragraphs on sentence boundaries. For this benchmark we prefer
higher fidelity: chunks should preserve the original context text as closely as
possible so we are not accidentally changing the task while preparing it.

This implementation keeps paragraph separators in the emitted chunks and only
falls back to raw character slicing for oversize units.
"""

from __future__ import annotations

import re

CHARS_PER_TOKEN = 4
MAX_CHUNK_OVERFLOW = 1.2


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


_PARA_BOUNDARY = re.compile(r"\n\s*\n")


def chunk_text(text: str, chunk_tokens: int) -> list[str]:
    if chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be > 0")

    if not text:
        return [text]

    target_chars = chunk_tokens * CHARS_PER_TOKEN
    max_chars = int(target_chars * MAX_CHUNK_OVERFLOW)
    units = _paragraph_units(text)

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            chunks.append("".join(buf))
        buf = []
        buf_len = 0

    for unit in units:
        unit_len = len(unit)
        if unit_len > max_chars:
            flush()
            chunks.extend(_split_raw(unit, target_chars))
            continue
        if buf_len + unit_len > target_chars and buf_len > 0:
            flush()
        buf.append(unit)
        buf_len += unit_len

    flush()
    return [chunk for chunk in chunks if chunk]


def _paragraph_units(text: str) -> list[str]:
    """Return paragraph-like units while preserving exact separators."""

    units: list[str] = []
    cursor = 0
    for match in _PARA_BOUNDARY.finditer(text):
        end = match.end()
        piece = text[cursor:end]
        if piece.strip():
            units.append(piece)
        cursor = end
    tail = text[cursor:]
    if tail.strip() or not units:
        units.append(tail)
    return units


def _split_raw(text: str, target_chars: int) -> list[str]:
    return [text[i : i + target_chars] for i in range(0, len(text), target_chars)]
