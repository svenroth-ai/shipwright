#!/usr/bin/env python3
"""Markdown rendering for the derived iterate-throughput report — no I/O.

Pure ``run_stats in -> markdown string out``, deterministic and reproducible
entirely from ``shipwright_events.jsonl`` (via ``iterate_throughput_stats``).
See ``tools/iterate_throughput_report.py`` for the orchestrating I/O.
"""

from __future__ import annotations

from lib.iterate_throughput_stats import ROLLING_WINDOW, rolling_percentiles
from lib.iterate_timings import FOLD_TIME_CAPTURABLE_SPANS, TOP_LEVEL_SPANS

_NESTED_CALLOUTS: tuple[str, ...] = (
    "pre_f0_validation", "f0_queue", "canonical_f0_active", "focused_tests",
    "self_review", "spec_review", "code_review", "doubt_review",
    "external_review", "reviewer_wait", "remediation",
    "ci_wait", "post_ci_remediation", "delivery_wait",
)


def _ms(value) -> str:
    if value is None:
        return "—"
    minutes = value / 60000.0
    return f"{minutes:.1f} min" if minutes >= 1 else f"{value / 1000.0:.1f} s"


def _pct(value) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _md_cell(value) -> str:
    """Escape a value for a markdown table cell — ``extra`` strings are
    closed-vocabulary but CLI-supplied (``--extra-json``), so a `|` or
    newline must not be able to break the table structure."""
    text = str(value).replace("|", "\\|").replace("\n", " ").replace("\r", "")
    return text


def render_run_section(stat: dict) -> list[str]:
    lines = [f"## Latest run: `{stat['run_id']}`", ""]
    if stat.get("pre_instrumentation"):
        lines += [
            ("**Pre-instrumentation run** — no `iterate_timings` recorded "
             "(predates this measurement). Not zero duration; simply not measured."),
            "",
        ]
        return lines
    if not stat.get("has_timings"):
        lines += ["**No timing data captured** for this run (all marks missed).", ""]
        return lines

    coverage = f"{stat['coverage_top_level']}/{stat['coverage_top_level_total']}"
    degraded = " — **DEGRADED** (a fold-time-capturable phase is missing)" if stat["degraded"] else ""
    derived_n = stat.get("derived_top_level", 0)
    derived_note = f" (+{derived_n} derived)" if derived_n else ""
    lines += [
        f"- **Timing source:** producer + agent spans (mixed) · "
        f"**coverage:** {coverage} fold-time-capturable groups{derived_note}, "
        f"{stat['span_count']} spans total{degraded}",
        f"- **Total wall-clock (discovery through review):** {_ms(stat['total_ms'])}",
        f"- **Unattributed:** {_ms(stat['unattributed_ms'])} ({_pct(stat['unattributed_pct'])})",
        f"- **Invalidation-driven restarts:** {stat['restarts']}",
        "",
        "### Top-level phases (inclusive / exclusive / % of total)",
        "",
        "| Phase | Inclusive | Exclusive | % of total |",
        "|---|---:|---:|---:|",
    ]
    for name in TOP_LEVEL_SPANS:
        p = stat["phases"].get(name, {"present": False})
        if not p.get("present"):
            if name in FOLD_TIME_CAPTURABLE_SPANS:
                # No process owns a top-level group boundary — an absent one
                # means the agent never emitted its start/end mark. The card's
                # own acceptance criterion is "unattributed WITH REASON, never
                # silently omitted" — a bare "not captured" doesn't say why
                # (external code review).
                lines.append(f"| {name} | *unattributed — no agent start/end marks recorded* | — | — |")
            else:
                # finalization/delivery structurally cannot close (or, for
                # delivery, cannot even exist) by F5b fold time in ANY run —
                # see the Coverage boundary callout. This is the expected
                # shape, not a missed mark.
                lines.append(f"| {name} | *not reached before F5b fold (structural)* | — | — |")
        elif p.get("duration_ms") is None or p.get("outcome") in ("incomplete", "unavailable"):
            # Present but unclosed/untrustworthy — a bare start mark or a
            # clock-regression span. Showing "—" here alone would be
            # indistinguishable from *not captured*; naming the outcome is
            # what keeps a partial run from reading as a clean one (external
            # code review). A derived-but-still-open envelope (one of its
            # referencing children never closed) is tagged the same way.
            tag = "derived, " if p.get("source") == "derived" else ""
            lines.append(f"| {name} | *{tag}{p.get('outcome') or 'incomplete'}* (started, not closed) | — | — |")
        elif p.get("source") == "derived":
            # No agent boundary mark exists for this group — the duration is
            # reconstructed from the envelope of its producer children (see
            # iterate_timings_synthesis.py), not a measured boundary. Shown,
            # not hidden, but labeled so it's never read as a real mark.
            lines.append(
                f"| {name} | {_ms(p['duration_ms'])} *(derived — reconstructed from child spans)* | "
                f"{_ms(p['exclusive_ms'])} | {_pct(p['pct'])} |"
            )
        else:
            lines.append(f"| {name} | {_ms(p['duration_ms'])} | {_ms(p['exclusive_ms'])} | {_pct(p['pct'])} |")

    nested_rows = []
    for name in _NESTED_CALLOUTS:
        entries = stat["nested"].get(name) or []
        for e in entries:
            extra_bits = ", ".join(
                f"{k}={_md_cell(v)}" for k, v in (e.get("extra") or {}).items()
            )
            nested_rows.append(
                f"| {name} | {e.get('parent')} | {_ms(e.get('duration_ms'))} | "
                f"{e.get('outcome')} | {extra_bits or '—'} |"
            )
    if nested_rows:
        lines += ["", "### Nested spans", "", "| Span | Parent | Duration | Outcome | Detail |",
                  "|---|---|---:|---|---|", *nested_rows]
    lines.append("")
    return lines


