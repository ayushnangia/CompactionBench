#!/usr/bin/env python3
"""Prepare 125 real agent-memory tasks from SWE-chat + LongMemEval.

This panel is for a 250-run paired experiment:
- 50 SWE-chat coding-session tasks x {full_context, grep_file}
- 75 LongMemEval-V2 rendered web-agent tasks x {full_context, grep_file}

No local synthetic generator tasks are included.

Important: LME rows use a compact text rendering of raw browser trajectories;
this is not a claim of fully lossless raw trajectory inclusion. SWE-chat rows use
real transcript prefixes without filler.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.core.chunking import estimate_tokens
from compactionbench.datasets.lme_loader import load_lme_questions, prepare_lme_tasks
from compactionbench.core.schema import Scorer, TaskRow, write_task_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/benchmarks/confirmation/swe_lme_real_125.jsonl")
    p.add_argument("--report-dir", default="artifacts/analysis/swe_lme_real_125")
    p.add_argument("--swe-count", type=int, default=50)
    p.add_argument("--lme-count", type=int, default=75)
    p.add_argument("--swe-min-context-tokens", type=int, default=8_000)
    p.add_argument("--swe-max-context-tokens", type=int, default=180_000)
    p.add_argument("--swe-snapshot", default="auto")
    p.add_argument("--lme-snapshot", default="auto")
    p.add_argument("--lme-max-trajectories", type=int, default=120)
    p.add_argument("--lme-max-context-tokens", type=int, default=185_000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: list[TaskRow] = []
    rows.extend(
        build_swe_chat(
            count=args.swe_count,
            snapshot_arg=args.swe_snapshot,
            min_context_tokens=args.swe_min_context_tokens,
            max_context_tokens=args.swe_max_context_tokens,
        )
    )
    rows.extend(
        build_lme(
            count=args.lme_count,
            snapshot_arg=args.lme_snapshot,
            max_trajectories=args.lme_max_trajectories,
            max_context_tokens=args.lme_max_context_tokens,
        )
    )

    expected = args.swe_count + args.lme_count
    if len(rows) != expected:
        raise RuntimeError(f"Expected {expected} rows, got {len(rows)}")

    write_task_rows(rows, out)
    manifest = [row_to_manifest(row, out) for row in rows]
    write_manifest(report_dir / "manifest.csv", manifest)
    write_report(report_dir / "report.md", rows, manifest, out)

    print(f"Wrote {len(rows)} rows to {out}")
    print(f"Wrote report to {report_dir / 'report.md'}")
    return 0


def build_swe_chat(*, count: int, snapshot_arg: str, min_context_tokens: int, max_context_tokens: int) -> list[TaskRow]:
    snapshot = resolve_swe_snapshot(snapshot_arg)
    if snapshot is None:
        raise RuntimeError("SWE-chat local HF cache not found")
    transcripts = sorted((snapshot / "transcripts").glob("*.jsonl"), key=lambda p: p.stat().st_size, reverse=True)
    rows: list[TaskRow] = []

    for path in transcripts:
        if len(rows) >= count:
            break
        turns = extract_swe_turns(path)
        if len(turns) < 6:
            continue
        candidates = []
        for idx, turn in enumerate(turns):
            if turn.get("role") != "user":
                continue
            if idx + 1 >= len(turns) or turns[idx + 1].get("role") != "assistant":
                continue
            question = str(turn.get("content") or "").strip()
            gold = str(turns[idx + 1].get("content") or "").strip()
            if len(question) < 20 or len(gold) < 80:
                continue
            ctx = render_context(turns[:idx]).strip()
            if not ctx:
                continue
            tok = estimate_tokens(ctx)
            if tok < min_context_tokens or tok > max_context_tokens:
                continue
            candidates.append((idx, ctx, question, gold, tok))
        if not candidates:
            continue

        selected: list[tuple[int, str, str, str, int]] = []
        for frac in (0.30, 0.50, 0.70, 0.90):
            target_idx = int(len(turns) * frac)
            remaining = [c for c in candidates if all(abs(c[0] - s[0]) >= 4 for s in selected)]
            if not remaining:
                break
            selected.append(min(remaining, key=lambda c: abs(c[0] - target_idx)))

        sid = path.stem
        for idx, ctx, question, gold, tok in selected:
            if len(rows) >= count:
                break
            row = TaskRow(
                task_id=f"swe-chat-{sanitize(sid)}-turn{idx:04d}",
                source_benchmark="swe_chat",
                source_task="swe_chat",
                source_sample_id=f"{sid}-turn{idx}",
                context=ctx,
                question=question[:20_000],
                gold_answer=gold[:4_000],
                gold_answer_aliases=[],
                scorer="substring_ci",
                metadata={
                    "panel": "swe_lme_real_125",
                    "panel_family": "swe_chat",
                    "session_id": sid,
                    "transcript_path": str(path),
                    "turn_index": idx,
                    "total_turns": len(turns),
                    "context_tokens_est": tok,
                    "gold_truncated": len(gold) > 4_000,
                    "scoring_note": "Use semantic/judge scoring for this family; substring is only a rough fallback.",
                },
            )
            rows.append(row)

    if len(rows) < count:
        raise RuntimeError(f"Only prepared {len(rows)} SWE-chat rows, need {count}")
    return rows


def build_lme(*, count: int, snapshot_arg: str, max_trajectories: int, max_context_tokens: int) -> list[TaskRow]:
    snapshot = resolve_lme_snapshot(snapshot_arg)
    if snapshot is None:
        raise RuntimeError("LongMemEval-V2 local HF cache not found")
    haystack = snapshot / "haystacks" / "lme_v2_medium.json"
    trajectories = snapshot / "trajectories.jsonl"
    questions = snapshot / "questions.jsonl"
    for path in (haystack, trajectories, questions):
        if not path.exists():
            raise FileNotFoundError(path)

    qtypes = sorted({str(q.get("question_type") or "unknown") for q in load_lme_questions(questions)})
    # Prepare a balanced-ish pool, then trim to requested count.
    per_type = max(1, (count + len(qtypes) - 1) // len(qtypes))
    rows = prepare_lme_tasks(
        haystack,
        trajectories,
        questions,
        count=per_type * len(qtypes),
        target_tokens=1,
        question_types=set(qtypes),
        count_per_type=per_type,
        max_trajectories=max_trajectories,
    )
    kept: list[TaskRow] = []
    for row in rows:
        tok = estimate_tokens(row.context)
        if tok > max_context_tokens:
            continue
        metadata = dict(row.metadata)
        metadata.update(
            {
                "panel": "swe_lme_real_125",
                "panel_family": "lme_rendered",
                "context_tokens_est": tok,
                "rendering_note": "Rendered/clipped browser trajectories, not lossless raw trajectory JSON.",
            }
        )
        kept.append(row.model_copy(update={"metadata": metadata}))
        if len(kept) >= count:
            break
    if len(kept) < count:
        raise RuntimeError(f"Only prepared {len(kept)} LME rows under token cap, need {count}")
    return kept


def extract_swe_turns(path: Path) -> list[dict[str, str]]:
    """Extract user/assistant text turns from SWE-chat cached transcript formats."""
    turns: list[dict[str, str]] = []
    try:
        obj = json.loads(path.read_text())
        if isinstance(obj, dict) and isinstance(obj.get("messages"), list):
            for msg in obj["messages"]:
                if not isinstance(msg, dict):
                    continue
                info = msg.get("info") if isinstance(msg.get("info"), dict) else {}
                role = str(info.get("role") or msg.get("role") or "").lower()
                if role in {"assistant", "agent"}:
                    role = "assistant"
                if role not in {"user", "assistant"}:
                    continue
                text_parts: list[str] = []
                for part in msg.get("parts") or []:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(str(part.get("text") or ""))
                content = "\n".join(text_parts).strip()
                if len(content) >= 10:
                    turns.append({"role": role, "content": content})
            return turns
    except Exception:
        pass

    # Fallback for JSONL event transcript shape.
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
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


def render_context(turns: list[dict[str, str]]) -> str:
    return "\n\n".join(f"[{turn['role'].upper()}]: {turn['content']}" for turn in turns)


def resolve_swe_snapshot(raw: str) -> Path | None:
    if raw != "auto":
        return Path(raw)
    root = Path.home() / ".cache/huggingface/hub/datasets--SALT-NLP--SWE-chat/snapshots"
    if not root.exists():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def resolve_lme_snapshot(raw: str) -> Path | None:
    if raw != "auto":
        return Path(raw)
    root = Path.home() / ".cache/huggingface/hub/datasets--xiaowu0162--longmemeval-v2/snapshots"
    if not root.exists():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def row_to_manifest(row: TaskRow, panel_path: Path) -> dict[str, str]:
    return {
        "panel_path": str(panel_path),
        "task_id": row.task_id,
        "benchmark": row.source_benchmark,
        "panel_family": str(row.metadata.get("panel_family", "")),
        "source_task": row.source_task,
        "question_type": str(row.metadata.get("question_type") or row.source_task),
        "scorer": row.scorer,
        "context_tokens_est": str(estimate_tokens(row.context)),
        "gold_answer_preview": compact(row.gold_answer, 140),
        "question_preview": compact(row.question, 180),
    }


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[TaskRow], manifest: list[dict[str, str]], panel_path: Path) -> None:
    by_bench = Counter(row.source_benchmark for row in rows)
    by_family = Counter(str(row.metadata.get("panel_family")) for row in rows)
    by_lme_qtype = Counter(str(row.metadata.get("question_type")) for row in rows if row.source_benchmark == "lme")
    toks = [estimate_tokens(row.context) for row in rows]
    lines = ["# SWE-chat + LongMemEval real-agent panel", ""]
    lines.append(f"Task file: `{panel_path}`")
    lines.append("")
    lines.append("This real-only panel is intended for 125 tasks x 2 arms = 250 Codex runs.")
    lines.append("")
    lines.append("## Composition")
    lines.append("")
    lines.append(f"- total tasks: `{len(rows)}`")
    lines.append(f"- by benchmark: `{dict(by_bench)}`")
    lines.append(f"- by family: `{dict(by_family)}`")
    lines.append(f"- LME question types: `{dict(by_lme_qtype)}`")
    lines.append(f"- context token estimate: min `{min(toks)}`, max `{max(toks)}`, avg `{sum(toks)/len(toks):.0f}`")
    lines.append("")
    lines.append("## Important scoring note")
    lines.append("")
    lines.append("SWE-chat gold answers are full assistant replies, so deterministic substring scoring is only a rough fallback. Use semantic/judge scoring for the final readout.")
    lines.append("LME uses rendered/clipped browser trajectory text, so label it as rendered context rather than raw lossless trajectory JSON.")
    lines.append("")
    lines.append("## Manifest preview")
    lines.append("")
    lines.append("| Benchmark | Family | Type | Tokens | Task id |")
    lines.append("|---|---|---|---:|---|")
    for row in manifest[:100]:
        lines.append(f"| `{row['benchmark']}` | `{row['panel_family']}` | `{row['question_type']}` | {row['context_tokens_est']} | `{row['task_id']}` |")
    if len(manifest) > 100:
        lines.append(f"| ... | ... | ... | ... | `{len(manifest)-100}` more rows in manifest.csv |")
    path.write_text("\n".join(lines) + "\n")


def sanitize(raw: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-")[:80]


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
