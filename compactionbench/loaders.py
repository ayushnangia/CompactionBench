"""Load upstream long-context benchmarks into direct JSONL task rows."""

from __future__ import annotations

import ast
import json
import re
import tempfile
import time
import urllib.request
from http.client import IncompleteRead
from pathlib import Path
from typing import Iterable

from pyarrow import parquet as pq

from .schema import Scorer, TaskRow, load_task_rows, write_task_rows

RULER_TASK_CONFIG: dict[str, tuple[Scorer, str]] = {
    "niah_single_1": ("exact_ci", "What is the special magic number mentioned in the documents?"),
    "niah_single_2": ("exact_ci", "What is the special magic number mentioned in the documents?"),
    "niah_single_3": ("exact_ci", "What is the special magic UUID mentioned in the documents?"),
    "niah_multikey_1": ("exact_ci", "What is the special magic number for the specified key?"),
    "niah_multikey_2": ("exact_ci", "What is the special magic number for the specified key?"),
    "niah_multikey_3": ("exact_ci", "What is the special magic number for the specified key?"),
    "niah_multivalue": ("substring_ci", "What are the special magic numbers for the specified key?"),
    "niah_multiquery": ("substring_ci", "What are the special magic numbers for the specified keys?"),
    "vt": ("substring_ci", "What are the values of the tracked variables?"),
    "cwe": ("substring_ci", "What are the 10 most common words in the documents?"),
    "fwe": ("substring_ci", "What are the frequent words in the documents?"),
    "qa_1": ("substring_ci", "Answer the question based on the documents."),
    "qa_2": ("substring_ci", "Answer the question based on the documents."),
}

