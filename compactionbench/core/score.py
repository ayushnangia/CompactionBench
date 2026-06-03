"""Scoring and summary reporting for direct run artifacts."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .schema import RunRecord, Scorer


@dataclass
class ScoredRun:
    task_id: str
    source_benchmark: str
    source_task: str
    harness: str
    model: str
    condition: str
    chunk_tokens: int
    chunk_count: int
    context_tokens_est: int
    scorer: str
    gold_answer: str
    agent_answer: str | None
    score_value: float
    correct: bool
    parse_ok: bool
    contaminated_by_tools: bool
    compaction_event_count: int
    tool_event_count: int
    error: str | None
    duration_s: float | None
    metadata_json: str


def _trim(text: str) -> str:
    return text.strip().strip('"').strip("'").strip()


def _normalize_oolong_text(text: str) -> str:
    s = _trim(text).replace("*", "")
    s = re.sub(r"\\boxed\{(?:\\text\{)?([^}]*)\}?\}", r"\1", s)
    if ":" in s:
        prefix, rest = s.split(":", 1)
        if prefix.strip().lower() in {"label", "answer", "user", "date"}:
            s = rest.strip()
    s = s.strip().strip("[]")
    return _trim(s)


def _normalize_csv_parts(value: str) -> tuple[str, ...]:
    parts = [_normalize_oolong_text(part).lower() for part in _trim(value).split(",") if part.strip()]
    return tuple(sorted(parts))


def _exact(answer: str, gold: str) -> float:
    return float(_trim(answer) == _trim(gold))


def _exact_ci(answer: str, gold: str) -> float:
    return float(_trim(answer).lower() == _trim(gold).lower())


def _substring_ci(answer: str, gold: str) -> float:
    return float(_trim(gold).lower() in answer.lower())


_MCQ_LETTER_RE = re.compile(r"\b([ABCD])\b")


def _multiple_choice(answer: str, gold: str) -> float:
    match = _MCQ_LETTER_RE.search(answer)
    if not match:
        return 0.0
    return float(match.group(1) == _trim(gold).upper())


def _csv_set_ci(answer: str, gold: str) -> float:
    return float(_normalize_csv_parts(answer) == _normalize_csv_parts(gold))


_INT_RE = re.compile(r"-?\d+")


def _parse_int_like(value: str) -> int | None:
    text = _normalize_oolong_text(value)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    match = _INT_RE.search(text)
    if not match:
        return None
    return int(match.group(0))


def _numeric_075(answer: str, gold: str) -> float:
    pred = _parse_int_like(answer)
    target = _parse_int_like(gold)
    if pred is None or target is None:
        return 0.0
    return 0.75 ** abs(target - pred)


def _csv_overlap_ci(answer: str, gold: str) -> float:
    gold_parts = {_normalize_oolong_text(part).lower() for part in _trim(gold).split(",") if part.strip()}
    pred_parts = {_normalize_oolong_text(part).lower() for part in _trim(answer).split(",") if part.strip()}
    if not gold_parts:
        return 0.0
    return len(gold_parts & pred_parts) / len(gold_parts)


def _oolong_text_ci(answer: str, gold: str) -> float:
    return float(_normalize_oolong_text(answer).lower() == _normalize_oolong_text(gold).lower())


def _normalize_comparison(value: str) -> str:
    text = _normalize_oolong_text(value).lower()
    text = text.replace("the same frequency as", "same frequency")
    text = text.replace("same frequency as", "same frequency")
    text = text.replace("more common than", "more common")
    text = text.replace("less common than", "less common")
    if "same frequency" in text:
        return "same frequency"
    if "more common" in text:
        return "more common"
    if "less common" in text:
        return "less common"
    return text


def _oolong_comparison_ci(answer: str, gold: str) -> float:
    return float(_normalize_comparison(answer) == _normalize_comparison(gold))


_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_DOT_RE = re.compile(r"datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)")


def _canonical_date(value: str) -> str | None:
    text = _normalize_oolong_text(value)
    if match := _DATE_ISO_RE.search(text):
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    if match := _DATE_DOT_RE.search(text):
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    cleaned = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)
    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


_MONTH_YEAR_RE = re.compile(r"([A-Za-z]+)\s+(\d{4})")


def _canonical_month_year(value: str) -> str | None:
    text = _normalize_oolong_text(value)
    if match := _MONTH_YEAR_RE.search(text):
        month_name, year = match.groups()
        for fmt in ("%B %Y", "%b %Y"):
            try:
                return datetime.strptime(f"{month_name} {year}", fmt).strftime("%B %Y")
            except ValueError:
                pass
    return None


def _date_ci(answer: str, gold: str) -> float:
    pred = _canonical_date(answer)
    target = _canonical_date(gold)
    if pred is None or target is None:
        return 0.0
    return float(pred == target)


def _month_year_ci(answer: str, gold: str) -> float:
    pred = _canonical_month_year(answer)
    target = _canonical_month_year(gold)
    if pred is None or target is None:
        return 0.0
    return float(pred == target)


SCORER_FUNCS: dict[str, Callable[[str, str], float]] = {
    "exact": _exact,
    "exact_ci": _exact_ci,
    "substring_ci": _substring_ci,
    "multiple_choice": _multiple_choice,
    "csv_set_ci": _csv_set_ci,
    "numeric_075": _numeric_075,
    "csv_overlap_ci": _csv_overlap_ci,
    "oolong_text_ci": _oolong_text_ci,
    "oolong_comparison_ci": _oolong_comparison_ci,
    "date_ci": _date_ci,
    "month_year_ci": _month_year_ci,
}


def score_value_one(*, scorer: Scorer, gold: str, gold_aliases: list[str], answer: str | None) -> float:
    if answer is None:
        return 0.0
    func = SCORER_FUNCS[scorer]
    return max(func(answer, candidate) for candidate in (gold, *gold_aliases))


def score_one(*, scorer: Scorer, gold: str, gold_aliases: list[str], answer: str | None) -> bool:
    return score_value_one(scorer=scorer, gold=gold, gold_aliases=gold_aliases, answer=answer) >= 1.0


def iter_run_records(runs_root: Path) -> Iterable[Path]:
    yield from sorted(runs_root.rglob("*.json"))


def score_runs(runs_root: Path, out_dir: Path) -> list[ScoredRun]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[ScoredRun] = []

    for run_path in iter_run_records(runs_root):
        rec = RunRecord.model_validate_json(run_path.read_text())
        agent_answer = rec.final_answer_parsed.answer if rec.final_answer_parsed else None
        score_value = score_value_one(
            scorer=rec.scorer,
            gold=rec.gold_answer,
            gold_aliases=rec.gold_answer_aliases,
            answer=agent_answer,
        )
        rows.append(
            ScoredRun(
                task_id=rec.task_id,
                source_benchmark=rec.source_benchmark,
                source_task=rec.source_task,
                harness=rec.harness,
                model=rec.model,
                condition=rec.condition,
                chunk_tokens=rec.chunk_tokens,
                chunk_count=rec.chunk_count,
                context_tokens_est=rec.context_tokens_est,
                scorer=rec.scorer,
                gold_answer=rec.gold_answer,
                agent_answer=agent_answer,
                score_value=score_value,
                correct=score_value >= 1.0,
                parse_ok=rec.parse_ok,
                contaminated_by_tools=rec.contaminated_by_tools,
                compaction_event_count=len(rec.compaction_events),
                tool_event_count=len(rec.tool_events),
                error=rec.error,
                duration_s=rec.duration_s,
                metadata_json=json.dumps(rec.metadata, sort_keys=True),
            )
        )

    _write_rows_csv(rows, out_dir / "rows.csv")
    summary = _aggregate(rows)
    _write_summary_csv(summary, out_dir / "summary.csv")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return rows


def format_report(summary: dict) -> str:
    lines = ["CompactionBench direct-run summary", ""]
    for key, stats in summary.get("by_harness_model_condition", {}).items():
        lines.append(
            f"{key}: total={stats['n_total']} clean={stats['n_clean']} acc={stats['accuracy']:.3f} "
            f"avg_score={stats['avg_score']:.3f} parse={stats['parse_ok_rate']:.3f} "
            f"contaminated={stats['contaminated_rate']:.3f} compactions={stats['compaction_events']}"
        )
    return "\n".join(lines)


def _write_rows_csv(rows: list[ScoredRun], path: Path) -> None:
    if not rows:
        path.write_text("")
        return

    cols = [
        "task_id",
        "source_benchmark",
        "source_task",
        "harness",
        "model",
        "condition",
        "chunk_tokens",
        "chunk_count",
        "context_tokens_est",
        "scorer",
        "gold_answer",
        "agent_answer",
        "score_value",
        "correct",
        "parse_ok",
        "contaminated_by_tools",
        "compaction_event_count",
        "tool_event_count",
        "error",
        "duration_s",
        "metadata_json",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: getattr(row, col) for col in cols})


def _aggregate(rows: list[ScoredRun]) -> dict:
    by_hmc: dict[tuple[str, str, str], list[ScoredRun]] = defaultdict(list)
    by_hbmc: dict[tuple[str, str, str, str], list[ScoredRun]] = defaultdict(list)

    for row in rows:
        by_hmc[(row.harness, row.model, row.condition)].append(row)
        by_hbmc[(row.harness, row.model, row.condition, row.source_benchmark)].append(row)

    def stats(rs: list[ScoredRun]) -> dict:
        n_total = len(rs)
        clean = [row for row in rs if not row.contaminated_by_tools]
        n_clean = len(clean)
        correct_clean = sum(1 for row in clean if row.correct)
        correct_all = sum(1 for row in rs if row.correct)
        avg_score_clean = sum(row.score_value for row in clean) / n_clean if n_clean else 0.0
        avg_score_all = sum(row.score_value for row in rs) / n_total if n_total else 0.0
        parse_ok = sum(1 for row in rs if row.parse_ok)
        contaminated = sum(1 for row in rs if row.contaminated_by_tools)
        errors = sum(1 for row in rs if row.error)
        compactions = sum(row.compaction_event_count for row in rs)
        durs = [row.duration_s for row in rs if row.duration_s is not None]
        return {
            "n_total": n_total,
            "n_clean": n_clean,
            "correct_clean": correct_clean,
            "correct_all": correct_all,
            "accuracy": correct_clean / n_clean if n_clean else 0.0,
            "accuracy_all": correct_all / n_total if n_total else 0.0,
            "avg_score": avg_score_clean,
            "avg_score_all": avg_score_all,
            "parse_ok": parse_ok,
            "parse_ok_rate": parse_ok / n_total if n_total else 0.0,
            "contaminated": contaminated,
            "contaminated_rate": contaminated / n_total if n_total else 0.0,
            "errors": errors,
            "compaction_events": compactions,
            "avg_duration_s": sum(durs) / len(durs) if durs else None,
        }

    return {
        "by_harness_model_condition": {
            f"{h}:{m}:{c}": stats(rs)
            for (h, m, c), rs in sorted(by_hmc.items())
        },
        "by_harness_model_condition_benchmark": {
            f"{h}:{m}:{c}:{b}": stats(rs)
            for (h, m, c, b), rs in sorted(by_hbmc.items())
        },
    }


def _write_summary_csv(summary: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "key",
                "scope",
                "n_total",
                "n_clean",
                "correct_clean",
                "correct_all",
                "accuracy",
                "accuracy_all",
                "avg_score",
                "avg_score_all",
                "parse_ok_rate",
                "contaminated_rate",
                "errors",
                "compaction_events",
                "avg_duration_s",
            ]
        )
        for scope in ("by_harness_model_condition", "by_harness_model_condition_benchmark"):
            for key, stats in sorted(summary.get(scope, {}).items()):
                writer.writerow(
                    [
                        key,
                        scope,
                        stats["n_total"],
                        stats["n_clean"],
                        stats["correct_clean"],
                        stats["correct_all"],
                        stats["accuracy"],
                        stats["accuracy_all"],
                        stats["avg_score"],
                        stats["avg_score_all"],
                        stats["parse_ok_rate"],
                        stats["contaminated_rate"],
                        stats["errors"],
                        stats["compaction_events"],
                        stats["avg_duration_s"],
                    ]
                )
