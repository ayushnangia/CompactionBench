"""Secondary LLM-as-judge pass for deterministic scoring failures.

The main benchmark score remains deterministic. This module provides an
optional adjudication pass over saved run artifacts, using OpenRouter with
`qwen/qwq-32b` to judge only borderline-looking failures.
"""

from __future__ import annotations

import csv
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from dotenv import load_dotenv
from openrouter import OpenRouter
from pydantic import BaseModel, ConfigDict, Field

from .schema import RunRecord
from .score import iter_run_records

JUDGE_MODEL = "qwen/qwq-32b"
JUDGE_TEMPERATURE = 0
JUDGE_MAX_TOKENS = 300


class JudgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equivalent: bool
    reason: str = Field(..., min_length=1, max_length=2000)


@dataclass
class JudgeResult:
    decision: JudgeDecision
    raw_text: str


@dataclass
class JudgedRow:
    task_id: str
    source_benchmark: str
    source_task: str
    harness: str
    model: str
    condition: str
    gold_answer: str
    agent_answer: str
    deterministic_correct: bool
    judge_applied: bool
    judge_equivalent: bool | None
    final_correct_with_judge: bool
    contaminated_by_tools: bool
    parse_ok: bool
    judge_reason: str | None
    error: str | None


def judge_runs(runs_root: Path, out_dir: Path, *, max_workers: int = 4) -> list[JudgedRow]:
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions_dir = out_dir / "judge_decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)

    records: list[tuple[Path, RunRecord]] = [
        (run_path, RunRecord.model_validate_json(run_path.read_text()))
        for run_path in iter_run_records(runs_root)
    ]
    rows: list[JudgedRow] = []
    rows_lock = Lock()

    def process(pair: tuple[Path, RunRecord]) -> JudgedRow:
        run_path, rec = pair
        agent_answer = rec.final_answer_parsed.answer if rec.final_answer_parsed else None
        deterministic_correct = bool(rec.correct)

        judge_applied = False
        judge_equivalent: bool | None = None
        judge_reason: str | None = None

        if _should_judge(rec, deterministic_correct, agent_answer):
            judge_applied = True
            try:
                result = judge_one(
                    client=_make_client(),
                    source_task=rec.source_task,
                    gold_answer=rec.gold_answer,
                    agent_answer=agent_answer or "",
                )
                judge_equivalent = result.decision.equivalent
                judge_reason = result.decision.reason
                decision_path = decisions_dir / f"{rec.task_id}.json"
                decision_path.write_text(
                    json.dumps(
                        {
                            "task_id": rec.task_id,
                            "run_path": str(run_path),
                            "source_task": rec.source_task,
                            "gold_answer": rec.gold_answer,
                            "agent_answer": agent_answer,
                            "decision": result.decision.model_dump(),
                            "raw_text": result.raw_text,
                        },
                        indent=2,
                    )
                )
            except Exception as e:
                judge_equivalent = None
                judge_reason = f"judge_error: {type(e).__name__}: {e}"

        final_correct = deterministic_correct or bool(judge_equivalent)
        return JudgedRow(
            task_id=rec.task_id,
            source_benchmark=rec.source_benchmark,
            source_task=rec.source_task,
            harness=rec.harness,
            model=rec.model,
            condition=rec.condition,
            gold_answer=rec.gold_answer,
            agent_answer=agent_answer or "",
            deterministic_correct=deterministic_correct,
            judge_applied=judge_applied,
            judge_equivalent=judge_equivalent,
            final_correct_with_judge=final_correct,
            contaminated_by_tools=rec.contaminated_by_tools,
            parse_ok=rec.parse_ok,
            judge_reason=judge_reason,
            error=rec.error,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(process, pair) for pair in records]
        for future in as_completed(futures):
            row = future.result()
            with rows_lock:
                rows.append(row)

    rows.sort(key=lambda r: (r.harness, r.model, r.condition, r.source_task, r.task_id))
    _write_rows_csv(rows, out_dir / "judge_rows.csv")
    summary = _aggregate(rows)
    (out_dir / "judge_summary.json").write_text(json.dumps(summary, indent=2))
    return rows


def judge_one(*, client: OpenRouter, source_task: str, gold_answer: str, agent_answer: str) -> JudgeResult:
    system_prompt = (
        "You are a strict grading assistant for long-context QA. "
        "Decide whether the candidate answer is semantically equivalent to the gold answer. "
        "Be conservative: do not award credit for clearly different facts. "
        "Ignore only superficial formatting differences like punctuation, articles, sentence wrappers, or digit-vs-word forms when the answer content is the same. "
        "Return a tiny JSON object only."
    )
    user_prompt = (
        f"Task type: {source_task}\n"
        f"Gold answer: {gold_answer}\n"
        f"Candidate answer: {agent_answer}\n\n"
        "Return exactly this JSON shape and nothing else:\n"
        '{"equivalent": true, "reason": "brief explanation"}'
    )

    resp = client.chat.send(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=JUDGE_TEMPERATURE,
        max_tokens=JUDGE_MAX_TOKENS,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    decision = _parse_judge_json(content or "")
    return JudgeResult(decision=decision, raw_text=content or "")


def _parse_judge_json(text: str) -> JudgeDecision:
    try:
        end = text.rfind("}")
        if end == -1:
            raise ValueError("Judge returned no JSON object")
        depth = 0
        start = -1
        for i in range(end, -1, -1):
            ch = text[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start == -1:
            raise ValueError("Judge returned malformed JSON")
        return JudgeDecision.model_validate(json.loads(text[start : end + 1]))
    except Exception:
        lowered = text.lower()
        match = re.search(r'"equivalent"\s*:\s*(true|false)', lowered)
        if not match:
            raise
        equivalent = match.group(1) == 'true'
        return JudgeDecision(
            equivalent=equivalent,
            reason=(text.strip()[:1800] or 'fallback parse from raw judge output'),
        )


def _should_judge(rec: RunRecord, deterministic_correct: bool, agent_answer: str | None) -> bool:
    if deterministic_correct:
        return False
    if not rec.parse_ok:
        return False
    if rec.contaminated_by_tools:
        return False
    if not agent_answer or not agent_answer.strip():
        return False
    return True


def _make_client() -> OpenRouter:
    load_dotenv('.env')
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise RuntimeError('OPENROUTER_API_KEY missing; expected in .env or environment')
    return OpenRouter(api_key=api_key)


def _write_rows_csv(rows: list[JudgedRow], path: Path) -> None:
    cols = [
        'task_id',
        'source_benchmark',
        'source_task',
        'harness',
        'model',
        'condition',
        'gold_answer',
        'agent_answer',
        'deterministic_correct',
        'judge_applied',
        'judge_equivalent',
        'final_correct_with_judge',
        'contaminated_by_tools',
        'parse_ok',
        'judge_reason',
        'error',
    ]
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({c: getattr(row, c) for c in cols})


def _aggregate(rows: list[JudgedRow]) -> dict[str, Any]:
    total = len(rows)
    judged = [r for r in rows if r.judge_applied]
    deterministic_correct = sum(1 for r in rows if r.deterministic_correct)
    final_correct = sum(1 for r in rows if r.final_correct_with_judge)
    overturned = sum(1 for r in rows if (not r.deterministic_correct and r.judge_equivalent))
    return {
        'n_total': total,
        'n_judged': len(judged),
        'deterministic_correct': deterministic_correct,
        'final_correct_with_judge': final_correct,
        'deterministic_accuracy': deterministic_correct / total if total else 0.0,
        'judge_adjusted_accuracy': final_correct / total if total else 0.0,
        'judge_overturns': overturned,
    }
