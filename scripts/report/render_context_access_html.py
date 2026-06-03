#!/usr/bin/env python3
"""Render a plain-English HTML report for context-access strategy runs."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--analysis-dir", required=True)
    p.add_argument("--out-html", required=True)
    p.add_argument("--title", default="Paged context experiment report")
    p.add_argument("--batch-root", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    analysis_dir = Path(args.analysis_dir)
    out = Path(args.out_html)
    rows = read_rows(analysis_dir / "rows.csv")
    summary = read_json(analysis_dir / "summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(args.title, args.batch_root, rows, summary))
    print(out)
    return 0


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text().strip():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def pct(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except Exception:
        return "n/a"


def esc(value: Any) -> str:
    return html.escape(str(value))


def render(title: str, batch_root: str, rows: list[dict[str, str]], summary: dict[str, Any]) -> str:
    by_arm = summary.get("by_arm", [])
    by_bench = summary.get("by_arm_benchmark", [])
    overall = summary.get("overall", {})
    target_arm = choose_example_arm(rows)
    examples = select_examples(rows, target_arm=target_arm)
    pairwise = summary.get("pairwise_vs_baseline", {})

    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{esc(title)}</title>
<style>
:root{{--bg:#0b1020;--panel:#121a2b;--panel2:#172238;--text:#eef4ff;--muted:#aab8ce;--line:#2a3956;--green:#34d399;--blue:#60a5fa;--yellow:#fbbf24;--red:#fb7185;}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 10% 0%,rgba(96,165,250,.22),transparent 35rem),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.55}}.wrap{{max-width:1160px;margin:0 auto;padding:42px 22px 80px}}header,section{{border:1px solid var(--line);background:rgba(18,26,43,.94);border-radius:24px;padding:28px;margin:0 0 20px;box-shadow:0 20px 60px rgba(0,0,0,.32)}}h1{{font-size:clamp(34px,6vw,68px);line-height:1;letter-spacing:-.055em;margin:0 0 14px}}h2{{font-size:clamp(24px,3vw,38px);letter-spacing:-.035em;line-height:1.1;margin:0 0 14px}}h3{{margin:0 0 8px}}p{{margin:0 0 12px}}.big{{font-size:20px;color:#dbeafe}}.muted{{color:var(--muted)}}.pillrow{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.pill{{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:#0b1020;color:#dbeafe;font-size:14px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.grid.two{{grid-template-columns:repeat(2,1fr)}}.card{{border:1px solid var(--line);border-radius:18px;background:rgba(23,34,56,.85);padding:18px}}.metric{{font-size:38px;font-weight:950;letter-spacing:-.05em;line-height:1;margin:8px 0}}table{{width:100%;border-collapse:collapse;margin-top:12px;border-radius:14px;overflow:hidden}}th,td{{border:1px solid var(--line);padding:11px 13px;text-align:left;vertical-align:top}}th{{background:#0b1020}}td{{background:rgba(11,16,32,.36)}}code,pre{{background:#0b1020;border:1px solid var(--line);border-radius:12px}}code{{padding:2px 5px}}pre{{padding:14px;white-space:pre-wrap;word-break:break-word}}.green{{color:var(--green);font-weight:850}}.blue{{color:var(--blue);font-weight:850}}.yellow{{color:var(--yellow);font-weight:850}}.red{{color:var(--red);font-weight:850}}.callout{{border:1px solid rgba(52,211,153,.45);background:rgba(52,211,153,.10);border-radius:18px;padding:18px}}@media(max-width:850px){{.grid,.grid.two{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main class=\"wrap\">
<header>
<h1>{esc(title)}</h1>
<p class=\"big\">This report compares several ways for an agent to use a long source: direct full context, one searchable file, manual paging, and transparent virtual context.</p>
<div class=\"pillrow\"><span class=\"pill\">batch: {esc(batch_root or 'not recorded')}</span><span class=\"pill\">runs: {esc(overall.get('n','n/a'))}</span><span class=\"pill\">strict + relaxed scoring</span><span class=\"pill\">real BABILong + OOLONG</span></div>
</header>

<section>
<h2>What we are testing</h2>
<div class=\"grid\">
<div class=\"card\"><h3>Full context</h3><p>The whole source is pasted into the prompt. No search tools.</p></div>
<div class=\"card\"><h3>File search</h3><p>The source is saved as <code>full_context.txt</code>. The agent can grep/search it.</p></div>
<div class=\"card\"><h3>Paged / virtual context</h3><p>Manual paging lets the model search pages. Virtual context makes the system load a resident evidence packet before the model answers.</p></div>
</div>
</section>

<section>
<h2>Top-line results</h2>
{render_arm_cards(by_arm)}
<p class=\"muted\">Strict score uses the original benchmark scorer. Relaxed score also accepts harmless formatting changes such as <code>the bathroom</code> vs <code>bathroom</code>.</p>
</section>

<section>
<h2>Pairwise against full context</h2>
{render_pairwise(pairwise)}
</section>

<section>
<h2>Breakdown by dataset</h2>
{render_by_benchmark(by_bench)}
</section>

<section>
<h2>Interesting examples</h2>
{render_examples(examples, target_arm)}
</section>

<section>
<h2>How to read this</h2>
<div class=\"callout\"><p><strong>Good result for paging:</strong> paged context should match or beat file search on exact lookup, while doing better on broad reading/counting because pages preserve nearby context.</p><p><strong>Bad result for paging:</strong> if it searches the wrong pages, it can confidently answer from irrelevant evidence. The examples above are the most useful part for improving the pager.</p></div>
</section>

</main></body></html>
"""


