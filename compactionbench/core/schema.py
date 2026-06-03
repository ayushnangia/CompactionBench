"""Pydantic models for the simple direct-injection experiment path.

The benchmark now uses JSONL task rows with raw long context stored directly in
one field. At run time the context is chunked into repeated user messages and
fed into a live harness session. Run artifacts stay intentionally lean: they
record prompt/response previews, compaction events, tool contamination, and the
final parsed answer, but they do not duplicate the full context again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CompactionMode = Literal["off", "auto"]
HarnessName = Literal["claude_code", "codex"]
SourceBenchmark = Literal[
    "ruler",
    "babilong",
    "longbench_v2",
    "oolong",
    "lme",
    "clb",
    "synthetic",
    "swe_chat",
]
Scorer = Literal[
    "exact",
    "exact_ci",
    "substring_ci",
    "multiple_choice",
    "csv_set_ci",
    "numeric_075",
    "csv_overlap_ci",
    "oolong_text_ci",
    "oolong_comparison_ci",
    "date_ci",
    "month_year_ci",
]
TurnRole = Literal["user", "assistant", "tool"]
TurnKind = Literal["context_chunk", "final_question", "other"]


class TaskRow(BaseModel):
    """One benchmark sample stored as a single JSONL row."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., pattern=r"^[A-Za-z0-9._:-]+$")
    source_benchmark: SourceBenchmark
    source_task: str = Field(..., min_length=1, max_length=200)
    source_sample_id: str = Field(..., min_length=1, max_length=200)

    context: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=20000)
    gold_answer: str = Field(..., min_length=1, max_length=4000)
    gold_answer_aliases: list[str] = Field(default_factory=list)
    scorer: Scorer
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAnswer(BaseModel):
    """The exact JSON object the harness is asked to emit at the end."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1, max_length=4000)


class TurnTrace(BaseModel):
    """Compact, human-readable trace for one prompt/response step."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=1)
    role: TurnRole
    kind: TurnKind = "other"
    chunk_index: int | None = Field(default=None, ge=1)
    chunk_count: int | None = Field(default=None, ge=1)
    chars: int | None = Field(default=None, ge=0)
    tokens_est: int | None = Field(default=None, ge=0)
    content_preview: str | None = Field(default=None, max_length=400)


class ToolEvent(BaseModel):
    """Any tool-like action means the run is contaminated for the main metric."""

    model_config = ConfigDict(extra="forbid")

    turn_index: int | None = Field(default=None, ge=1)
    tool_name: str = Field(..., min_length=1, max_length=200)
    raw: dict[str, Any] = Field(default_factory=dict)


class CompactionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_index: int | None = Field(default=None, ge=1)
    mode: CompactionMode
    before_tokens: int | None = Field(default=None, ge=0)
    after_tokens: int | None = Field(default=None, ge=0)
    raw: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """One direct-injection run artifact."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., pattern=r"^[A-Za-z0-9._:-]+$")
    source_benchmark: SourceBenchmark
    source_task: str = Field(..., min_length=1, max_length=200)
    source_sample_id: str = Field(..., min_length=1, max_length=200)

    harness: HarnessName
    model: str = Field(..., min_length=1, max_length=200)
    condition: CompactionMode
    session_id: str = Field(..., min_length=1, max_length=200)

    chunk_tokens: int = Field(..., gt=0)
    chunk_count: int = Field(..., ge=1)
    context_tokens_est: int = Field(..., ge=1)

    scorer: Scorer
    gold_answer: str = Field(..., min_length=1, max_length=4000)
    gold_answer_aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    turns: list[TurnTrace] = Field(default_factory=list)
    tool_events: list[ToolEvent] = Field(default_factory=list)
    compaction_events: list[CompactionEvent] = Field(default_factory=list)

    final_answer_raw: str | None = None
    final_answer_parsed: AgentAnswer | None = None
    parse_ok: bool = False
    correct: bool | None = None
    contaminated_by_tools: bool = False

    error: str | None = None
    duration_s: float | None = Field(default=None, ge=0)


def parse_agent_answer(raw: str) -> AgentAnswer:
    """Extract the last JSON object in ``raw`` and validate it with Pydantic."""

    end = raw.rfind("}")
    if end == -1:
        raise ValueError("No JSON object found in agent output")

    depth = 0
    start = -1
    for i in range(end, -1, -1):
        ch = raw[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start == -1:
        raise ValueError("Unbalanced JSON braces in agent output")
    return AgentAnswer.model_validate(json.loads(raw[start : end + 1]))


def load_task_rows(path: Path) -> list[TaskRow]:
    """Validate every non-empty line of a task JSONL file."""

    rows: list[TaskRow] = []
    with path.open() as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(TaskRow.model_validate_json(line))
            except Exception as e:  # pragma: no cover - lineno context matters
                raise ValueError(f"{path}:{lineno}: {e}") from e
    return rows


def write_task_rows(rows: list[TaskRow], path: Path) -> None:
    ensure_unique_task_ids(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(row.model_dump_json())
            f.write("\n")


def ensure_unique_task_ids(rows: list[TaskRow]) -> None:
    seen: dict[str, int] = {}
    dupes: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if row.task_id in seen:
            dupes.append(row.task_id)
        else:
            seen[row.task_id] = idx
    if dupes:
        dupes_fmt = ", ".join(sorted(set(dupes)))
        raise ValueError(f"Duplicate task_id values found: {dupes_fmt}")
