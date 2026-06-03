"""LongMemEval-V2 loader for CompactionBench.

Converts web-agent trajectory haystacks into compaction stress tests. Each
question has a haystack of trajectory IDs; the rendered trajectories become the
long context and the LongMemEval question becomes the final prompt.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from ..core.schema import Scorer, TaskRow

LME_BENCHMARK = "lme"
LME_SCORER: Scorer = "substring_ci"


def load_lme_haystack(haystack_path: Path) -> dict[str, list[str]]:
    """Load haystack: question/session id -> list of trajectory IDs."""
    return json.loads(haystack_path.read_text())


def load_lme_trajectories(traj_path: Path) -> dict[str, dict]:
    """Load trajectories: trajectory id -> trajectory data."""
    trajs: dict[str, dict] = {}
    with traj_path.open() as f:
        for line in f:
            if line.strip():
                traj = json.loads(line)
                tid = str(traj.get("id") or traj.get("trajectory_id") or "")
                if tid:
                    trajs[tid] = traj
    return trajs


def load_lme_questions(q_path: Path) -> list[dict]:
    """Load LongMemEval questions JSONL."""
    with q_path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def prepare_lme_tasks(
    haystack_path: Path,
    trajectories_path: Path,
    questions_path: Path,
    *,
    count: int = 10,
    target_tokens: int = 160_000,
    sessions: list[str] | None = None,
    question_types: set[str] | None = None,
    count_per_type: int | None = None,
    max_trajectories: int = 120,
) -> list[TaskRow]:
    """Create compaction tasks from LongMemEval-V2.

    Parameters
    ----------
    haystack_path:
        JSON mapping question/session ids to trajectory ids.
    trajectories_path:
        JSONL trajectory database.
    questions_path:
        JSONL LongMemEval questions.
    count:
        Global maximum number of emitted rows.
    target_tokens:
        Minimum approximate context size. Short rendered contexts are padded
        with neutral filler to reach this token estimate.
    sessions:
        Optional allowlist of LongMemEval question/session ids.
    question_types:
        Optional allowlist of LongMemEval ``question_type`` values.
    count_per_type:
        Optional cap per question type, useful for all-type confirmation panels.
    max_trajectories:
        Maximum trajectories rendered from each haystack. The upstream medium
        haystack has up to 500 trajectories/question, so this keeps preparation
        and pilot runs tractable while preserving a long-agent-history shape.
    """
    if count <= 0:
        return []
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    if count_per_type is not None and count_per_type <= 0:
        raise ValueError("count_per_type must be positive when provided")
    if max_trajectories <= 0:
        raise ValueError("max_trajectories must be positive")

    haystack = load_lme_haystack(haystack_path)
    traj_db = load_lme_trajectories(trajectories_path)
    questions = load_lme_questions(questions_path)
    session_allowlist = set(sessions) if sessions else None

    rows: list[TaskRow] = []
    per_type_counts: defaultdict[str, int] = defaultdict(int)

    for q in questions:
        if len(rows) >= count:
            break

        qid = str(q.get("id") or "").strip()
        if not qid or qid not in haystack:
            continue
        if session_allowlist is not None and qid not in session_allowlist:
            continue

        qtype = str(q.get("question_type") or "unknown")
        if question_types is not None and qtype not in question_types:
            continue
        if count_per_type is not None and per_type_counts[qtype] >= count_per_type:
            continue

        question = str(q.get("question") or "").strip()
        answer = str(q.get("answer") or "").strip()
        if not question or not answer:
            continue

        context = _render_session_context(
            qid=qid,
            traj_ids=haystack[qid],
            traj_db=traj_db,
            max_trajectories=max_trajectories,
        )
        real_tokens = len(context) // 4
        if real_tokens < target_tokens:
            context += "\n\n" + _generate_filler(target_tokens - real_tokens)

        rows.append(
            TaskRow(
                task_id=f"lme-{_sanitize(qtype)}-{_sanitize(qid)}",
                source_benchmark=LME_BENCHMARK,
                source_task=f"lme_{qtype}",
                source_sample_id=qid,
                context=context,
                question=question,
                gold_answer=answer,
                gold_answer_aliases=[],
                scorer=_scorer_for_lme_question(q),
                metadata={
                    "input_haystack_path": str(haystack_path),
                    "input_trajectories_path": str(trajectories_path),
                    "input_questions_path": str(questions_path),
                    "domain": q.get("domain", "?"),
                    "environment": q.get("environment", "?"),
                    "question_type": qtype,
                    "eval_function": q.get("eval_function"),
                    "trajectories_in_context": min(max_trajectories, len(haystack[qid])),
                    "total_trajectories": len(haystack[qid]),
                    "target_tokens": target_tokens,
                },
            )
        )
        per_type_counts[qtype] += 1

    if not rows:
        raise RuntimeError(
            f"No LongMemEval rows emitted from {questions_path} "
            f"(question_types={sorted(question_types) if question_types else None}, sessions={sessions})"
        )
    return rows


def _render_session_context(
    *,
    qid: str,
    traj_ids: list[str],
    traj_db: dict[str, dict],
    max_trajectories: int,
) -> str:
    ctx_parts = [f"LONGMEMEVAL QUESTION/HAYSTACK {qid}", f"TRAJECTORIES ({len(traj_ids)} total; rendering first {min(max_trajectories, len(traj_ids))})"]
    missing = 0
    for tid in traj_ids[:max_trajectories]:
        traj = traj_db.get(tid)
        if traj is None:
            missing += 1
            continue
        ctx_parts.append(_render_trajectory(traj))
    if missing:
        ctx_parts.append(f"[missing trajectories skipped: {missing}]")
    return "\n\n".join(ctx_parts)


def _render_trajectory(traj: dict, *, max_states: int = 4, state_text_chars: int = 700) -> str:
    """Render one trajectory compactly but preserve agent-memory details."""
    parts: list[str] = []
    tid = str(traj.get("id") or traj.get("trajectory_id") or "?")
    parts.append(f"TRAJECTORY {tid}:")

    for key in ("domain", "environment", "goal", "outcome", "start_url"):
        value = traj.get(key)
        if value not in (None, ""):
            parts.append(f"  {key}: {_clip(str(value), 900)}")

    states = traj.get("states")
    if isinstance(states, list) and states:
        selected = _select_edge_items(states, max_items=max_states)
        for state in selected:
            if not isinstance(state, dict):
                parts.append(f"  State: {_clip(str(state), state_text_chars)}")
                continue
            state_idx = state.get("state_index", "?")
            step = state.get("step", "?")
            parts.append(f"  State {state_idx} (step {step}):")
            for key in ("url", "thought", "action"):
                value = state.get(key)
                if value not in (None, ""):
                    parts.append(f"    {key}: {_clip(str(value), state_text_chars)}")
            tree = state.get("accessibility_tree") or state.get("observation")
            if tree:
                parts.append(f"    page_observation: {_clip(str(tree), state_text_chars)}")
        if len(states) > len(selected):
            parts.append(f"  ... {len(states) - len(selected)} intermediate states omitted ...")
    elif "steps" in traj and isinstance(traj["steps"], list):
        for i, step in enumerate(_select_edge_items(traj["steps"], max_items=max_states)):
            if isinstance(step, dict):
                action = step.get("action", step.get("type", "?"))
                target = step.get("target", step.get("element", ""))
                result = step.get("result", step.get("observation", ""))
                parts.append(f"  Step {i}: {_clip(str(action), 200)} {_clip(str(target), 200)} -> {_clip(str(result), state_text_chars)}")
            else:
                parts.append(f"  Step {i}: {_clip(str(step), state_text_chars)}")
    elif "actions" in traj and isinstance(traj["actions"], list):
        for i, action in enumerate(_select_edge_items(traj["actions"], max_items=max_states)):
            parts.append(f"  Action {i}: {_clip(str(action), state_text_chars)}")
    else:
        for key, value in traj.items():
            if key != "id":
                parts.append(f"  {key}: {_clip(str(value), state_text_chars)}")

    return "\n".join(parts)


def _select_edge_items(items: list, *, max_items: int) -> list:
    if len(items) <= max_items:
        return items
    front = max_items // 2
    back = max_items - front
    return items[:front] + items[-back:]


def _scorer_for_lme_question(q: dict) -> Scorer:
    answer = str(q.get("answer") or "").strip()
    eval_function = str(q.get("eval_function") or "")
    if "," in answer and "ordered" not in eval_function:
        return "csv_set_ci"
    if re.fullmatch(r"-?\d+(?:\.0+)?", answer):
        return "exact_ci"
    return LME_SCORER


def _generate_filler(n_tokens: int) -> str:
    import random as _r

    rng = _r.Random(42)
    templates = [
        "The agent navigated to the next page and continued the task.",
        "A form was filled with the requested information and submitted.",
        "The system displayed a confirmation message after processing.",
        "Several dropdown options were reviewed before making a selection.",
        "The page loaded additional content after scrolling down.",
    ]
    out: list[str] = []
    chars = 0
    while chars < n_tokens * 4:
        phrase = rng.choice(templates)
        out.append(phrase)
        chars += len(phrase) + 1
    return " ".join(out)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _sanitize(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-")[:80]