def render_arm_cards(by_arm: list[dict[str, Any]]) -> str:
    if not by_arm:
        return "<p>No completed analysis yet.</p>"
    cards = ["<div class=\"grid\">"]
    for row in by_arm:
        cards.append(
            "<div class=\"card\">"
            f"<h3>{esc(row.get('key_1','unknown'))}</h3>"
            f"<div class=\"metric\">{esc(row.get('correct','?'))}/{esc(row.get('n','?'))}</div>"
            f"<p>strict: <span class=\"blue\">{pct(row.get('accuracy'))}</span></p>"
            f"<p>relaxed: <span class=\"green\">{esc(row.get('relaxed_correct','?'))}/{esc(row.get('n','?'))} ({pct(row.get('relaxed_accuracy'))})</span></p>"
            f"<p class=\"muted\">tools/run {float(row.get('avg_tool_events') or 0):.2f}; duration {float(row.get('avg_duration_s') or 0):.1f}s</p>"
            "</div>"
        )
    cards.append("</div>")
    return "\n".join(cards)


def render_pairwise(pairwise: dict[str, Any]) -> str:
    if not pairwise:
        return "<p>No pairwise results yet.</p>"
    lines = ["<table><thead><tr><th>Comparison</th><th>Pairs</th><th>Full wins</th><th>Other wins</th><th>Ties</th><th>Only other correct</th></tr></thead><tbody>"]
    for arm, rec in sorted(pairwise.items()):
        lines.append(
            f"<tr><td>full_context vs {esc(arm)}</td><td>{esc(rec.get('n_pairs'))}</td>"
            f"<td>{esc(rec.get('baseline_wins'))}</td><td>{esc(rec.get('compare_wins'))}</td>"
            f"<td>{esc(rec.get('ties'))}</td><td>{esc(rec.get('compare_only_correct'))}</td></tr>"
        )
    lines.append("</tbody></table>")
    return "\n".join(lines)


