"""Structured-output parser tests for Claude Code and Codex."""

from __future__ import annotations

import json
from pathlib import Path

from compactionbench.runners.run import (
    _load_codex_session_compaction_events,
    parse_claude_stream_json,
    parse_codex_jsonl,
)


def test_parse_claude_stream_json_extracts_text_tools_and_compaction() -> None:
    raw = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "session_id": "s1",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                            {"type": "text", "text": "intermediate"},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "session_id": "s1",
                    "compact_metadata": {"pre_tokens": 1000, "post_tokens": 300},
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "session_id": "s1",
                    "result": '{"answer": "42"}',
                    "duration_ms": 2500,
                    "usage": {
                        "server_tool_use": {
                            "web_search_requests": 1,
                            "web_fetch_requests": 2
                        }
                    }
                }
            ),
        ]
    )
    got = parse_claude_stream_json(raw, condition="auto")
    assert got.session_id == "s1"
    assert got.text == '{"answer": "42"}'
    assert len(got.tool_events) == 3
    assert got.tool_events[0].tool_name == "Bash"
    assert {e.tool_name for e in got.tool_events[1:]} == {"web_search", "web_fetch"}
    assert len(got.compaction_events) == 1
    assert got.compaction_events[0].before_tokens == 1000
    assert got.duration_s == 2.5


def test_parse_codex_jsonl_extracts_text_tools_and_compaction() -> None:
    raw = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "event_msg", "payload": {"type": "context_compacted"}}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": "ls"},
                }
            ),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": '{"answer": "OK"}'},
                }
            ),
        ]
    )
    got = parse_codex_jsonl(raw, condition="auto")
    assert got.session_id == "t1"
    assert got.text == '{"answer": "OK"}'
    assert len(got.compaction_events) == 1
    assert len(got.tool_events) == 1
    assert got.tool_events[0].tool_name == "command_execution"


def test_load_codex_session_compaction_events_prefers_compacted_records(tmp_path, monkeypatch) -> None:
    sessions_root = tmp_path / '.codex' / 'sessions' / '2026' / '04' / '22'
    sessions_root.mkdir(parents=True)
    session_id = 'abc123'
    session_file = sessions_root / f'rollout-2026-04-22T00-00-00-{session_id}.jsonl'
    session_file.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "payload": {"id": session_id}}),
                json.dumps({"type": "event_msg", "payload": {"type": "context_compacted"}}),
                json.dumps({"type": "compacted", "payload": {"replacement_history": []}}),
            ]
        )
    )
    monkeypatch.setattr('compactionbench.runners.run.CODEX_SESSIONS_DIR', tmp_path / '.codex' / 'sessions')
    got = _load_codex_session_compaction_events(session_id, condition='auto')
    assert len(got) == 1
    assert got[0].raw['type'] == 'compacted'
