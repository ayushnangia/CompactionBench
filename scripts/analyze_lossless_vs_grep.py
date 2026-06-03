#!/usr/bin/env python3
"""Analyze context-access strategy runs.

Supports the original full-context vs grep-file comparison and newer arms such
as paged_context.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compactionbench.schema import RunRecord
from compactionbench.score import iter_run_records, score_value_one


def relaxed_score_value(*, scorer: str, gold: str, gold_aliases: list[str], answer: str | None) -> float:
    """More human-aligned fallback for short-answer artifacts.

    The benchmark still reports strict score. This relaxed score is used for
    diagnosis so formatting differences like `the bathroom` vs `bathroom` and
    `\\boxed{G}` vs `G` do not hide semantically correct short answers.
    """

    strict = score_value_one(scorer=scorer, gold=gold, gold_aliases=gold_aliases, answer=answer)
    if strict >= 1.0 or answer is None:
        return strict
    return max(_relaxed_one(answer, candidate) for candidate in (gold, *gold_aliases))


def _relaxed_one(answer: str, gold: str) -> float:
    gold_clean = _clean_short_answer(gold)
    answer_clean = _clean_short_answer(answer)
    if not gold_clean or not answer_clean:
        return 0.0

    # Multiple-choice letters in LME often appear as \\boxed{G}. The original
    # multiple-choice scorer only covers A-D, so diagnose A-H here.
    if re.fullmatch(r"[a-h]", gold_clean):
        if re.fullmatch(r"[a-h]", answer_clean):
            return float(answer_clean == gold_clean)
        match = re.search(r"\b([a-h])\b", answer_clean)
        return float(bool(match and match.group(1) == gold_clean))

    if gold_clean in {"unknown", "not mentioned", "not enough information"} and _is_unknown_or_no_record_answer(answer_clean):
        return 1.0

    if gold_clean == answer_clean:
        return 1.0
    if _drop_articles(gold_clean) == _drop_articles(answer_clean):
        return 1.0
    if len(gold_clean) >= 3 and gold_clean in answer_clean:
        return 1.0
    return 0.0


def _is_unknown_or_no_record_answer(value: str) -> bool:
    return bool(
        re.search(r"\b(unknown|not enough information|cannot be determined|can not be determined|can't be determined)\b", value)
        or re.search(r"\b(no|not)\b.*\b(record|entry|mention|mentioned|specified|given|present|available|found|contain|contains|recorded)\b", value)
        or re.search(r"\bdoes not\b.*\b(contain|mention|include)\b", value)
    )


def _clean_short_answer(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\\boxed\{(?:\\text\{)?([^{}]*)\}?\}", r"\1", text)
    text = re.sub(r"^\s*(answer|label|user|date)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.lower()
    text = text.replace("%", " percent ")
    text = re.sub(r"[^a-z0-9,.-]+", " ", text)
    return " ".join(text.split()).strip(" .,'\"")


def _drop_articles(value: str) -> str:
    return " ".join(tok for tok in value.split() if tok not in {"a", "an", "the"})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--runs-root", required=True, action="append", help="Run-record root. Can be supplied multiple times to merge old baselines with new arms.")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--title", default="Context access strategies")
    p.add_argument("--baseline-arm", default="full_context")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    runs_roots = [Path(p) for p in args.runs_root]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for runs_root in runs_roots:
        for path in iter_run_records(runs_root):
            rec = RunRecord.model_validate_json(path.read_text())
            arm = str(rec.metadata.get("arm") or "unknown")
            original_task_id = str(rec.metadata.get("original_task_id") or rec.task_id)
            answer = rec.final_answer_parsed.answer if rec.final_answer_parsed else None
            memory_meta = rec.metadata.get("hierarchical_memory") or rec.metadata.get("virtual_context") or rec.metadata.get("bidirectional_proof") or {}
            if isinstance(memory_meta, dict) and rec.metadata.get("bidirectional_proof"):
                evidence_tokens = sum(
                    int(memory_meta.get(key) or 0)
                    for key in (
                        "proof_json_tokens_est",
                        "proof_audit_tokens_est",
                        "proof_packet_repaired_tokens_est",
                        "proof_repair_audit_tokens_est",
                        "proof_md_tokens_est",
                    )
                )
            else:
                evidence_tokens = int(
                    memory_meta.get("evidence_tokens_est")
                    or memory_meta.get("notes_tokens_est")
                    or 0
                ) if isinstance(memory_meta, dict) else 0
            score = score_value_one(scorer=rec.scorer, gold=rec.gold_answer, gold_aliases=rec.gold_answer_aliases, answer=answer)
            relaxed_score = relaxed_score_value(scorer=rec.scorer, gold=rec.gold_answer, gold_aliases=rec.gold_answer_aliases, answer=answer)
            rows.append(
                {
                    "original_task_id": original_task_id,
                    "run_task_id": rec.task_id,
                    "arm": arm,
                    "benchmark": rec.source_benchmark,
                    "panel_family": str(rec.metadata.get("panel_family") or ""),
                    "source_task": rec.source_task,
                    "query_type": str(rec.metadata.get("query_type") or rec.metadata.get("question_type") or rec.source_task),
                    "expected_tier": str(rec.metadata.get("expected_tier") or ""),
                    "length": str(rec.metadata.get("length_label") or rec.metadata.get("episode_count") or "unknown"),
                    "scorer": rec.scorer,
                    "gold_answer": rec.gold_answer,
                    "agent_answer": answer or "",
                    "score": score,
                    "correct": score >= 1.0,
                    "relaxed_score": relaxed_score,
                    "relaxed_correct": relaxed_score >= 1.0,
                    "parse_ok": rec.parse_ok,
                    "error": rec.error or "",
                    "tool_events": len(rec.tool_events),
                    "compaction_events": len(rec.compaction_events),
                    "duration_s": rec.duration_s or 0.0,
                    "memory_evidence_tokens_est": evidence_tokens,
                    "path": str(path),
                }
            )
    # Drop duplicate arm/task pairs when combining roots. Keep the last supplied root,
    # so a new-arm rerun can intentionally override an older matching arm if needed.
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        deduped[(str(row["original_task_id"]), str(row["arm"]))] = row
    rows = list(deduped.values())

    write_csv(out_dir / "rows.csv", rows)
    summary = summarize(rows, baseline_arm=args.baseline_arm)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    write_report(out_dir / "report.md", args.title, summary)
    print(out_dir)
    return 0


def summarize(rows: list[dict[str, Any]], *, baseline_arm: str = "full_context") -> dict[str, Any]:
    def stats(bucket: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(bucket)
        return {
            "n": n,
            "resolved": sum(1 for r in bucket if not r["error"]),
            "parse_ok": sum(1 for r in bucket if r["parse_ok"]),
            "correct": sum(1 for r in bucket if r["correct"]),
            "accuracy": sum(1 for r in bucket if r["correct"]) / n if n else 0.0,
            "avg_score": sum(float(r["score"]) for r in bucket) / n if n else 0.0,
            "relaxed_correct": sum(1 for r in bucket if r.get("relaxed_correct")),
            "relaxed_accuracy": sum(1 for r in bucket if r.get("relaxed_correct")) / n if n else 0.0,
            "avg_relaxed_score": sum(float(r.get("relaxed_score") or 0.0) for r in bucket) / n if n else 0.0,
            "avg_tool_events": sum(int(r["tool_events"]) for r in bucket) / n if n else 0.0,
            "avg_compaction_events": sum(int(r["compaction_events"]) for r in bucket) / n if n else 0.0,
            "avg_duration_s": sum(float(r["duration_s"]) for r in bucket) / n if n else 0.0,
            "avg_memory_evidence_tokens_est": sum(int(r.get("memory_evidence_tokens_est") or 0) for r in bucket) / n if n else 0.0,
        }

    by_arm = group_stats(rows, lambda r: (r["arm"],), stats)
    by_arm_benchmark = group_stats(rows, lambda r: (r["arm"], r["benchmark"]), stats)
    by_arm_family = group_stats(rows, lambda r: (r["arm"], r["panel_family"]), stats)
    by_arm_task = group_stats(rows, lambda r: (r["arm"], r["source_task"]), stats)
    by_arm_query_type = group_stats(rows, lambda r: (r["arm"], r["query_type"]), stats)

    paired_by_task = defaultdict(dict)
    for r in rows:
        paired_by_task[r["original_task_id"]][r["arm"]] = r

    arms_present = sorted({str(r["arm"]) for r in rows})
    if baseline_arm != "grep_file" and "grep_file" in arms_present:
        default_compare_arm = "grep_file"
    elif baseline_arm != "hierarchy_packet" and "hierarchy_packet" in arms_present:
        default_compare_arm = "hierarchy_packet"
    elif "hierarchy_packet" in arms_present:
        default_compare_arm = "hierarchy_packet"
    else:
        default_compare_arm = next((arm for arm in arms_present if arm != baseline_arm), "grep_file")
    pair_summary = pairwise_summary(paired_by_task, baseline_arm, default_compare_arm)
    pairwise_vs_baseline = {
        arm: pairwise_summary(paired_by_task, baseline_arm, arm)
        for arm in arms_present
        if arm != baseline_arm
    }

    return {
        "overall": stats(rows),
        "by_arm": by_arm,
        "by_arm_benchmark": by_arm_benchmark,
        "by_arm_family": by_arm_family,
        "by_arm_task": by_arm_task,
        "by_arm_query_type": by_arm_query_type,
        "baseline_arm": baseline_arm,
        "paired": pair_summary,
        "pairwise_vs_baseline": pairwise_vs_baseline,
    }


def pairwise_summary(paired_by_task: dict[str, dict[str, dict[str, Any]]], baseline_arm: str, compare_arm: str) -> dict[str, Any]:
    pair_rows: list[dict[str, Any]] = []
    for tid, arms in paired_by_task.items():
        baseline = arms.get(baseline_arm)
        compare = arms.get(compare_arm)
        if not baseline or not compare:
            continue
        baseline_score = float(baseline["score"])
        compare_score = float(compare["score"])
        if baseline_score > compare_score:
            winner = baseline_arm
        elif compare_score > baseline_score:
            winner = compare_arm
        else:
            winner = "tie"
        pair_rows.append(
            {
                "original_task_id": tid,
                "benchmark": baseline["benchmark"],
                "panel_family": baseline["panel_family"],
                "source_task": baseline["source_task"],
                "baseline_arm": baseline_arm,
                "compare_arm": compare_arm,
                "baseline_score": baseline_score,
                "compare_score": compare_score,
                "baseline_correct": bool(baseline["correct"]),
                "compare_correct": bool(compare["correct"]),
                "winner": winner,
                "baseline_error": baseline["error"],
                "compare_error": compare["error"],
            }
        )

    baseline_wins = sum(1 for r in pair_rows if r["winner"] == baseline_arm)
    compare_wins = sum(1 for r in pair_rows if r["winner"] == compare_arm)
    ties = sum(1 for r in pair_rows if r["winner"] == "tie")
    both_correct = sum(1 for r in pair_rows if r["baseline_correct"] and r["compare_correct"])
    baseline_only = sum(1 for r in pair_rows if r["baseline_correct"] and not r["compare_correct"])
    compare_only = sum(1 for r in pair_rows if r["compare_correct"] and not r["baseline_correct"])
    both_wrong = sum(1 for r in pair_rows if not r["baseline_correct"] and not r["compare_correct"])
    return {
        "baseline_arm": baseline_arm,
        "compare_arm": compare_arm,
        "n_pairs": len(pair_rows),
        "baseline_wins": baseline_wins,
        "compare_wins": compare_wins,
        "ties": ties,
        "both_correct": both_correct,
        "baseline_only_correct": baseline_only,
        "compare_only_correct": compare_only,
        "both_wrong": both_wrong,
        "by_benchmark": group_pair_stats(pair_rows, "benchmark"),
        "by_family": group_pair_stats(pair_rows, "panel_family"),
        # Backwards-compatible names used by older reports.
        "full_context_wins": baseline_wins if baseline_arm == "full_context" else 0,
        "grep_file_wins": compare_wins if compare_arm == "grep_file" else 0,
        "full_only_correct": baseline_only if baseline_arm == "full_context" else 0,
        "grep_only_correct": compare_only if compare_arm == "grep_file" else 0,
    }


def group_stats(rows, key_fn, stats_fn):
    buckets = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)
    out = []
    for key, bucket in sorted(buckets.items()):
        rec = {f"key_{i+1}": part for i, part in enumerate(key)}
        rec.update(stats_fn(bucket))
        out.append(rec)
    return out


def group_pair_stats(pair_rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets = defaultdict(list)
    for row in pair_rows:
        buckets[row[key]].append(row)
    out = []
    for value, bucket in sorted(buckets.items()):
        n = len(bucket)
        out.append(
            {
                key: value,
                "n_pairs": n,
                "baseline_arm": bucket[0]["baseline_arm"] if bucket else "",
                "compare_arm": bucket[0]["compare_arm"] if bucket else "",
                "baseline_wins": sum(1 for r in bucket if r["winner"] == r["baseline_arm"]),
                "compare_wins": sum(1 for r in bucket if r["winner"] == r["compare_arm"]),
                "ties": sum(1 for r in bucket if r["winner"] == "tie"),
                "both_correct": sum(1 for r in bucket if r["baseline_correct"] and r["compare_correct"]),
                "baseline_only_correct": sum(1 for r in bucket if r["baseline_correct"] and not r["compare_correct"]),
                "compare_only_correct": sum(1 for r in bucket if r["compare_correct"] and not r["baseline_correct"]),
                "both_wrong": sum(1 for r in bucket if not r["baseline_correct"] and not r["compare_correct"]),
                # Backwards-compatible names for old full-vs-grep report text.
                "full_context_wins": sum(1 for r in bucket if r["winner"] == "full_context"),
                "grep_file_wins": sum(1 for r in bucket if r["winner"] == "grep_file"),
                "full_only_correct": sum(1 for r in bucket if r["baseline_arm"] == "full_context" and r["baseline_correct"] and not r["compare_correct"]),
                "grep_only_correct": sum(1 for r in bucket if r["compare_arm"] == "grep_file" and r["compare_correct"] and not r["baseline_correct"]),
            }
        )
    return out


def write_report(path: Path, title: str, summary: dict[str, Any]) -> None:
    lines = [f"# {title}", ""]
    overall = summary["overall"]
    paired = summary["paired"]
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- runs: `{overall['n']}`")
    lines.append(f"- resolved: `{overall['resolved']}/{overall['n']}`")
    lines.append(f"- parse ok: `{overall['parse_ok']}/{overall['n']}`")
    lines.append(f"- accuracy: `{overall['accuracy']:.1%}` strict, `{overall.get('relaxed_accuracy', 0.0):.1%}` relaxed")
    lines.append("")

    lines.append("## By arm")
    lines.append("")
    for row in summary["by_arm"]:
        lines.append(
            f"- `{row['key_1']}`: `{row['correct']}/{row['n']}` strict-correct ({row['accuracy']:.1%}), "
            f"`{row.get('relaxed_correct', 0)}/{row['n']}` relaxed-correct ({row.get('relaxed_accuracy', 0.0):.1%}), "
            f"parse `{row['parse_ok']}/{row['n']}`, avg tools/run `{row['avg_tool_events']:.2f}`, "
            f"avg evidence `{row.get('avg_memory_evidence_tokens_est', 0.0):.0f}` tok, avg duration `{row['avg_duration_s']:.1f}s`"
        )
    lines.append("")

    lines.append("## Paired comparison")
    lines.append("")
    lines.append(f"- baseline arm: `{paired['baseline_arm']}`")
    lines.append(f"- compare arm: `{paired['compare_arm']}`")
    lines.append(f"- pairs: `{paired['n_pairs']}`")
    lines.append(f"- baseline wins by score: `{paired['baseline_wins']}`")
    lines.append(f"- compare wins by score: `{paired['compare_wins']}`")
    lines.append(f"- ties by score: `{paired['ties']}`")
    lines.append(f"- both correct: `{paired['both_correct']}`")
    lines.append(f"- baseline only correct: `{paired['baseline_only_correct']}`")
    lines.append(f"- compare only correct: `{paired['compare_only_correct']}`")
    lines.append(f"- both wrong: `{paired['both_wrong']}`")
    lines.append("")

    pairwise = summary.get("pairwise_vs_baseline", {})
    extra_pairwise = {arm: rec for arm, rec in pairwise.items() if rec.get("n_pairs", 0) and arm != "grep_file"}
    if extra_pairwise:
        lines.append("## Pairwise vs baseline")
        lines.append("")
        baseline_arm = summary.get("baseline_arm", "full_context")
        for arm, rec in sorted(extra_pairwise.items()):
            lines.append(
                f"- `{baseline_arm}` vs `{arm}`: pairs `{rec['n_pairs']}`, "
                f"baseline wins `{rec['baseline_wins']}`, `{arm}` wins `{rec['compare_wins']}`, ties `{rec['ties']}`, "
                f"both correct `{rec['both_correct']}`, baseline-only `{rec['baseline_only_correct']}`, "
                f"{arm}-only `{rec['compare_only_correct']}`, both wrong `{rec['both_wrong']}`"
            )
        lines.append("")

    query_rows = summary.get("by_arm_query_type") or []
    if query_rows:
        lines.append("## By query type and arm")
        lines.append("")
        for row in query_rows:
            lines.append(f"- `{row['key_1']}` / `{row['key_2']}`: `{row['correct']}/{row['n']}` strict ({row['accuracy']:.1%}), `{row.get('relaxed_correct', 0)}/{row['n']}` relaxed ({row.get('relaxed_accuracy', 0.0):.1%})")
        lines.append("")

    lines.append("## By benchmark and arm")
    lines.append("")
    for row in summary["by_arm_benchmark"]:
        lines.append(f"- `{row['key_1']}` / `{row['key_2']}`: `{row['correct']}/{row['n']}` strict ({row['accuracy']:.1%}), `{row.get('relaxed_correct', 0)}/{row['n']}` relaxed ({row.get('relaxed_accuracy', 0.0):.1%})")
    lines.append("")

    lines.append("## Paired by benchmark")
    lines.append("")
    for row in paired["by_benchmark"]:
        lines.append(
            f"- `{row['benchmark']}`: pairs `{row['n_pairs']}`, baseline-only `{row['baseline_only_correct']}`, "
            f"compare-only `{row['compare_only_correct']}`, both-correct `{row['both_correct']}`, both-wrong `{row['both_wrong']}`"
        )
    lines.append("")

    lines.append("## Paired by family")
    lines.append("")
    for row in paired["by_family"]:
        lines.append(
            f"- `{row['panel_family']}`: pairs `{row['n_pairs']}`, baseline-only `{row['baseline_only_correct']}`, "
            f"compare-only `{row['compare_only_correct']}`, both-correct `{row['both_correct']}`, both-wrong `{row['both_wrong']}`"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
