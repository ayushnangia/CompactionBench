"""Continual Learning Bench loader for CompactionBench.

Converts CLB tasks into compaction stress tests. Each CLB task type produces
a different kind of long context, simulating real agent episodes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.schema import Scorer, TaskRow

CLB_BENCHMARK = "ruler"
CLB_SCORER: Scorer = "substring_ci"


def _pad_context(context: str, target_tokens: int) -> str:
    if len(context) // 4 >= target_tokens:
        return context
    return context + "\n\n" + _make_filler(target_tokens - len(context) // 4)


def _make_filler(n: int) -> str:
    import random as _r
    rng = _r.Random(42)
    t = [
        "The assistant reviewed the codebase structure and identified relevant modules.",
        "Several test runs were executed to verify the changes did not introduce regressions.",
        "The agent consulted documentation and previous commits to understand the context.",
        "A careful analysis of the data revealed patterns that informed the next steps.",
        "The implementation was refined through iterative testing and feedback.",
        "Multiple approaches were evaluated before the final solution was chosen.",
    ]
    out, chars = [], 0
    while chars < n * 4:
        p = rng.choice(t)
        out.append(p)
        chars += len(p) + 1
    return " ".join(out)


def _load_jsonl(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _sanitize(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-")


# ═══════════════════════════════════════════════════════════════════
# Codebase adaptation
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_codebase(
    path: Path,
    *,
    count: int = 10,
    target_tokens: int = 160000,
) -> list[TaskRow]:
    """Sequential PR fixes on the same repo. Episode N context → episode N+1 task."""
    tasks = _load_jsonl(path)
    if not tasks:
        raise RuntimeError(f"No tasks in {path}")

    # Group by repo, sort by sequence
    by_repo: dict[str, list[dict]] = {}
    for t in tasks:
        by_repo.setdefault(t.get("repo", "?"), []).append(t)
    for ts in by_repo.values():
        ts.sort(key=lambda t: t.get("sequence_rank", 0))

    rows: list[TaskRow] = []
    for repo, ts in by_repo.items():
        for i in range(len(ts) - 1):
            if len(rows) >= count:
                break
            prev, curr = ts[i], ts[i + 1]

            ctx = "\n\n".join([
                f"REPO: {repo}",
                f"PREVIOUS FIX #{prev.get('pull_number','?')}: {prev.get('problem_statement','')}",
                f"PREVIOUS PATCH:\n{str(prev.get('patch',''))[:4000]}",
                f"TESTS FIXED: {', '.join(prev.get('FAIL_TO_PASS',[])[:5])}",
            ])
            ctx = _pad_context(ctx, target_tokens)

            q = (
                f"Fix this bug in {repo}:\n\n{curr.get('problem_statement','')}\n\n"
                f"Failing tests: {', '.join(curr.get('FAIL_TO_PASS',[])[:5])}"
            )
            gold = str(curr.get('patch', ''))[:4000]

            rows.append(TaskRow(
                task_id=f"clb-codebase-{_sanitize(repo)}-ep{i:02d}",
                source_benchmark=CLB_BENCHMARK,
                source_task="clb_codebase",
                source_sample_id=curr.get("instance_id", f"{repo}-{i}"),
                context=ctx, question=q, gold_answer=gold,
                gold_answer_aliases=[], scorer=CLB_SCORER,
                metadata={"repo": repo, "episode": i, "prev": prev.get("instance_id",""),
                          "curr": curr.get("instance_id","")},
            ))
        if len(rows) >= count:
            break
    return rows


# ═══════════════════════════════════════════════════════════════════
# Sales prediction
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_sales(
    panel_path: Path,
    meta_path: Path,
    *,
    count: int = 6,
    target_tokens: int = 160000,
) -> list[TaskRow]:
    """Sales forecasting across episodes. Each episode adds more sales data."""
    meta = json.loads(meta_path.read_text())
    panel = _load_jsonl(panel_path)

    total_episodes = meta.get("total_instances", 12)
    rows_per_ep = len(panel) // max(total_episodes, 1)

    rows: list[TaskRow] = []
    for ep in range(min(total_episodes - 1, count)):
        start = ep * rows_per_ep
        end = start + rows_per_ep

        # Context: all data up to this episode
        history = panel[:end]
        ctx = f"SALES DATA (episodes 0-{ep}, {len(history)} rows):\n"
        ctx += "furniture_id,location,type,price,year,sold\n"
        for r in history[:500]:  # Sample first 500 rows
            ctx += f"{r.get('furniture_id','')},{r.get('location_id','')},{r.get('furniture_type','')},{r.get('furniture_price','')},{r.get('year','')},{r.get('items_sold','')}\n"
        ctx = _pad_context(ctx, target_tokens)

        # Next episode data
        next_data = panel[end:end + rows_per_ep]
        if not next_data:
            break

        q = f"Predict items sold for the next period. Here is the new data ({len(next_data)} rows):\n"
        q += "furniture_id,location,type,price,year\n"
        for r in next_data[:10]:
            q += f"{r.get('furniture_id','')},{r.get('location_id','')},{r.get('furniture_type','')},{r.get('furniture_price','')},{r.get('year','')}\n"
        q += "\nReturn your predictions as: furniture_id,predicted_sold"

        gold_rows = []
        for r in next_data[:10]:
            gold_rows.append(f"{r.get('furniture_id','')},{r.get('items_sold','')}")
        gold = "\n".join(gold_rows)

        rows.append(TaskRow(
            task_id=f"clb-sales-ep{ep:02d}",
            source_benchmark=CLB_BENCHMARK,
            source_task="clb_sales",
            source_sample_id=f"ep{ep}",
            context=ctx, question=q, gold_answer=gold,
            gold_answer_aliases=[], scorer=CLB_SCORER,
            metadata={"episode": ep, "history_rows": len(history), "next_rows": len(next_data)},
        ))

    return rows


# ═══════════════════════════════════════════════════════════════════
# Database exploration
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_database(
    questions_path: Path,
    *,
    count: int = 10,
    target_tokens: int = 160000,
) -> list[TaskRow]:
    """SQL questions over a database. Each question tests query writing."""
    qs = json.loads(questions_path.read_text())
    if not isinstance(qs, list):
        raise RuntimeError("Expected list of questions")

    rows: list[TaskRow] = []
    for i, q in enumerate(qs):
        if len(rows) >= count:
            break
        ctx = f"DATABASE SCHEMA:\n"
        ctx += "Table: fdbk_g1 (review_id, product_id, timestamp, rating, text)\n"
        ctx += "Table: products (product_id, category, price)\n"
        ctx = _pad_context(ctx, target_tokens)

        question = q.get("question", "")
        gold = q.get("sql", "")

        rows.append(TaskRow(
            task_id=f"clb-db-q{i:03d}",
            source_benchmark=CLB_BENCHMARK,
            source_task="clb_database",
            source_sample_id=str(q.get("question_id", i)),
            context=ctx, question=question, gold_answer=gold,
            gold_answer_aliases=[], scorer=CLB_SCORER,
            metadata={"question_id": q.get("question_id", i)},
        ))
    return rows


# ═══════════════════════════════════════════════════════════════════
# Cohort studies
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_cohort(
    meta_path: Path,
    ground_truth_path: Path,
    *,
    count: int = 10,
    target_tokens: int = 160000,
) -> list[TaskRow]:
    """Medical cohort analysis tasks over patient databases."""
    meta = json.loads(meta_path.read_text())
    truth = json.loads(ground_truth_path.read_text())
    instances = meta.get("instances", [])

    rows: list[TaskRow] = []
    for inst in instances[:count]:
        ctx = (
            f"STUDY: {inst.get('study_name','?')}\n"
            f"DATABASE: {inst.get('db_filename','?')}\n"
            f"PATIENTS: {inst.get('n_patients','?')}\n"
            f"REGION: {inst.get('region_slice','?')}\n"
        )
        ctx = _pad_context(ctx, target_tokens)

        q = (
            f"Analyze the {inst.get('study_name','?')} cohort.\n"
            f"Find the key findings for region {inst.get('region_slice','?')}.\n"
            f"Write the SQL queries needed."
        )

        # Gold: relevant ground truth
        inst_id = inst.get("instance_index", 0)
        gold = str(truth[inst_id])[:4000] if inst_id < len(truth) else ""

        rows.append(TaskRow(
            task_id=f"clb-cohort-{_sanitize(inst.get('study_name','?'))}-{inst.get('instance_index',0)}",
            source_benchmark=CLB_BENCHMARK,
            source_task="clb_cohort",
            source_sample_id=str(inst.get("instance_index", 0)),
            context=ctx, question=q, gold_answer=gold,
            gold_answer_aliases=[], scorer=CLB_SCORER,
            metadata={"study": inst.get("study_name",""), "region": inst.get("region_slice","")},
        ))
    return rows


# ═══════════════════════════════════════════════════════════════════
# Blind spectrum monitoring
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_spectrum(
    data_path: Path,
    *,
    count: int = 5,
    target_tokens: int = 160000,
) -> list[TaskRow]:
    scans = _load_jsonl(data_path)
    if not scans:
        raise RuntimeError(f"No scans in {data_path}")

    rows: list[TaskRow] = []
    for ep in range(0, min(len(scans) - 10, count * 10), 10):
        if len(rows) >= count:
            break
        history = scans[:ep + 10]
        ctx = "BLIND SPECTRUM MONITORING — Radio frequency scan data\\n"
        ctx += "SCAN: idx, sensor, noise_floor_dbm, peaks(freq_mhz@power_dbm)\\n\\n"
        for s in history:
            peaks = s.get('detected_peaks', [])
            peak_str = ", ".join(
                f"{p['freq_mhz']:.1f}MHz@{p['power_dbm']:.0f}dBm" for p in peaks
            ) or "none"
            ctx += f"scan{s['scan_idx']:03d}: noise={s['estimated_noise_floor_dbm']}dBm peaks=[{peak_str}]\n"
        ctx = _pad_context(ctx, target_tokens)
        future = scans[ep + 10:ep + 15]
        q = "Analyze the next scans for interference patterns:\n"
        for s in future:
            peaks = s.get('detected_peaks', [])
            peak_str = ", ".join(
                f"{p['freq_mhz']:.1f}MHz@{p['power_dbm']:.0f}dBm" for p in peaks
            ) or "none"
            q += f"scan{s['scan_idx']:03d}: peaks=[{peak_str}]\n"
        gold = str(s.get('ground_truth', '') or '')[:4000]
        rows.append(TaskRow(
            task_id=f"clb-spectrum-ep{ep//10:02d}",
            source_benchmark=CLB_BENCHMARK, source_task="clb_spectrum",
            source_sample_id=str(ep),
            context=ctx, question=q, gold_answer=gold,
            gold_answer_aliases=[], scorer=CLB_SCORER,
            metadata={"episode": ep, "scans_in_context": len(history)},
        ))
    return rows


# ═══════════════════════════════════════════════════════════════════
# Exploitable poker
# ═══════════════════════════════════════════════════════════════════

def prepare_clb_poker(
    *,
    count: int = 5,
    target_tokens: int = 160000,
    hands_per_context: int = 100,
) -> list[TaskRow]:
    import random as _r
    rng = _r.Random(42)
    suits = ["S", "H", "D", "C"]
    ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    actions = ["fold", "call", "raise", "check", "bet"]

    rows: list[TaskRow] = []
    for ep in range(count):
        ctx = "POKER HAND HISTORY\n\n"
        for h in range(hands_per_context):
            hole = f"{rng.choice(ranks)}{rng.choice(suits)} {rng.choice(ranks)}{rng.choice(suits)}"
            board = " ".join(f"{rng.choice(ranks)}{rng.choice(suits)}" for _ in range(5))
            opp_action = rng.choice(actions)
            ctx += f"H{h+1}: [{hole}] board[{board}] opp={opp_action}\n"
        ctx = _pad_context(ctx, target_tokens)

        hole = f"{rng.choice(ranks)}{rng.choice(suits)} {rng.choice(ranks)}{rng.choice(suits)}"
        board = " ".join(f"{rng.choice(ranks)}{rng.choice(suits)}" for _ in range(3))
        q = f"You hold [{hole}]. Flop is [{board}]. Optimal action?"
        gold = "raise" if rng.random() > 0.5 else "fold"

        rows.append(TaskRow(
            task_id=f"clb-poker-ep{ep:02d}",
            source_benchmark=CLB_BENCHMARK, source_task="clb_poker",
            source_sample_id=str(ep),
            context=ctx, question=q, gold_answer=gold,
            gold_answer_aliases=[], scorer=CLB_SCORER,
            metadata={"episode": ep, "hands": hands_per_context},
        ))
    return rows
