"""Temporary P1.15 event-context observation writer and report renderer."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from statistics import mean
from typing import Any

METRICS_RELATIVE_PATH = Path(".shipwright/compliance/context-cost/events-context-metrics.jsonl")
REPORT_RELATIVE_PATH = Path(".shipwright/compliance/context-cost/events-context-report.md")
ROLLING_WINDOW = 10


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def render_report(rows: list[dict[str, Any]]) -> str:
    latest = rows[-1] if rows else {}
    rolling = rows[-ROLLING_WINDOW:]
    averages = {
        key: mean(float(row.get(key, 0)) for row in rolling) if rolling else 0
        for key in ("full_count", "full_bytes", "full_estimated_tokens", "selected_count",
                    "selected_bytes", "selected_estimated_tokens", "reduction_percentage")
    }
    fallbacks = latest.get("fallbacks", []) or []
    observation_label = "observation" if len(rolling) == 1 else "observations"
    lines = [
        "# Events context cost",
        "",
        "> Temporary P1.15 observation output. It is generated for the operator and is not an agent startup input.",
        "",
        "## Latest iterate",
        "",
        f"- **Run:** `{latest.get('run_id', 'none')}`",
        f"- **Mode:** `{latest.get('mode', 'none')}`",
        f"- **Reduction:** {_fmt(latest.get('reduction_percentage', 0))}%",
        f"- **Selected:** {latest.get('selected_count', 0)} of {latest.get('full_count', 0)} events; "
        f"{latest.get('selected_estimated_tokens', 0)} of {latest.get('full_estimated_tokens', 0)} estimated tokens",
        f"- **Queries / truncations / fallbacks:** {latest.get('query_count', 0)} / "
        f"{latest.get('truncations', 0)} / {len(fallbacks)}",
        f"- **Fallbacks:** {', '.join(fallbacks) if fallbacks else 'none'}",
        "",
        f"## Rolling values (last {len(rolling)} {observation_label})",
        "",
        "| Measure | Latest | Rolling average |",
        "|---|---:|---:|",
    ]
    for label, key in (
        ("Full events", "full_count"), ("Full bytes", "full_bytes"),
        ("Full estimated tokens", "full_estimated_tokens"),
        ("Selected events", "selected_count"), ("Selected bytes", "selected_bytes"),
        ("Selected estimated tokens", "selected_estimated_tokens"),
        ("Reduction %", "reduction_percentage"),
    ):
        lines.append(f"| {label} | {_fmt(latest.get(key, 0))} | {_fmt(averages[key])} |")
    note = "Counts are measured from the raw log and the emitted structured event payload. "
    note += "Estimated tokens use the deterministic `ceil(bytes / 4)` approximation."
    lines.extend(["", note, ""])
    return "\n".join(lines)


def record_metric(project_root: Path | str, metric: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(project_root)
    metrics_path = root / METRICS_RELATIVE_PATH
    report_path = root / REPORT_RELATIVE_PATH
    rows = [row for row in _read_rows(metrics_path) if row.get("run_id") != metric.get("run_id")]
    rows.append(metric)
    text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
    _atomic_text(metrics_path, text)
    _atomic_text(report_path, render_report(rows))
    return metrics_path, report_path