def render_by_benchmark(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No breakdown yet.</p>"
    lines = ["<table><thead><tr><th>Arm</th><th>Dataset</th><th>Strict</th><th>Relaxed</th><th>Parse OK</th></tr></thead><tbody>"]
    for row in rows:
        n = row.get("n", "?")
        lines.append(
            f"<tr><td>{esc(row.get('key_1'))}</td><td>{esc(row.get('key_2'))}</td>"
            f"<td>{esc(row.get('correct'))}/{esc(n)} ({pct(row.get('accuracy'))})</td>"
            f"<td>{esc(row.get('relaxed_correct'))}/{esc(n)} ({pct(row.get('relaxed_accuracy'))})</td>"
            f"<td>{esc(row.get('parse_ok'))}/{esc(n)}</td></tr>"
        )
    lines.append("</tbody></table>")
    return "\n".join(lines)


def choose_example_arm(rows: list[dict[str, str]]) -> str:
    arms = {row.get("arm", "") for row in rows}
    virtual_arms = sorted(arm for arm in arms if arm.startswith("virtual_context"))
    if "virtual_context_rlm" in arms:
        return "virtual_context_rlm"
    if "virtual_context_24k" in arms:
        return "virtual_context_24k"
    if "virtual_context" in arms:
        return "virtual_context"
    if virtual_arms:
        return virtual_arms[0]
    if "paged_context" in arms:
        return "paged_context"
    return ""


def select_examples(rows: list[dict[str, str]], *, target_arm: str) -> dict[str, list[tuple[dict[str, str], dict[str, str] | None, dict[str, str] | None]]]:
    grouped: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        grouped[row.get("original_task_id", row.get("run_task_id", ""))][row.get("arm", "")] = row
    out: dict[str, list[tuple[dict[str, str], dict[str, str] | None, dict[str, str] | None]]] = defaultdict(list)
    for arms in grouped.values():
        full = arms.get("full_context")
        grep = arms.get("grep_file")
        paged = arms.get(target_arm) if target_arm else None
        if not paged:
            continue
        p_rel = as_bool(paged.get("relaxed_correct"))
        f_rel = as_bool(full.get("relaxed_correct")) if full else False
        g_rel = as_bool(grep.get("relaxed_correct")) if grep else False
        if p_rel and not f_rel and not g_rel and len(out["pager_only"]) < 4:
            out["pager_only"].append((paged, full, grep))
        if f_rel and not p_rel and len(out["full_only_over_pager"]) < 4:
            out["full_only_over_pager"].append((paged, full, grep))
        if p_rel and not as_bool(paged.get("correct")) and len(out["formatting_save"]) < 4:
            out["formatting_save"].append((paged, full, grep))
    return out


def render_examples(examples: dict[str, list[tuple[dict[str, str], dict[str, str] | None, dict[str, str] | None]]], target_arm: str) -> str:
    if not any(examples.values()):
        return f"<p>No example rows yet, or no {esc(target_arm or 'target')} rows were present.</p>"
    labels = {
        "pager_only": f"{target_arm}-only relaxed wins",
        "full_only_over_pager": f"Full-context wins over {target_arm}",
        "formatting_save": "Strict marked wrong but relaxed accepts",
    }
    parts: list[str] = []
    for key, title in labels.items():
        rows = examples.get(key, [])
        if not rows:
            continue
        parts.append(f"<h3>{esc(title)}</h3>")
        parts.append(f"<table><thead><tr><th>Task</th><th>Dataset</th><th>Gold</th><th>{esc(target_arm)} answer</th><th>Full answer</th><th>Grep answer</th></tr></thead><tbody>")
        for paged, full, grep in rows:
            parts.append(
                f"<tr><td>{esc(paged.get('original_task_id'))}</td><td>{esc(paged.get('benchmark'))}/{esc(paged.get('source_task'))}</td>"
                f"<td>{esc(paged.get('gold_answer'))}</td><td>{esc(paged.get('agent_answer'))}</td>"
                f"<td>{esc((full or {}).get('agent_answer',''))}</td><td>{esc((grep or {}).get('agent_answer',''))}</td></tr>"
            )
        parts.append("</tbody></table>")
    return "\n".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