QUESTION_MARKER_RE = re.compile(
    r"(?:^|\n)(Question:\s*(?P<q>.+?))(?:\n\s*Answer:?\s*)?\Z",
    re.DOTALL,
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def prepare_ruler_tasks(
    input_path: Path,
    *,
    count: int,
    min_length: int = 1_000_000,
    allowed_tasks: set[str] | None = None,
) -> list[TaskRow]:
    """Convert a RULER JSONL shard into direct task rows.

    ``min_length`` defaults to 1M because this experiment is explicitly trying
    to stress harness compaction rather than sit below the model context limit.
    """

    samples = load_jsonl(input_path)
    rows: list[TaskRow] = []

    for sample in samples:
        task = str(sample.get("task") or "unknown")
        if allowed_tasks is not None and task not in allowed_tasks:
            continue

        length = int(sample.get("length") or 0)
        if min_length > 0 and length < min_length:
            continue

        raw_input = str(sample.get("input") or "").strip()
        outputs = [str(o) for o in (sample.get("outputs") or []) if str(o).strip()]
        if not raw_input or not outputs:
            continue

        context, question = _split_ruler_haystack_and_question(raw_input, task)
        scorer, _ = RULER_TASK_CONFIG.get(task, ("substring_ci", "Answer based on the documents."))
        sample_id = str(sample.get("index") or len(rows))
        task_id = f"ruler-{task}-{_sanitize(sample_id)}"

        rows.append(
            TaskRow(
                task_id=task_id,
                source_benchmark="ruler",
                source_task=task,
                source_sample_id=sample_id,
                context=context,
                question=question,
                gold_answer=outputs[0],
                gold_answer_aliases=outputs[1:],
                scorer=scorer,
                metadata={
                    "upstream_length": length or None,
                    "input_path": str(input_path),
                },
            )
        )
        if len(rows) >= count:
            break

    if not rows:
        raise RuntimeError(
            f"No RULER rows emitted from {input_path} (min_length={min_length}, allowed_tasks={allowed_tasks})"
        )
    return rows


BABILONG_DATASET_DEFAULT = "RMT-team/babilong"
BABILONG_DATASET_1K = "RMT-team/babilong-1k-samples"

BABILONG_TASK_INFO: dict[str, dict[str, str]] = {
    "qa1": {"name": "single supporting fact", "scorer": "exact_ci"},
    "qa2": {"name": "two supporting facts", "scorer": "exact_ci"},
    "qa3": {"name": "three supporting facts", "scorer": "exact_ci"},
    "qa4": {"name": "two arg relations", "scorer": "exact_ci"},
    "qa5": {"name": "three arg relations", "scorer": "exact_ci"},
    "qa6": {"name": "yes-no questions", "scorer": "exact_ci"},
    "qa7": {"name": "counting", "scorer": "exact_ci"},
    # qa8 answers can be comma-separated sets like "apple,football" where
    # order should not matter.
    "qa8": {"name": "lists-sets", "scorer": "csv_set_ci"},
    "qa9": {"name": "simple negation", "scorer": "exact_ci"},
    "qa10": {"name": "indefinite knowledge", "scorer": "exact_ci"},
    "qa11": {"name": "basic coreference", "scorer": "exact_ci"},
    "qa12": {"name": "conjunction", "scorer": "exact_ci"},
    "qa13": {"name": "compound coreference", "scorer": "exact_ci"},
    "qa14": {"name": "time reasoning", "scorer": "exact_ci"},
    "qa15": {"name": "basic deduction", "scorer": "exact_ci"},
    "qa16": {"name": "basic induction", "scorer": "exact_ci"},
    "qa17": {"name": "positional reasoning", "scorer": "exact_ci"},
    "qa18": {"name": "size reasoning", "scorer": "exact_ci"},
    "qa19": {"name": "path finding", "scorer": "exact_ci"},
    "qa20": {"name": "agents motivations", "scorer": "exact_ci"},
}

BABILONG_TASK_SCORER: dict[str, Scorer] = {
    task: info["scorer"]  # type: ignore[assignment]
    for task, info in BABILONG_TASK_INFO.items()
}

BABILONG_LONG_CONFIGS = {"128k", "256k", "512k", "1M"}
BABILONG_LONG_SOURCE_TASKS = tuple(f"qa{i}" for i in range(1, 11))
BABILONG_EXTENDED_SOURCE_TASKS = tuple(f"qa{i}" for i in range(11, 21))

_BABI_ENTITY_TERMS = {
    "mary",
    "john",
    "daniel",
    "sandra",
    "julie",
    "bill",
    "fred",
    "jeff",
}
_BABI_LOCATION_TERMS = {
    "bathroom",
    "bedroom",
    "kitchen",
    "hallway",
    "garden",
    "office",
    "school",
    "cinema",
    "park",
}
_BABI_OBJECT_TERMS = {
    "apple",
    "football",
    "milk",
}
_BABI_STYLE_LINE_RE = re.compile(
    r"^(?:mary|john|daniel|sandra|julie|bill|fred|jeff)\b.*$",
    re.IGNORECASE,
)


def prepare_babilong_tasks(
    input_path: Path,
    *,
    count: int,
    source_task: str | None = None,
    length_label: str | None = "1M",
    scorer_override: Scorer | None = None,
    dataset_name: str = BABILONG_DATASET_DEFAULT,
) -> list[TaskRow]:
    """Convert BABILong JSONL rows into direct task rows.

    The public dataset format uses:
      * ``input``    — the full long context
      * ``question`` — the bAbI question
      * ``target``   — the gold answer
    """

    if dataset_name == BABILONG_DATASET_1K and length_label == "1M":
        raise ValueError(
            "RMT-team/babilong-1k-samples does not provide 1M splits; use RMT-team/babilong for 1M BABILong runs"
        )

    samples = load_jsonl(input_path)
    rows: list[TaskRow] = []
    inferred_task = source_task or input_path.stem

    for idx, sample in enumerate(samples):
        context = str(sample.get("input") or sample.get("context") or "").strip()
        question = str(sample.get("question") or "").strip()
        target = str(sample.get("target") or sample.get("answer") or "").strip()
        if not context or not question or not target:
            continue

        sample_id = str(sample.get("id") or sample.get("sample_id") or idx)
        task_name = str(sample.get("task") or inferred_task)
        length_slug = _sanitize(str(length_label or sample.get("length") or "unknown"))
        task_id = f"babilong-{_sanitize(task_name)}-{length_slug}-{_sanitize(sample_id)}"
        scorer = scorer_override or BABILONG_TASK_SCORER.get(task_name, "exact_ci")
        metadata = {"input_path": str(input_path), "dataset_name": dataset_name}
        if length_label is not None:
            metadata["length_label"] = length_label
        if sample.get("length") is not None:
            metadata["upstream_length"] = sample.get("length")

        if task_name in BABILONG_TASK_INFO:
            metadata["task_name"] = BABILONG_TASK_INFO[task_name]["name"]

        rows.append(
            TaskRow(
                task_id=task_id,
                source_benchmark="babilong",
                source_task=task_name,
                source_sample_id=sample_id,
                context=context,
                question=question,
                gold_answer=target,
                gold_answer_aliases=[],
                scorer=scorer,
                metadata=metadata,
            )
        )
        if len(rows) >= count:
            break

    if not rows:
        raise RuntimeError(f"No BABILong rows emitted from {input_path}")
    return rows


def prepare_babilong_tasks_from_hf(
    *,
    config: str,
    split: str,
    count: int,
    dataset_name: str = BABILONG_DATASET_DEFAULT,
    scorer_override: Scorer | None = None,
) -> list[TaskRow]:
    """Load real BABILong rows directly from the HF dataset service.

    Prefer the lightweight `rows` API so we can fetch a tiny slice of a 1M
    split without downloading the full parquet file. Fall back to parquet if
    needed.
    """

    if dataset_name == BABILONG_DATASET_1K and config == "1M":
        raise ValueError(
            "RMT-team/babilong-1k-samples does not provide 1M splits; use RMT-team/babilong for 1M BABILong runs"
        )

    try:
        records = _read_babilong_rows_api(
            dataset_name=dataset_name,
            config=config,
            split=split,
            limit=count,
        )
    except Exception:
        parquet_url = _babilong_parquet_url(dataset_name=dataset_name, config=config, split=split)
        records = _read_parquet_rows(parquet_url, limit=count)

    tmp_rows: list[dict] = []
    for idx, rec in enumerate(records):
        row = {
            "input": rec.get("input"),
            "question": rec.get("question"),
            "target": rec.get("target"),
            "id": str(idx),
            "task": split,
            "length": config,
        }
        tmp_rows.append(row)

    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        tmp_path = Path(f.name)
        for row in tmp_rows:
            f.write(json.dumps(row))
            f.write("\n")

    try:
        return prepare_babilong_tasks(
            tmp_path,
            count=count,
            source_task=split,
            length_label=config,
            scorer_override=scorer_override,
            dataset_name=dataset_name,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


OOLONG_SYNTH_DATASET = "oolongbench/oolong-synth"
OOLONG_REAL_DATASET = "oolongbench/oolong-real"
OOLONG_SYNTH_CONFIG = "default"
OOLONG_REAL_CONFIG = "dnd"
OOLONG_REAL_TOY_CONFIG = "toy_dnd"

OOLONG_CONTEXT_LENGTH_LABELS: dict[int, str] = {
    1024: "1k",
    2048: "2k",
    4096: "4k",
    8192: "8k",
    16384: "16k",
    32768: "32k",
    65536: "64k",
    131072: "128k",
    262144: "256k",
    524288: "512k",
    1_048_576: "1M",
    2_097_152: "2M",
    4_194_304: "4M",
}

OOLONG_SYNTH_ANSWER_SCORER: dict[str, Scorer] = {
    "ANSWER_TYPE.NUMERIC": "numeric_075",
    "ANSWER_TYPE.LABEL": "oolong_text_ci",
    "ANSWER_TYPE.COMPARISON": "oolong_comparison_ci",
    "ANSWER_TYPE.USER": "oolong_text_ci",
    "ANSWER_TYPE.DATE": "date_ci",
    "ANSWER_TYPE.MONTH_YEAR": "month_year_ci",
}


def prepare_oolong_synth_tasks(
    input_path: Path,
    *,
    count: int,
    split: str = "test",
    include_labels: bool = False,
    min_context_len: int = 0,
    max_context_len: int | None = None,
    allowed_task_groups: set[str] | None = None,
    allowed_datasets: set[str] | None = None,
    allowed_context_lens: set[int] | None = None,
    scorer_override: Scorer | None = None,
    dataset_name: str = OOLONG_SYNTH_DATASET,
) -> list[TaskRow]:
    rows: list[TaskRow] = []
    samples = load_jsonl(input_path)

    for sample in samples:
        context_len = int(sample.get("context_len") or 0)
        if min_context_len and context_len < min_context_len:
            continue
        if max_context_len is not None and context_len > max_context_len:
            continue
        if allowed_context_lens is not None and context_len not in allowed_context_lens:
            continue

        task_group = str(sample.get("task_group") or "unknown")
        dataset = str(sample.get("dataset") or "unknown")
        if allowed_task_groups is not None and task_group not in allowed_task_groups:
            continue
        if allowed_datasets is not None and dataset not in allowed_datasets:
            continue

        context_field = "context_window_text_with_labels" if include_labels else "context_window_text"
        context = str(sample.get(context_field) or "").strip()
        question = str(sample.get("question") or "").strip()
        answer_type = str(sample.get("answer_type") or "")
        gold = _parse_oolong_synth_gold(str(sample.get("answer") or ""), answer_type=answer_type)
        if not context or not question or not gold:
            continue

        sample_id = str(sample.get("id") or len(rows))
        length_label = _coerce_context_len_label(context_len)
        scorer = scorer_override or OOLONG_SYNTH_ANSWER_SCORER.get(answer_type, "oolong_text_ci")
        task_id = f"oolong-synth-{_sanitize(task_group)}-{length_label}-{_sanitize(sample_id)}"
        rows.append(
            TaskRow(
                task_id=task_id,
                source_benchmark="oolong",
                source_task=task_group,
                source_sample_id=sample_id,
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=scorer,
                metadata={
                    "input_path": str(input_path),
                    "dataset_name": dataset_name,
                    "split": split,
                    "variant": "with_labels" if include_labels else "standard",
                    "task_group": task_group,
                    "dataset": dataset,
                    "task": sample.get("task"),
                    "answer_type": answer_type,
                    "input_subset": sample.get("input_subset"),
                    "num_labels": sample.get("num_labels"),
                    "context_len": context_len,
                    "length_label": length_label,
                    "context_window_id": sample.get("context_window_id"),
                },
            )
        )
        if len(rows) >= count:
            break

    if not rows:
        raise RuntimeError(f"No OOLONG-synth rows emitted from {input_path}")
    return rows


def prepare_oolong_synth_tasks_from_hf(
    *,
    split: str,
    count: int,
    include_labels: bool = False,
    min_context_len: int = 0,
    max_context_len: int | None = None,
    allowed_task_groups: set[str] | None = None,
    allowed_datasets: set[str] | None = None,
    allowed_context_lens: set[int] | None = None,
    dataset_name: str = OOLONG_SYNTH_DATASET,
    scorer_override: Scorer | None = None,
) -> list[TaskRow]:
    records = _read_hf_rows_api_filtered(
        dataset_name=dataset_name,
        config=OOLONG_SYNTH_CONFIG,
        split=split,
        limit=count,
        record_filter=lambda row: _oolong_synth_record_matches(
            row,
            min_context_len=min_context_len,
            max_context_len=max_context_len,
            allowed_task_groups=allowed_task_groups,
            allowed_datasets=allowed_datasets,
            allowed_context_lens=allowed_context_lens,
        ),
    )
    return _prepare_oolong_synth_records(
        records,
        count=count,
        split=split,
        include_labels=include_labels,
        scorer_override=scorer_override,
        dataset_name=dataset_name,
    )



def prepare_oolong_synth_task_matrix_from_hf(
    *,
    split: str,
    count_per_bucket: int,
    task_groups: list[str],
    context_lens: list[int],
    include_labels: bool = False,
    allowed_datasets: set[str] | None = None,
    dataset_name: str = OOLONG_SYNTH_DATASET,
    scorer_override: Scorer | None = None,
    page_size: int = 20,
    inter_page_sleep_s: float = 0.5,
) -> dict[tuple[str, int], list[TaskRow]]:
    wanted = {(task_group, context_len) for context_len in context_lens for task_group in task_groups}
    buckets: dict[tuple[str, int], list[dict]] = {key: [] for key in wanted}
    offset = 0
    total: int | None = None

    try:
        while total is None or offset < total:
            page_rows, total = _read_hf_rows_page_resilient(
                dataset_name=dataset_name,
                config=OOLONG_SYNTH_CONFIG,
                split=split,
                offset=offset,
                length=page_size,
            )
            if not page_rows:
                break

            for row in page_rows:
                task_group = str(row.get("task_group") or "unknown")
                context_len = int(row.get("context_len") or 0)
                key = (task_group, context_len)
                if key not in wanted:
                    continue
                if allowed_datasets is not None and str(row.get("dataset") or "unknown") not in allowed_datasets:
                    continue
                if len(buckets[key]) < count_per_bucket:
                    buckets[key].append(row)

            if all(len(buckets[key]) >= count_per_bucket for key in wanted):
                break

            offset += len(page_rows)
            if inter_page_sleep_s > 0:
                time.sleep(inter_page_sleep_s)

        missing = {key: len(rows) for key, rows in buckets.items() if len(rows) < count_per_bucket}
        if missing:
            raise RuntimeError(f"Could not fill all OOLONG-synth buckets via rows API: {missing}")
    except Exception:
        buckets = _read_oolong_synth_buckets_from_repo_parquet(
            split=split,
            count_per_bucket=count_per_bucket,
            task_groups=task_groups,
            context_lens=context_lens,
            allowed_datasets=allowed_datasets,
            dataset_name=dataset_name,
        )

    return {
        key: _prepare_oolong_synth_records(
            rows,
            count=count_per_bucket,
            split=split,
            include_labels=include_labels,
            scorer_override=scorer_override,
            dataset_name=dataset_name,
        )
        for key, rows in buckets.items()
    }


def prepare_oolong_real_tasks(
    input_path: Path,
    *,
    count: int,
    split: str = "test",
    config: str = OOLONG_REAL_CONFIG,
    allowed_question_types: set[str] | None = None,
    scorer_override: Scorer | None = None,
    dataset_name: str = OOLONG_REAL_DATASET,
) -> list[TaskRow]:
    rows: list[TaskRow] = []
    for sample in load_jsonl(input_path):
        question_type = str(sample.get("question_type") or "unknown")
        if allowed_question_types is not None and question_type not in allowed_question_types:
            continue
        context = str(sample.get("context_window_text") or "").strip()
        question = str(sample.get("question") or "").strip()
        gold_raw = str(sample.get("answer") or "").strip()
        if not context or not question or not gold_raw:
            continue

        gold, scorer = _parse_oolong_real_gold(gold_raw)
        sample_id = str(sample.get("id") or len(rows))
        task_id = f"oolong-real-{_sanitize(question_type)}-{_sanitize(sample_id)}"
        rows.append(
            TaskRow(
                task_id=task_id,
                source_benchmark="oolong",
                source_task=question_type,
                source_sample_id=sample_id,
                context=context,
                question=question,
                gold_answer=gold,
                gold_answer_aliases=[],
                scorer=scorer_override or scorer,
                metadata={
                    "input_path": str(input_path),
                    "dataset_name": dataset_name,
                    "split": split,
                    "config": config,
                    "question_type": question_type,
                    "episodes": sample.get("episodes"),
                    "campaign": sample.get("campaign"),
                    "context_window_id": sample.get("context_window_id"),
                },
            )
        )
        if len(rows) >= count:
            break

    if not rows:
        raise RuntimeError(f"No OOLONG-real rows emitted from {input_path}")
    return rows


def prepare_oolong_real_tasks_from_hf(
    *,
    split: str,
    count: int,
    config: str = OOLONG_REAL_CONFIG,
    allowed_question_types: set[str] | None = None,
    dataset_name: str = OOLONG_REAL_DATASET,
    scorer_override: Scorer | None = None,
) -> list[TaskRow]:
    records = _read_hf_rows_api_filtered(
        dataset_name=dataset_name,
        config=config,
        split=split,
        limit=count,
        record_filter=lambda row: allowed_question_types is None or str(row.get("question_type") or "unknown") in allowed_question_types,
    )
    return _prepare_oolong_real_records(
        records,
        count=count,
        split=split,
        config=config,
        scorer_override=scorer_override,
        dataset_name=dataset_name,
    )


def _prepare_oolong_synth_records(
    records: list[dict],
    *,
    count: int,
    split: str,
    include_labels: bool,
    scorer_override: Scorer | None,
    dataset_name: str,
) -> list[TaskRow]:
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        tmp_path = Path(f.name)
        for row in records:
            f.write(json.dumps(row))
            f.write("\n")
    try:
        return prepare_oolong_synth_tasks(
            tmp_path,
            count=count,
            split=split,
            include_labels=include_labels,
            scorer_override=scorer_override,
            dataset_name=dataset_name,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def _prepare_oolong_real_records(
    records: list[dict],
    *,
    count: int,
    split: str,
    config: str,
    scorer_override: Scorer | None,
    dataset_name: str,
) -> list[TaskRow]:
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        tmp_path = Path(f.name)
        for row in records:
            f.write(json.dumps(row))
            f.write("\n")
    try:
        return prepare_oolong_real_tasks(
            tmp_path,
            count=count,
            split=split,
            config=config,
            scorer_override=scorer_override,
            dataset_name=dataset_name,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def prepare_babilong_long_missing_tasks_from_hf(
    *,
    length_label: str,
    split: str,
    count: int,
    carrier_dir: Path,
    dataset_name: str = BABILONG_DATASET_DEFAULT,
) -> list[TaskRow]:
    """Construct long qa11-qa20 tasks by embedding real 0k rows in long BABILong noise.

    Upstream `RMT-team/babilong` only exposes qa11-qa20 at config `0k`. To keep the
    benchmark simple and close to the original setting, we reuse cleaned long BABILong
    contexts from qa1-qa10 as the carrier noise, then splice the real short task into
    the middle while preserving the original question and answer.
    """

    if length_label not in BABILONG_LONG_CONFIGS:
        raise ValueError(f"length_label must be one of {sorted(BABILONG_LONG_CONFIGS)}")
    if split not in BABILONG_EXTENDED_SOURCE_TASKS:
        raise ValueError(
            f"split must be one of {list(BABILONG_EXTENDED_SOURCE_TASKS)} for constructed long tasks"
        )

    short_rows = prepare_babilong_tasks_from_hf(
        config="0k",
        split=split,
        count=count,
        dataset_name=dataset_name,
    )
    carrier_rows = _load_babilong_carrier_rows(carrier_dir, length_label=length_label)
    return extend_babilong_rows_with_long_carriers(
        short_rows=short_rows,
        carrier_rows=carrier_rows,
        length_label=length_label,
        dataset_name=dataset_name,
    )


def extend_babilong_rows_with_long_carriers(
    *,
    short_rows: list[TaskRow],
    carrier_rows: list[TaskRow],
    length_label: str,
    dataset_name: str = BABILONG_DATASET_DEFAULT,
) -> list[TaskRow]:
    if length_label not in BABILONG_LONG_CONFIGS:
        raise ValueError(f"length_label must be one of {sorted(BABILONG_LONG_CONFIGS)}")
    if not short_rows:
        raise ValueError("short_rows must not be empty")
    if not carrier_rows:
        raise ValueError("carrier_rows must not be empty")

    rows: list[TaskRow] = []
    for idx, short_row in enumerate(short_rows):
        primary_carrier = carrier_rows[idx % len(carrier_rows)]
        target_chars = len(primary_carrier.context)
        clean_carrier = _build_clean_carrier_text(
            carrier_rows,
            start_idx=idx,
            target_chars=target_chars,
        )
        context = _splice_short_context_into_carrier(
            short_context=short_row.context,
            carrier_text=clean_carrier,
            target_chars=target_chars,
        )
        metadata = dict(short_row.metadata)
        metadata.update(
            {
                "dataset_name": dataset_name,
                "length_label": length_label,
                "construction": "babilong_0k_embedded_in_cleaned_long_carrier",
                "base_length_label": short_row.metadata.get("length_label", "0k"),
                "carrier_length_label": length_label,
                "carrier_task_id": primary_carrier.task_id,
                "carrier_source_task": primary_carrier.source_task,
            }
        )
        rows.append(
            TaskRow(
                task_id=f"babilong-{_sanitize(short_row.source_task)}-{_sanitize(length_label)}-{_sanitize(short_row.source_sample_id)}",
                source_benchmark="babilong",
                source_task=short_row.source_task,
                source_sample_id=short_row.source_sample_id,
                context=context,
                question=short_row.question,
                gold_answer=short_row.gold_answer,
                gold_answer_aliases=short_row.gold_answer_aliases,
                scorer=short_row.scorer,
                metadata=metadata,
            )
        )
    return rows


def write_prepared_tasks(rows: list[TaskRow], out_path: Path) -> None:
    write_task_rows(rows, out_path)


def _load_babilong_carrier_rows(carrier_dir: Path, *, length_label: str) -> list[TaskRow]:
    rows: list[TaskRow] = []
    for task in BABILONG_LONG_SOURCE_TASKS:
        path = carrier_dir / f"babilong_{task}_{length_label}.jsonl"
        if path.exists():
            rows.extend(load_task_rows(path))
    if not rows:
        raise RuntimeError(f"No BABILong carrier rows found in {carrier_dir} for length {length_label}")
    return rows


def _build_clean_carrier_text(
    carrier_rows: list[TaskRow],
    *,
    start_idx: int,
    target_chars: int,
) -> str:
    pieces: list[str] = []
    total = 0
    for offset in range(len(carrier_rows) * 3):
        carrier = carrier_rows[(start_idx + offset) % len(carrier_rows)]
        cleaned = _clean_babilong_carrier_text(carrier.context)
        if not cleaned:
            continue
        pieces.append(cleaned)
        total += len(cleaned)
        if total >= target_chars * 2:
            break
    text = "\n\n".join(pieces)
    if len(text) < target_chars:
        raise RuntimeError(
            f"Cleaned carrier text too short for target length {target_chars}: got {len(text)} chars"
        )
    return text


def _clean_babilong_carrier_text(text: str) -> str:
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_babi_like_line(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _is_babi_like_line(line: str) -> bool:
    lowered = line.lower().strip()
    if not lowered:
        return False
    if _BABI_STYLE_LINE_RE.match(lowered):
        return True
    terms = _BABI_ENTITY_TERMS | _BABI_LOCATION_TERMS | _BABI_OBJECT_TERMS
    if any(term in lowered for term in terms) and len(lowered) <= 240:
        return True
    return False


def _splice_short_context_into_carrier(*, short_context: str, carrier_text: str, target_chars: int) -> str:
    glue = "\n\n"
    budget = target_chars - len(short_context) - len(glue) * 2
    if budget <= 0:
        return short_context
    prefix_chars = budget // 2
    suffix_chars = budget - prefix_chars
    prefix = carrier_text[:prefix_chars].rstrip()
    suffix = carrier_text[-suffix_chars:].lstrip() if suffix_chars > 0 else ""
    return f"{prefix}{glue}{short_context}{glue}{suffix}".strip()


def _read_oolong_synth_buckets_from_repo_parquet(
    *,
    split: str,
    count_per_bucket: int,
    task_groups: list[str],
    context_lens: list[int],
    allowed_datasets: set[str] | None,
    dataset_name: str,
) -> dict[tuple[str, int], list[dict]]:
    from huggingface_hub import HfApi, hf_hub_download

    wanted = {(task_group, context_len) for context_len in context_lens for task_group in task_groups}
    buckets: dict[tuple[str, int], list[dict]] = {key: [] for key in wanted}
    api = HfApi()
    prefix = f"data/{split}-"
    files = sorted(
        file
        for file in api.list_repo_files(dataset_name, repo_type="dataset")
        if file.startswith(prefix) and file.endswith(".parquet")
    )
    if not files:
        raise RuntimeError(f"No OOLONG-synth parquet shards found for split={split} in {dataset_name}")

    wanted_cols = [
        "id",
        "context_len",
        "dataset",
        "context_window_text",
        "context_window_text_with_labels",
        "question",
        "task_group",
        "task",
        "answer",
        "answer_type",
        "input_subset",
        "num_labels",
        "context_window_id",
    ]

    for file in files:
        path = hf_hub_download(repo_id=dataset_name, filename=file, repo_type="dataset")
        quick = pq.read_table(path, columns=["context_len", "task_group", "dataset"])
        quick_rows = quick.to_pylist()
        if not any(
            (str(row["task_group"]), int(row["context_len"])) in wanted
            and (allowed_datasets is None or str(row["dataset"]) in allowed_datasets)
            and len(buckets[(str(row["task_group"]), int(row["context_len"]))]) < count_per_bucket
            for row in quick_rows
        ):
            continue

        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=8, columns=wanted_cols):
            for row in batch.to_pylist():
                key = (str(row.get("task_group") or "unknown"), int(row.get("context_len") or 0))
                if key not in wanted:
                    continue
                if allowed_datasets is not None and str(row.get("dataset") or "unknown") not in allowed_datasets:
                    continue
                if len(buckets[key]) < count_per_bucket:
                    buckets[key].append(row)
            if all(len(buckets[key]) >= count_per_bucket for key in wanted):
                return buckets

    missing = {key: len(rows) for key, rows in buckets.items() if len(rows) < count_per_bucket}
    raise RuntimeError(f"Could not fill all OOLONG-synth buckets from repo parquet: {missing}")



def _coerce_context_len_label(context_len: int) -> str:
    return OOLONG_CONTEXT_LENGTH_LABELS.get(context_len, _sanitize(str(context_len)))


def _oolong_synth_record_matches(
    row: dict,
    *,
    min_context_len: int,
    max_context_len: int | None,
    allowed_task_groups: set[str] | None,
    allowed_datasets: set[str] | None,
    allowed_context_lens: set[int] | None,
) -> bool:
    context_len = int(row.get("context_len") or 0)
    task_group = str(row.get("task_group") or "unknown")
    dataset = str(row.get("dataset") or "unknown")
    if min_context_len and context_len < min_context_len:
        return False
    if max_context_len is not None and context_len > max_context_len:
        return False
    if allowed_context_lens is not None and context_len not in allowed_context_lens:
        return False
    if allowed_task_groups is not None and task_group not in allowed_task_groups:
        return False
    if allowed_datasets is not None and dataset not in allowed_datasets:
        return False
    return True


_DATE_LITERAL_RE = re.compile(r"datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)")


def _parse_oolong_synth_gold(raw: str, *, answer_type: str) -> str:
    raw = raw.strip()
    if answer_type == "ANSWER_TYPE.DATE":
        match = _DATE_LITERAL_RE.search(raw)
        if not match:
            return raw
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    try:
        value = ast.literal_eval(raw)
    except Exception:
        return raw

    if isinstance(value, list) and value:
        value = value[0]
    return str(value)


def _parse_oolong_real_gold(raw: str) -> tuple[str, Scorer]:
    value = raw.strip()
    if re.fullmatch(r"-?\d+", value):
        return value, "numeric_075"
    if "," in value:
        return value, "csv_overlap_ci"
    return value, "oolong_text_ci"


def _read_hf_rows_api_filtered(
    *,
    dataset_name: str,
    config: str,
    split: str,
    limit: int,
    record_filter,
    page_size: int = 20,
) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    total: int | None = None

    while total is None or offset < total:
        take = page_size
        page_rows, total = _read_hf_rows_page_resilient(
            dataset_name=dataset_name,
            config=config,
            split=split,
            offset=offset,
            length=take,
        )
        if not page_rows:
            break
        for row in page_rows:
            if record_filter(row):
                rows.append(row)
                if len(rows) >= limit:
                    return rows
        offset += len(page_rows)
    return rows


def _read_babilong_rows_api(
    *,
    dataset_name: str,
    config: str,
    split: str,
    limit: int,
) -> list[dict]:
    return _read_hf_rows_api_filtered(
        dataset_name=dataset_name,
        config=config,
        split=split,
        limit=limit,
        record_filter=lambda row: True,
    )


def _read_hf_rows_page_resilient(
    *,
    dataset_name: str,
    config: str,
    split: str,
    offset: int,
    length: int,
) -> tuple[list[dict], int]:
    url = (
        "https://datasets-server.huggingface.co/rows"
        f"?dataset={dataset_name}"
        f"&config={config}&split={split}&offset={offset}&length={length}"
    )
    try:
        obj = _load_json_url(url)
        return [row["row"] for row in obj.get("rows", [])], int(obj.get("num_rows_total") or 0)
    except Exception:
        if length <= 1:
            raise
        left_len = length // 2
        right_len = length - left_len
        left_rows, total = _read_hf_rows_page_resilient(
            dataset_name=dataset_name,
            config=config,
            split=split,
            offset=offset,
            length=left_len,
        )
        right_rows, _ = _read_hf_rows_page_resilient(
            dataset_name=dataset_name,
            config=config,
            split=split,
            offset=offset + left_len,
            length=right_len,
        )
        return left_rows + right_rows, total



def _babilong_parquet_url(*, dataset_name: str, config: str, split: str) -> str:
    api = f"https://datasets-server.huggingface.co/parquet?dataset={dataset_name.replace('/', '%2F')}"
    obj = _load_json_url(api)
    for row in obj.get("parquet_files", []):
        if row.get("dataset") == dataset_name and row.get("config") == config and row.get("split") == split:
            return str(row["url"])
    raise RuntimeError(f"No parquet file found for dataset={dataset_name} config={config} split={split}")


def _read_parquet_rows(url: str, *, limit: int) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        parquet_path = Path(f.name)

    try:
        _download_url_to_file(url, parquet_path)
        table = pq.read_table(parquet_path, columns=["input", "question", "target"])
        if limit > 0:
            table = table.slice(0, limit)
        return table.to_pylist()
    finally:
        parquet_path.unlink(missing_ok=True)


def _load_json_url(url: str, *, attempts: int = 6) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as response:
                return json.load(response)
        except Exception as e:
            last_error = e
            if attempt == attempts:
                break
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"Failed to fetch JSON after {attempts} attempts: {url}") from last_error


def _download_url_to_file(url: str, path: Path, *, attempts: int = 6) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as response, path.open("wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            return
        except (IncompleteRead, Exception) as e:
            last_error = e
            path.unlink(missing_ok=True)
            if attempt == attempts:
                break
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"Failed to download file after {attempts} attempts: {url}") from last_error


def _split_ruler_haystack_and_question(raw_input: str, task: str) -> tuple[str, str]:
    match = QUESTION_MARKER_RE.search(raw_input)
    if match:
        return raw_input[: match.start()].rstrip(), match.group("q").strip()
    _, fallback = RULER_TASK_CONFIG.get(task, ("substring_ci", "Answer based on the documents."))
    return raw_input.rstrip(), fallback


def _sanitize(s: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in s)
    return cleaned[:80]
