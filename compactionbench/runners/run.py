"""Direct multi-turn runners for Claude Code and Codex.

The context lives in conversation history, not in local files. Every task row is
chunked at run time and injected over repeated user turns. This module keeps the
artifacts lean and explicitly logs tool contamination.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..core.chunking import chunk_text, estimate_tokens
from ..core.schema import (
    AgentAnswer,
    CompactionEvent,
    CompactionMode,
    RunRecord,
    TaskRow,
    ToolEvent,
    TurnTrace,
    ensure_unique_task_ids,
    load_task_rows,
    parse_agent_answer,
)
from ..core.score import score_one

CLAUDE_BIN = "claude"
CODEX_BIN = "codex"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


@dataclass
class PromptResult:
    session_id: str
    text: str
    tool_events: list[ToolEvent]
    compaction_events: list[CompactionEvent]
    duration_s: float | None = None


def load_tasks(paths: list[Path], *, task_filter: set[str] | None = None) -> list[TaskRow]:
    tasks: list[TaskRow] = []
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*.jsonl")):
                tasks.extend(load_task_rows(child))
        else:
            tasks.extend(load_task_rows(path))
    if task_filter is not None:
        tasks = [task for task in tasks if task.task_id in task_filter]
    if not tasks:
        raise RuntimeError("No task rows found after loading/filtering")
    ensure_unique_task_ids(tasks)
    return tasks


def run_claude_code_tasks(
    *,
    tasks: list[TaskRow],
    model: str,
    condition: CompactionMode,
    out_dir: Path,
    chunk_tokens: int,
    effort: str = "low",
    timeout_s: int = 900,
    settings: str | None = None,
) -> list[Path]:
    runner = ClaudeCodeRunner(
        model=model,
        condition=condition,
        chunk_tokens=chunk_tokens,
        effort=effort,
        timeout_s=timeout_s,
        settings=settings,
    )
    return _run_many(tasks=tasks, out_dir=out_dir, runner=runner)


def run_codex_tasks(
    *,
    tasks: list[TaskRow],
    model: str,
    condition: CompactionMode,
    out_dir: Path,
    chunk_tokens: int,
    timeout_s: int = 900,
    off_compact_limit: int = 2_000_000_000,
    auto_compact_limit: int | None = None,
    reasoning_effort: str = "low",
    verbosity: str = "low",
) -> list[Path]:
    runner = CodexRunner(
        model=model,
        condition=condition,
        chunk_tokens=chunk_tokens,
        timeout_s=timeout_s,
        off_compact_limit=off_compact_limit,
        auto_compact_limit=auto_compact_limit,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    )
    return _run_many(tasks=tasks, out_dir=out_dir, runner=runner)


def parse_claude_stream_json(raw: str, *, condition: CompactionMode) -> PromptResult:
    session_id = ""
    final_text = ""
    tool_events: list[ToolEvent] = []
    compaction_events: list[CompactionEvent] = []
    duration_s: float | None = None
    text_parts: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        session_id = str(event.get("session_id") or session_id)
        kind = event.get("type")

        if kind == "assistant":
            msg = event.get("message", {}) or {}
            for item in msg.get("content", []) or []:
                item_type = item.get("type")
                if item_type == "text":
                    text = str(item.get("text") or "")
                    if text:
                        text_parts.append(text)
                elif item_type == "tool_use":
                    tool_events.append(
                        ToolEvent(
                            tool_name=str(item.get("name") or "unknown"),
                            raw=item,
                        )
                    )
        elif kind == "system" and event.get("subtype") == "compact_boundary":
            meta = event.get("compact_metadata", {}) or {}
            compaction_events.append(
                CompactionEvent(
                    mode=condition,
                    before_tokens=meta.get("pre_tokens"),
                    after_tokens=meta.get("post_tokens"),
                    raw=meta,
                )
            )
        elif kind == "result":
            final_text = str(event.get("result") or final_text)
            usage = event.get("usage", {}) or {}
            server_tool_use = usage.get("server_tool_use", {}) or {}
            web_search_requests = int(server_tool_use.get("web_search_requests") or 0)
            web_fetch_requests = int(server_tool_use.get("web_fetch_requests") or 0)
            if web_search_requests > 0:
                tool_events.append(
                    ToolEvent(
                        tool_name="web_search",
                        raw={"requests": web_search_requests},
                    )
                )
            if web_fetch_requests > 0:
                tool_events.append(
                    ToolEvent(
                        tool_name="web_fetch",
                        raw={"requests": web_fetch_requests},
                    )
                )
            if event.get("duration_ms") is not None:
                duration_s = float(event["duration_ms"]) / 1000.0

    if not final_text:
        final_text = "\n".join(text_parts).strip()

    return PromptResult(
        session_id=session_id,
        text=final_text,
        tool_events=tool_events,
        compaction_events=compaction_events,
        duration_s=duration_s,
    )


def parse_codex_jsonl(raw: str, *, condition: CompactionMode) -> PromptResult:
    session_id = ""
    final_text = ""
    tool_events: list[ToolEvent] = []
    compaction_events: list[CompactionEvent] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = event.get("type")
        payload = event.get("payload", {}) or {}

        if kind == "thread.started":
            session_id = str(event.get("thread_id") or session_id)
        elif kind == "session_meta":
            session_id = str(payload.get("id") or session_id)
        elif kind in {"context_compacted", "compacted"}:
            compaction_events.append(
                CompactionEvent(mode=condition, raw=event)
            )
        elif kind == "event_msg" and payload.get("type") == "context_compacted":
            compaction_events.append(
                CompactionEvent(mode=condition, raw=payload)
            )
        elif kind == "item.completed":
            item = event.get("item", {}) or {}
            item_type = item.get("type")
            if item_type == "agent_message":
                final_text = str(item.get("text") or final_text)
            elif item_type is not None:
                tool_events.append(
                    ToolEvent(tool_name=str(item_type), raw=item)
                )
        elif kind == "response_item":
            item_type = payload.get("type")
            if item_type == "message" and payload.get("role") == "assistant":
                text_parts = []
                for part in payload.get("content", []) or []:
                    text = part.get("text")
                    if text:
                        text_parts.append(str(text))
                if text_parts:
                    final_text = "\n".join(text_parts)

    return PromptResult(
        session_id=session_id,
        text=final_text,
        tool_events=tool_events,
        compaction_events=compaction_events,
        duration_s=None,
    )


def _load_codex_session_compaction_events(session_id: str, *, condition: CompactionMode) -> list[CompactionEvent]:
    if not session_id:
        return []
    matches = sorted(CODEX_SESSIONS_DIR.rglob(f"*{session_id}.jsonl")) if CODEX_SESSIONS_DIR.exists() else []
    if not matches:
        return []

    compacted_events: list[CompactionEvent] = []
    fallback_events: list[CompactionEvent] = []
    with matches[0].open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            payload = event.get("payload", {}) or {}
            if kind == "compacted":
                compacted_events.append(CompactionEvent(mode=condition, raw=event))
            elif kind == "event_msg" and payload.get("type") == "context_compacted":
                fallback_events.append(CompactionEvent(mode=condition, raw=payload))
    return compacted_events or fallback_events


class ClaudeCodeRunner:
    harness_name = "claude_code"

    def __init__(
        self,
        *,
        model: str,
        condition: CompactionMode,
        chunk_tokens: int,
        effort: str,
        timeout_s: int,
        settings: str | None,
    ) -> None:
        if shutil.which(CLAUDE_BIN) is None:
            raise RuntimeError("`claude` binary not found in PATH")
        if not os.environ.get("ANTHROPIC_API_KEY") and not settings:
            raise RuntimeError(
                "Claude Code direct runner requires bare-mode auth. Set ANTHROPIC_API_KEY or pass "
                "a --settings value that provides apiKeyHelper for Claude --bare."
            )
        self.model = model
        self.condition = condition
        self.chunk_tokens = chunk_tokens
        self.effort = effort
        self.timeout_s = timeout_s
        self.settings = settings

    def run_task(self, task: TaskRow) -> RunRecord:
        chunks = chunk_text(task.context, self.chunk_tokens)
        context_tokens_est = sum(estimate_tokens(chunk) for chunk in chunks)
        session_id = str(uuid.uuid4())
        turns: list[TurnTrace] = []
        tool_events: list[ToolEvent] = []
        compaction_events: list[CompactionEvent] = []
        total_duration = 0.0
        final_raw: str | None = None
        parse_ok = False
        parsed: AgentAnswer | None = None
        error: str | None = None

        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="cbench-claude-") as tmpdir:
            env = os.environ.copy()
            if self.condition == "off":
                env["DISABLE_AUTOCOMPACT"] = "1"
            else:
                env.pop("DISABLE_AUTOCOMPACT", None)

            fresh = True
            turn_index = 1
            try:
                for idx, chunk in enumerate(chunks, start=1):
                    prompt = build_chunk_prompt(idx, len(chunks), chunk)
                    turns.append(
                        TurnTrace(
                            index=turn_index,
                            role="user",
                            kind="context_chunk",
                            chunk_index=idx,
                            chunk_count=len(chunks),
                            chars=len(chunk),
                            tokens_est=estimate_tokens(chunk),
                            content_preview=preview(prompt),
                        )
                    )
                    result = self._ask(
                        prompt=prompt,
                        cwd=Path(tmpdir),
                        session_id=session_id,
                        fresh=fresh,
                        env=env,
                    )
                    fresh = False
                    session_id = result.session_id or session_id
                    for event in result.tool_events:
                        event.turn_index = turn_index + 1
                    for event in result.compaction_events:
                        event.turn_index = turn_index + 1
                    tool_events.extend(result.tool_events)
                    compaction_events.extend(result.compaction_events)
                    total_duration += result.duration_s or 0.0
                    turns.append(
                        TurnTrace(
                            index=turn_index + 1,
                            role="assistant",
                            kind="context_chunk",
                            chunk_index=idx,
                            chunk_count=len(chunks),
                            chars=len(result.text),
                            tokens_est=estimate_tokens(result.text) if result.text else 0,
                            content_preview=preview(result.text),
                        )
                    )
                    turn_index += 2

                final_prompt = build_final_prompt(task.question)
                turns.append(
                    TurnTrace(
                        index=turn_index,
                        role="user",
                        kind="final_question",
                        chars=len(final_prompt),
                        tokens_est=estimate_tokens(final_prompt),
                        content_preview=preview(final_prompt),
                    )
                )
                result = self._ask(
                    prompt=final_prompt,
                    cwd=Path(tmpdir),
                    session_id=session_id,
                    fresh=fresh,
                    env=env,
                )
                session_id = result.session_id or session_id
                final_raw = result.text
                total_duration += result.duration_s or 0.0
                for event in result.tool_events:
                    event.turn_index = turn_index + 1
                for event in result.compaction_events:
                    event.turn_index = turn_index + 1
                tool_events.extend(result.tool_events)
                compaction_events.extend(result.compaction_events)
                turns.append(
                    TurnTrace(
                        index=turn_index + 1,
                        role="assistant",
                        kind="final_question",
                        chars=len(result.text),
                        tokens_est=estimate_tokens(result.text) if result.text else 0,
                        content_preview=preview(result.text),
                    )
                )
                try:
                    parsed = parse_agent_answer(final_raw)
                    parse_ok = True
                except Exception:
                    parsed = None
                    parse_ok = False
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

        if not session_id:
            session_id = f"error-{uuid.uuid4()}"

        duration_s = total_duration if total_duration > 0 else (time.monotonic() - start)
        contaminated = len(tool_events) > 0
        correct = score_one(
            scorer=task.scorer,
            gold=task.gold_answer,
            gold_aliases=task.gold_answer_aliases,
            answer=parsed.answer if parsed is not None else None,
        )

        return RunRecord(
            task_id=task.task_id,
            source_benchmark=task.source_benchmark,
            source_task=task.source_task,
            source_sample_id=task.source_sample_id,
            harness="claude_code",
            model=self.model,
            condition=self.condition,
            session_id=session_id,
            chunk_tokens=self.chunk_tokens,
            chunk_count=len(chunks),
            context_tokens_est=context_tokens_est,
            scorer=task.scorer,
            gold_answer=task.gold_answer,
            gold_answer_aliases=task.gold_answer_aliases,
            metadata=task.metadata,
            turns=turns,
            tool_events=tool_events,
            compaction_events=compaction_events,
            final_answer_raw=final_raw,
            final_answer_parsed=parsed,
            parse_ok=parse_ok,
            correct=correct,
            contaminated_by_tools=contaminated,
            error=error,
            duration_s=duration_s,
        )

    def _ask(
        self,
        *,
        prompt: str,
        cwd: Path,
        session_id: str,
        fresh: bool,
        env: dict[str, str],
    ) -> PromptResult:
        args = [
            CLAUDE_BIN,
            "-p",
            prompt,
            "--bare",
            "--model",
            self.model,
            "--effort",
            self.effort,
            "--output-format",
            "stream-json",
            "--verbose",
            "--tools",
            "",
            "--permission-mode",
            "default",
            "--disable-slash-commands",
            "--strict-mcp-config",
        ]
        if self.settings:
            args += ["--settings", self.settings]
        if fresh:
            args += ["--session-id", session_id]
        else:
            args += ["--resume", session_id]

        proc = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited {proc.returncode}: stderr_tail={proc.stderr[-500:]} stdout_tail={proc.stdout[-300:]}"
            )
        return parse_claude_stream_json(proc.stdout, condition=self.condition)


class CodexRunner:
    harness_name = "codex"

    def __init__(
        self,
        *,
        model: str,
        condition: CompactionMode,
        chunk_tokens: int,
        timeout_s: int,
        off_compact_limit: int,
        auto_compact_limit: int | None,
        reasoning_effort: str,
        verbosity: str,
    ) -> None:
        if shutil.which(CODEX_BIN) is None:
            raise RuntimeError("`codex` binary not found in PATH")
        self.model = model
        self.condition = condition
        self.chunk_tokens = chunk_tokens
        self.timeout_s = timeout_s
        self.off_compact_limit = off_compact_limit
        self.auto_compact_limit = auto_compact_limit
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity

    def run_task(self, task: TaskRow) -> RunRecord:
        chunks = chunk_text(task.context, self.chunk_tokens)
        context_tokens_est = sum(estimate_tokens(chunk) for chunk in chunks)
        session_id = ""
        turns: list[TurnTrace] = []
        tool_events: list[ToolEvent] = []
        compaction_events: list[CompactionEvent] = []
        final_raw: str | None = None
        parse_ok = False
        parsed: AgentAnswer | None = None
        error: str | None = None

        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="cbench-codex-") as tmpdir:
            fresh = True
            turn_index = 1
            try:
                for idx, chunk in enumerate(chunks, start=1):
                    prompt = build_chunk_prompt(idx, len(chunks), chunk)
                    turns.append(
                        TurnTrace(
                            index=turn_index,
                            role="user",
                            kind="context_chunk",
                            chunk_index=idx,
                            chunk_count=len(chunks),
                            chars=len(chunk),
                            tokens_est=estimate_tokens(chunk),
                            content_preview=preview(prompt),
                        )
                    )
                    result = self._ask(
                        prompt=prompt,
                        cwd=Path(tmpdir),
                        session_id=session_id,
                        fresh=fresh,
                    )
                    fresh = False
                    session_id = result.session_id or session_id
                    for event in result.tool_events:
                        event.turn_index = turn_index + 1
                    for event in result.compaction_events:
                        event.turn_index = turn_index + 1
                    tool_events.extend(result.tool_events)
                    compaction_events.extend(result.compaction_events)
                    turns.append(
                        TurnTrace(
                            index=turn_index + 1,
                            role="assistant",
                            kind="context_chunk",
                            chunk_index=idx,
                            chunk_count=len(chunks),
                            chars=len(result.text),
                            tokens_est=estimate_tokens(result.text) if result.text else 0,
                            content_preview=preview(result.text),
                        )
                    )
                    turn_index += 2

                final_prompt = build_final_prompt(task.question)
                turns.append(
                    TurnTrace(
                        index=turn_index,
                        role="user",
                        kind="final_question",
                        chars=len(final_prompt),
                        tokens_est=estimate_tokens(final_prompt),
                        content_preview=preview(final_prompt),
                    )
                )
                result = self._ask(
                    prompt=final_prompt,
                    cwd=Path(tmpdir),
                    session_id=session_id,
                    fresh=fresh,
                )
                session_id = result.session_id or session_id
                final_raw = result.text
                for event in result.tool_events:
                    event.turn_index = turn_index + 1
                for event in result.compaction_events:
                    event.turn_index = turn_index + 1
                tool_events.extend(result.tool_events)
                compaction_events.extend(result.compaction_events)
                turns.append(
                    TurnTrace(
                        index=turn_index + 1,
                        role="assistant",
                        kind="final_question",
                        chars=len(result.text),
                        tokens_est=estimate_tokens(result.text) if result.text else 0,
                        content_preview=preview(result.text),
                    )
                )
                try:
                    parsed = parse_agent_answer(final_raw)
                    parse_ok = True
                except Exception:
                    parsed = None
                    parse_ok = False
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

        if not session_id:
            session_id = f"error-{uuid.uuid4()}"

        if not compaction_events:
            compaction_events = _load_codex_session_compaction_events(
                session_id,
                condition=self.condition,
            )

        duration_s = time.monotonic() - start
        contaminated = len(tool_events) > 0
        correct = score_one(
            scorer=task.scorer,
            gold=task.gold_answer,
            gold_aliases=task.gold_answer_aliases,
            answer=parsed.answer if parsed is not None else None,
        )

        return RunRecord(
            task_id=task.task_id,
            source_benchmark=task.source_benchmark,
            source_task=task.source_task,
            source_sample_id=task.source_sample_id,
            harness="codex",
            model=self.model,
            condition=self.condition,
            session_id=session_id,
            chunk_tokens=self.chunk_tokens,
            chunk_count=len(chunks),
            context_tokens_est=context_tokens_est,
            scorer=task.scorer,
            gold_answer=task.gold_answer,
            gold_answer_aliases=task.gold_answer_aliases,
            metadata=task.metadata,
            turns=turns,
            tool_events=tool_events,
            compaction_events=compaction_events,
            final_answer_raw=final_raw,
            final_answer_parsed=parsed,
            parse_ok=parse_ok,
            correct=correct,
            contaminated_by_tools=contaminated,
            error=error,
            duration_s=duration_s,
        )

    def _ask(
        self,
        *,
        prompt: str,
        cwd: Path,
        session_id: str,
        fresh: bool,
    ) -> PromptResult:
        args = [
            CODEX_BIN,
            "-m",
            self.model,
            "-a",
            "never",
            "-s",
            "read-only",
            "-C",
            str(cwd),
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-c",
            f'model_verbosity="{self.verbosity}"',
            "-c",
            'web_search="disabled"',
        ]
        if self.condition == "off":
            args += ["-c", f"model_auto_compact_token_limit={self.off_compact_limit}"]
        elif self.auto_compact_limit is not None:
            args += ["-c", f"model_auto_compact_token_limit={self.auto_compact_limit}"]

        args += ["exec"]
        if fresh:
            args += ["--skip-git-repo-check", "--json", prompt]
        else:
            args += ["resume", "--skip-git-repo-check", "--json", session_id, prompt]

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"codex exited {proc.returncode}: stderr_tail={proc.stderr[-500:]} stdout_tail={proc.stdout[-300:]}"
            )
        return parse_codex_jsonl(proc.stdout, condition=self.condition)


def build_chunk_prompt(index: int, total: int, chunk: str) -> str:
    return (
        f"Context chunk {index}/{total}.\n"
        "Store this for later. Do not answer the final question yet.\n"
        "Do not use tools. Do not browse. Reply only with: OK\n\n"
        f"{chunk}"
    )


def build_final_prompt(question: str) -> str:
    return (
        "Now answer the following question using only the context chunks given earlier.\n"
        "Do not use tools. Return exactly one JSON object with one field: {\"answer\": \"...\"}.\n"
        "Do not include any extra text.\n\n"
        f"Question:\n{question}"
    )


def preview(text: str, limit: int = 160) -> str:
    squashed = " ".join(text.split())
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 1] + "…"


def _run_many(*, tasks: list[TaskRow], out_dir: Path, runner) -> list[Path]:
    written: list[Path] = []
    for task in tasks:
        record = runner.run_task(task)
        task_filename = task.task_id.replace("/", "_") + ".json"
        path = out_dir / runner.harness_name / runner.model / runner.condition / task_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2))
        written.append(path)
    return written