def render_rolling_section(run_stats: list[dict]) -> list[str]:
    timed = [s for s in run_stats if s.get("has_timings")]
    if len(timed) < 2:
        return ["## Rolling comparison", "",
               "Fewer than 2 instrumented runs — not enough samples for median/P90 yet.", ""]
    lines = [f"## Rolling comparison (last {min(len(timed), ROLLING_WINDOW)} instrumented runs)",
            "", "| Phase | Median exclusive | P90 exclusive | Samples |", "|---|---:|---:|---:|"]
    for name in TOP_LEVEL_SPANS:
        stats = rolling_percentiles(timed, field_path=("phases", name, "exclusive_ms"))
        if stats["n"] == 0:
            lines.append(f"| {name} | — | — | 0 |")
            continue
        median = _ms(stats["median"])
        p90 = _ms(stats.get("p90")) if "p90" in stats else "—"
        lines.append(f"| {name} | {median} | {p90} | {stats['n']} |")
    lines.append("")
    return lines


def render_history_section(run_stats: list[dict]) -> list[str]:
    lines = ["## Run history", "", "| Run | Total | Coverage | Restarts | Status |",
            "|---|---:|---:|---:|---|"]
    for stat in run_stats[-ROLLING_WINDOW:]:
        if stat.get("pre_instrumentation"):
            lines.append(f"| `{stat['run_id']}` | — | — | — | pre-instrumentation |")
            continue
        if not stat.get("has_timings"):
            lines.append(f"| `{stat['run_id']}` | — | — | — | no marks captured |")
            continue
        status = "degraded" if stat["degraded"] else "complete"
        cov = f"{stat['coverage_top_level']}/{stat['coverage_top_level_total']}"
        lines.append(f"| `{stat['run_id']}` | {_ms(stat['total_ms'])} | {cov} | "
                     f"{stat['restarts']} | {status} |")
    lines.append("")
    return lines


def render_report(run_stats: list[dict]) -> str:
    """``run_stats`` chronological (oldest first); the last entry is "latest"."""
    lines = [
        "# Iterate throughput", "",
        ("> Derived report — reproducible entirely from `shipwright_events.jsonl`. "
         "Not an agent startup input; regenerated at F5b. A missing agent mark is "
         "shown as *unattributed* with a reason, never as zero duration; the two "
         "structurally-limited groups (`finalization`, `delivery`) are labeled "
         "separately — see the Coverage boundary note below."),
        "",
        ("> **Derived spans:** a fold-time-capturable group with no agent "
         "start/end mark, but at least one producer child that names it as "
         "parent, is reconstructed from that child's own envelope and shown "
         "labeled *derived* rather than left unattributed — real duration "
         "data, not a measured boundary; it does not count toward coverage."),
        "",
        ("> **Coverage boundary:** F5b folds this report's durable data BEFORE F6 "
         "commits and F11 delivers — `discovery_diagnosis` through `review` can "
         "close by then, but `finalization`'s own duration and the entire "
         "`delivery` group (incl. `ci_wait`/`delivery_wait`/`post_ci_remediation`) "
         "structurally cannot, in every run. Coverage below is measured against "
         "the 5 groups that can — see `iterate-timings.md` for why."),
        "",
    ]
    if not run_stats:
        lines += ["No iterate `work_completed` events found yet.", ""]
        return "\n".join(lines)
    lines += render_run_section(run_stats[-1])
    lines += render_rolling_section(run_stats)
    lines += render_history_section(run_stats)
    return "\n".join(lines)
