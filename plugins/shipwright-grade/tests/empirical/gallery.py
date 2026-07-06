"""gallery — render the empirical run's report gallery + summary index.

Per repo: the grader's OWN self-contained ``render_html`` report (the launch
material). Plus a small index page (repo → grade → expected → pass/fail, linking
each report) and a plaintext summary table for the console. The gallery is a CI
**artifact**, never committed — so it carries a wall-clock stamp and is written to
a caller-supplied out dir.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from html_report import render_html
from report_model import ReportModel

from replay import _safe_key


@dataclass(frozen=True)
class SummaryRow:
    name: str
    band: str
    expected: str
    outcome: str  # "pass" | "FAIL" | "robust" (edge case: graded, no band asserted)
    score: float | None
    report_file: str


def report_filename(name: str) -> str:
    return f"{_safe_key(name)}.html"


def write_report(name: str, model: ReportModel, out_dir: Path, *, generated_at: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / report_filename(name)
    path.write_text(render_html(model, generated_at=generated_at), encoding="utf-8")
    return path


def _score_cell(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.1f}"


def summary_table(rows: list[SummaryRow]) -> str:
    """A fixed-width console table (repo · grade · expected · score · outcome)."""
    header = f"{'repo':<32} {'grade':<6} {'expected':<9} {'score':<7} outcome"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.name[:32]:<32} {r.band:<6} {r.expected or '—':<9} "
            f"{_score_cell(r.score):<7} {r.outcome}")
    return "\n".join(lines)


_INDEX_CSS = (
    "body{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#0f172a;"
    "background:#f8fafc}h1{font-size:1.4rem}table{border-collapse:collapse;"
    "width:100%;max-width:52rem}th,td{padding:.5rem .7rem;border-bottom:1px "
    "solid #e2e8f0;text-align:left}.fail{color:#b91c1c;font-weight:600}"
    ".pass{color:#15803d;font-weight:600}.robust{color:#64748b}"
    "a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}"
)


def write_index(rows: list[SummaryRow], out_dir: Path, *, generated_at: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    body = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>shipwright-grade — empirical calibration gallery</title>",
        f"<style>{_INDEX_CSS}</style></head><body>",
        "<h1>shipwright-grade — empirical calibration gallery</h1>",
        f"<p>Real OSS repos, pinned to a commit SHA. Generated {html.escape(generated_at)}.</p>",
        "<table><thead><tr><th>Repo</th><th>Grade</th><th>Expected</th>",
        "<th>Score</th><th>Outcome</th></tr></thead><tbody>",
    ]
    for r in rows:
        cls = {"pass": "pass", "FAIL": "fail"}.get(r.outcome, "robust")
        # Link only when a report file was actually written for this row
        # (edge/robust rows have none → plain text, never a dead 404 link).
        name_cell = (f"<a href='{html.escape(r.report_file)}'>{html.escape(r.name)}</a>"
                     if r.report_file else html.escape(r.name))
        body.append(
            f"<tr><td>{name_cell}</td><td>{html.escape(r.band)}</td>"
            f"<td>{html.escape(r.expected or '—')}</td><td>{_score_cell(r.score)}</td>"
            f"<td class='{cls}'>{html.escape(r.outcome)}</td></tr>")
    body.append("</tbody></table></body></html>\n")
    path = out_dir / "index.html"
    path.write_text("".join(body), encoding="utf-8")
    return path
