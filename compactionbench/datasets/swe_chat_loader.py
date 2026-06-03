"""SWE-chat task loader for CompactionBench.

Turns real coding agent conversations into compaction benchmark tasks.
Uses real user questions from SWE-chat Codex transcripts embedded in
long realistic context to test compaction at 150k+ tokens.
"""

from __future__ import annotations

import json
import random as _random
import re
from pathlib import Path

from ..core.schema import Scorer, TaskRow

SWE_CHAT_BENCHMARK: str = "ruler"
SWE_CHAT_SCORER: Scorer = "substring_ci"

_FILLER_TEMPLATES = [
    "The assistant examined the file structure, reading through src/ and tests/ to understand the project layout.",
    "Several files were opened and analyzed for patterns and potential issues.",
    "The model ran a series of grep searches to locate relevant function definitions across the codebase.",
    "A new test was drafted to cover the edge case identified in the previous discussion.",
    "The implementation was refactored to improve readability while maintaining the same behavior.",
    "Documentation was updated to reflect the recent changes in the API.",
    "The assistant verified the changes by running the existing test suite and confirming all tests passed.",
    "A code review was performed, checking for common issues like null handling and error propagation.",
    "The model suggested an alternative approach using a different design pattern.",
    "Several iterations were needed to get the implementation right.",
    "The assistant checked the git history to understand when a particular change was introduced.",
    "Package dependencies were updated to their latest compatible versions.",
    "The model identified a potential performance bottleneck and proposed an optimization.",
    "Configuration files were reviewed for consistency across different environments.",
    "The assistant traced through the call stack to understand how a particular function was invoked.",
]


def _extract_sweturns(transcript_path: Path) -> list[dict]:
    turns: list[dict] = []
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "event_msg":
                continue
            payload = msg.get("payload", {})
            if not isinstance(payload, dict):
                continue
            ptype = payload.get("type", "")
            if ptype not in ("user_message", "agent_message"):
                continue
            content = payload.get("message", "")
            if isinstance(content, list):
                content = " ".join(
                    str(c.get("text", "")) if isinstance(c, dict) else str(c)
                    for c in content
                )
            content = str(content).strip()
            if len(content) < 10:
                continue
            role = "user" if ptype == "user_message" else "assistant"
            turns.append({"role": role, "content": content})
    return turns


def _render_context(turns: list[dict]) -> str:
    parts = []
    for turn in turns:
        parts.append(f"[{turn['role'].upper()}]: {turn['content']}")
    return "\n\n".join(parts)


def _generate_filler(target_tokens: int) -> str:
    rng = _random.Random(42)
    chars_needed = target_tokens * 4
    parts = []
    chars = 0
    while chars < chars_needed:
        part = rng.choice(_FILLER_TEMPLATES)
        parts.append(part)
        chars += len(part) + 1
    return " ".join(parts)


def prepare_swe_chat_tasks(
    transcript_path: Path,
    *,
    count: int = 5,
    target_context_tokens: int = 160000,
    session_id: str = "",
) -> list[TaskRow]:
    turns = _extract_sweturns(transcript_path)
    if not turns:
        raise RuntimeError(f"No turns found in {transcript_path}")

    user_indices = [(i, t) for i, t in enumerate(turns) if t["role"] == "user"]
    if not user_indices:
        raise RuntimeError("No user turns found")

    # Use middle-third user turns as task questions
    start = len(user_indices) // 3
    end = 2 * len(user_indices) // 3
    candidates = user_indices[start:end]

    sid = session_id or transcript_path.stem[:12]
    tasks: list[TaskRow] = []

    for idx, turn in candidates:
        if len(tasks) >= count:
            break
        if idx + 1 >= len(turns) or turns[idx + 1]["role"] != "assistant":
            continue

        ctx_turns = turns[:idx]
        real_context = _render_context(ctx_turns)
        real_tokens = len(real_context) // 4

        if real_tokens < target_context_tokens:
            filler = _generate_filler(target_context_tokens - real_tokens)
            context = real_context + "\n\n" + filler
        else:
            context = real_context

        question = turn["content"]
        gold = turns[idx + 1]["content"][:4000]
        ctx_est = len(context) // 4

        task_id = f"swe-chat-{_sanitize(sid)}-turn{idx:04d}"
        tasks.append(
            TaskRow(
                task_id=task_id,
                source_benchmark=SWE_CHAT_BENCHMARK,
                source_task="swe_chat",
                source_sample_id=f"{sid}-turn{idx}",
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=SWE_CHAT_SCORER,
                metadata={
                    "session_id": sid,
                    "turn_index": idx,
                    "total_turns": len(turns),
                    "real_context_tokens": real_tokens,
                    "context_tokens_est": ctx_est,
                },
            )
        )

    return tasks


def _sanitize(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-")
