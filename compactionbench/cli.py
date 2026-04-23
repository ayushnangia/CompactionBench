"""CLI for the simple direct-injection compaction benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .loaders import (
    BABILONG_DATASET_DEFAULT,
    OOLONG_REAL_CONFIG,
    OOLONG_REAL_DATASET,
    OOLONG_REAL_TOY_CONFIG,
    OOLONG_SYNTH_DATASET,
    prepare_babilong_tasks,
    prepare_babilong_tasks_from_hf,
    prepare_oolong_real_tasks,
    prepare_oolong_real_tasks_from_hf,
    prepare_oolong_synth_tasks,
    prepare_oolong_synth_tasks_from_hf,
    prepare_ruler_tasks,
    write_prepared_tasks,
)
from .judge import judge_runs
from .run import load_tasks, run_claude_code_tasks, run_codex_tasks
from .score import format_report, score_runs

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="CompactionBench: simple long-context direct-injection experiments.",
)
prepare_app = typer.Typer(no_args_is_help=True, help="Convert raw benchmark rows into validated task JSONL files.")
run_app = typer.Typer(no_args_is_help=True, help="Run direct multi-turn experiments against a harness.")
app.add_typer(prepare_app, name="prepare")
app.add_typer(run_app, name="run")


@prepare_app.command("ruler")
def prepare_ruler(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True, help="Raw RULER JSONL."),
    out: Path = typer.Option(Path("data/benchmarks/ruler_1m.jsonl"), help="Output JSONL for validated direct task rows."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    min_length: int = typer.Option(1_000_000, help="Minimum upstream RULER length to keep."),
    task: list[str] = typer.Option(None, "--task", help="Optional allowlist of RULER task names; repeat for multiple."),
) -> None:
    rows = prepare_ruler_tasks(
        input_path,
        count=count,
        min_length=min_length,
        allowed_tasks=set(task) if task else None,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated RULER rows to {out}")


@prepare_app.command("babilong")
def prepare_babilong(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True, help="Raw BABILong JSONL."),
    out: Path = typer.Option(Path("data/benchmarks/babilong_1m.jsonl"), help="Output JSONL for validated direct task rows."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    source_task: str = typer.Option(None, "--source-task", help="Override the source task label (e.g. qa1)."),
    length_label: str = typer.Option("1M", "--length-label", help="Length label to store in metadata."),
    dataset_name: str = typer.Option(BABILONG_DATASET_DEFAULT, "--dataset-name", help="Source dataset name for provenance and validation (e.g. RMT-team/babilong)."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override (exact, exact_ci, substring_ci, multiple_choice, csv_set_ci)."),
) -> None:
    rows = prepare_babilong_tasks(
        input_path,
        count=count,
        source_task=source_task,
        length_label=length_label,
        scorer_override=scorer,
        dataset_name=dataset_name,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated BABILong rows to {out}")


@prepare_app.command("babilong-hf")
def prepare_babilong_hf(
    out: Path = typer.Option(Path("data/benchmarks/babilong_qa1_1m.jsonl"), help="Output JSONL for validated direct task rows."),
    config: str = typer.Option("1M", "--config", help="BABILong length config (e.g. 1M, 10M)."),
    split: str = typer.Option("qa1", "--split", help="BABILong split/task name (e.g. qa1)."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    dataset_name: str = typer.Option(BABILONG_DATASET_DEFAULT, "--dataset-name", help="Source dataset name for provenance and validation."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override (exact, exact_ci, substring_ci, multiple_choice, csv_set_ci, numeric_075, csv_overlap_ci, oolong_text_ci, oolong_comparison_ci, date_ci, month_year_ci)."),
) -> None:
    rows = prepare_babilong_tasks_from_hf(
        config=config,
        split=split,
        count=count,
        dataset_name=dataset_name,
        scorer_override=scorer,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated BABILong HF rows to {out}")


@prepare_app.command("oolong-synth")
def prepare_oolong_synth(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True, help="Raw OOLONG-synth JSONL."),
    out: Path = typer.Option(Path("data/benchmarks/oolong_synth.jsonl"), help="Output JSONL for validated direct task rows."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    include_labels: bool = typer.Option(False, "--include-labels", help="Use the in-context labeled variant."),
    min_context_len: int = typer.Option(0, help="Optional minimum context length to keep."),
    max_context_len: int = typer.Option(None, help="Optional maximum context length to keep."),
    task_group: list[str] = typer.Option(None, "--task-group", help="Optional task-group allowlist; repeat for multiple."),
    dataset: list[str] = typer.Option(None, "--dataset", help="Optional source dataset allowlist; repeat for multiple."),
    context_len: list[int] = typer.Option(None, "--context-len", help="Optional exact context length allowlist; repeat for multiple."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override."),
) -> None:
    rows = prepare_oolong_synth_tasks(
        input_path,
        count=count,
        include_labels=include_labels,
        min_context_len=min_context_len,
        max_context_len=max_context_len,
        allowed_task_groups=set(task_group) if task_group else None,
        allowed_datasets=set(dataset) if dataset else None,
        allowed_context_lens=set(context_len) if context_len else None,
        scorer_override=scorer,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated OOLONG-synth rows to {out}")


@prepare_app.command("oolong-synth-hf")
def prepare_oolong_synth_hf(
    out: Path = typer.Option(Path("data/benchmarks/oolong_synth_128k.jsonl"), help="Output JSONL for validated direct task rows."),
    split: str = typer.Option("test", "--split", help="Split name (typically test or validation)."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    include_labels: bool = typer.Option(False, "--include-labels", help="Use the in-context labeled variant."),
    min_context_len: int = typer.Option(0, help="Optional minimum context length to keep."),
    max_context_len: int = typer.Option(None, help="Optional maximum context length to keep."),
    task_group: list[str] = typer.Option(None, "--task-group", help="Optional task-group allowlist; repeat for multiple."),
    dataset: list[str] = typer.Option(None, "--dataset", help="Optional source dataset allowlist; repeat for multiple."),
    context_len: list[int] = typer.Option(None, "--context-len", help="Optional exact context length allowlist; repeat for multiple."),
    dataset_name: str = typer.Option(OOLONG_SYNTH_DATASET, "--dataset-name", help="Source dataset name for provenance and validation."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override."),
) -> None:
    rows = prepare_oolong_synth_tasks_from_hf(
        split=split,
        count=count,
        include_labels=include_labels,
        min_context_len=min_context_len,
        max_context_len=max_context_len,
        allowed_task_groups=set(task_group) if task_group else None,
        allowed_datasets=set(dataset) if dataset else None,
        allowed_context_lens=set(context_len) if context_len else None,
        dataset_name=dataset_name,
        scorer_override=scorer,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated OOLONG-synth HF rows to {out}")


@prepare_app.command("oolong-real")
def prepare_oolong_real(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True, help="Raw OOLONG-real JSONL."),
    out: Path = typer.Option(Path("data/benchmarks/oolong_real.jsonl"), help="Output JSONL for validated direct task rows."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    split: str = typer.Option("test", "--split", help="Split label to store in metadata."),
    config: str = typer.Option(OOLONG_REAL_CONFIG, "--config", help="OOLONG-real config label (dnd or toy_dnd)."),
    question_type: list[str] = typer.Option(None, "--question-type", help="Optional question-type allowlist; repeat for multiple."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override."),
) -> None:
    rows = prepare_oolong_real_tasks(
        input_path,
        count=count,
        split=split,
        config=config,
        allowed_question_types=set(question_type) if question_type else None,
        scorer_override=scorer,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated OOLONG-real rows to {out}")


@prepare_app.command("oolong-real-hf")
def prepare_oolong_real_hf(
    out: Path = typer.Option(Path("data/benchmarks/oolong_real_test.jsonl"), help="Output JSONL for validated direct task rows."),
    split: str = typer.Option("test", "--split", help="Split name (test or validation)."),
    count: int = typer.Option(10, help="Maximum number of rows to emit."),
    config: str = typer.Option(OOLONG_REAL_CONFIG, "--config", help="OOLONG-real config (dnd or toy_dnd)."),
    question_type: list[str] = typer.Option(None, "--question-type", help="Optional question-type allowlist; repeat for multiple."),
    dataset_name: str = typer.Option(OOLONG_REAL_DATASET, "--dataset-name", help="Source dataset name for provenance and validation."),
    scorer: str = typer.Option(None, "--scorer", help="Optional scoring override."),
) -> None:
    rows = prepare_oolong_real_tasks_from_hf(
        split=split,
        count=count,
        config=config,
        allowed_question_types=set(question_type) if question_type else None,
        dataset_name=dataset_name,
        scorer_override=scorer,
    )
    write_prepared_tasks(rows, out)
    typer.echo(f"Wrote {len(rows)} validated OOLONG-real HF rows to {out}")


@run_app.command("claude-code")
def run_claude_code(
    tasks: list[Path] = typer.Option(..., "--tasks", exists=True, readable=True, help="Task JSONL file(s) or directories containing task JSONL files."),
    model: str = typer.Option("claude-sonnet-4-6", help="Claude model id."),
    condition: str = typer.Option("auto", help="Compaction mode: off or auto."),
    out: Path = typer.Option(Path("artifacts/runs_direct"), help="Root directory for per-run JSON artifacts."),
    chunk_tokens: int = typer.Option(4000, help="Approximate tokens per injected context chunk."),
    task_id: list[str] = typer.Option(None, "--task-id", help="Optional task_id allowlist; repeat for multiple."),
    effort: str = typer.Option("low", help="Claude effort level."),
    timeout_s: int = typer.Option(900, help="Timeout per prompt in seconds."),
    settings: str = typer.Option(None, "--settings", help="Optional Claude settings file/JSON passed through to `claude --settings` for bare-mode auth via apiKeyHelper."),
) -> None:
    mode = _validate_condition(condition)
    loaded = load_tasks(tasks, task_filter=set(task_id) if task_id else None)
    written = run_claude_code_tasks(
        tasks=loaded,
        model=model,
        condition=mode,
        out_dir=out,
        chunk_tokens=chunk_tokens,
        effort=effort,
        timeout_s=timeout_s,
        settings=settings,
    )
    typer.echo(f"Wrote {len(written)} Claude Code run records under {out}")


@run_app.command("codex")
def run_codex(
    tasks: list[Path] = typer.Option(..., "--tasks", exists=True, readable=True, help="Task JSONL file(s) or directories containing task JSONL files."),
    model: str = typer.Option("gpt-5.4", help="Codex model id."),
    condition: str = typer.Option("auto", help="Compaction mode: off or auto."),
    out: Path = typer.Option(Path("artifacts/runs_direct"), help="Root directory for per-run JSON artifacts."),
    chunk_tokens: int = typer.Option(4000, help="Approximate tokens per injected context chunk."),
    task_id: list[str] = typer.Option(None, "--task-id", help="Optional task_id allowlist; repeat for multiple."),
    timeout_s: int = typer.Option(900, help="Timeout per prompt in seconds."),
    off_compact_limit: int = typer.Option(2_000_000_000, help="Very large compaction threshold used for condition=off."),
    auto_compact_limit: int = typer.Option(None, help="Optional explicit auto-compaction threshold for condition=auto."),
    reasoning_effort: str = typer.Option("low", "--reasoning-effort", help="Codex reasoning effort (none, minimal, low, medium, high, xhigh)."),
    verbosity: str = typer.Option("low", help="Codex verbosity (low, medium, high)."),
) -> None:
    mode = _validate_condition(condition)
    loaded = load_tasks(tasks, task_filter=set(task_id) if task_id else None)
    written = run_codex_tasks(
        tasks=loaded,
        model=model,
        condition=mode,
        out_dir=out,
        chunk_tokens=chunk_tokens,
        timeout_s=timeout_s,
        off_compact_limit=off_compact_limit,
        auto_compact_limit=auto_compact_limit,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
    )
    typer.echo(f"Wrote {len(written)} Codex run records under {out}")


@app.command()
def score(
    runs: Path = typer.Option(Path("artifacts/runs_direct"), exists=True, file_okay=False, help="Directory containing direct run JSON artifacts."),
    out: Path = typer.Option(Path("artifacts/results"), help="Output directory for rows.csv and summary.*"),
) -> None:
    rows = score_runs(runs, out)
    correct = sum(1 for row in rows if row.correct)
    typer.echo(f"Scored {len(rows)} runs -> {correct} correct ({correct / len(rows) * 100 if rows else 0:.1f}%). Output under {out}")


@app.command()
def report(
    results: Path = typer.Option(Path("artifacts/results"), exists=True, file_okay=False, help="Results directory written by `cbench score`."),
) -> None:
    summary_path = results / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"{summary_path} not found; run `cbench score` first")
    summary = json.loads(summary_path.read_text())
    typer.echo(format_report(summary))


@app.command()
def judge(
    runs: Path = typer.Option(Path("artifacts/runs_direct"), exists=True, file_okay=False, help="Directory containing direct run JSON artifacts."),
    out: Path = typer.Option(Path("artifacts/judge_results"), help="Output directory for judge_rows.csv and judge_summary.json."),
    max_workers: int = typer.Option(4, help="Maximum concurrent judge requests to OpenRouter."),
) -> None:
    rows = judge_runs(runs, out, max_workers=max_workers)
    typer.echo(f"Judged {len(rows)} runs. Output under {out}")


def _validate_condition(raw: str) -> str:
    if raw not in {"off", "auto"}:
        raise typer.BadParameter("condition must be 'off' or 'auto'")
    return raw


if __name__ == "__main__":
    app()
