"""Test Evidence Report generator.

Produces .shipwright/compliance/test-evidence.md with per-section test results,
test execution summary (unit/smoke/e2e), and links to specs and test files.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.mermaid import testing_pyramid_diagram

# Cross-cutting markdown helper lives at shared/scripts/markdown_table.py
# (outside the `lib/` namespace per ADR-045 so it can be imported here
# without colliding with this plugin's own `lib/` regular package).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from markdown_table import escape_cell  # noqa: E402

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def generate(data: ComplianceData) -> str:
    """Generate Test Evidence Report as Markdown string."""
    lines = [
        "# Test Evidence Report",
        "",
        f"Generated: {data.timestamp}",
        "",
    ]

    # Use event-based generation if events exist
    if data.work_events:
        lines.extend(_test_progression(data))
        # Iterate-2026-05-21-empirical-followups AC-2: when no explicit
        # test_run events exist on the wire (the common case empirically
        # — both shipwright and webui carry zero today), synthesize the
        # Full Suite Runs table from work_completed events instead of
        # silently omitting the section. test_run-based rendering wins
        # when present (canonical 4-layer breakdown). Synthesis branch
        # is gated on BOTH (a) no test_runs AND (b) at least one
        # qualifying work_event — gate is explicit at the call site
        # (code-review OpenAI finding #2) so reading `generate()` makes
        # the fallback condition obvious.
        if data.test_runs:
            lines.extend(_full_suite_runs(data))
        elif any(we.tests_total > 0 for we in data.work_events):
            lines.extend(_full_suite_runs_from_work_events(data))
        # else: no test_runs AND no qualifying work_events — emit nothing
        # (matches prior behavior: `_full_suite_runs(data)` returned `[]`).
        lines.extend(_e2e_details(data))
        lines.extend(_code_review_evidence_events(data))
    else:
        # Legacy fallback
        lines.extend(_test_execution_summary(data))
        lines.extend([
            "## Test Pyramid",
            "",
            testing_pyramid_diagram(data.sections, data.test_results),
            "",
        ])
        lines.extend(_per_split_results(data))
        lines.extend(_e2e_details(data))
        lines.extend(_code_review_evidence(data))

    return "\n".join(lines) + "\n"


def _test_execution_summary(data: ComplianceData) -> list[str]:
    """Generate test execution summary table with all three layers."""
    total_passed = sum(s.tests_passed for s in data.sections)
    total_tests = sum(s.tests_total for s in data.sections)
    total_findings = sum(s.review_findings for s in data.sections)
    total_fixed = sum(s.review_findings_fixed for s in data.sections)
    sections_reviewed = len(data.sections)

    lines = [
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total sections tested | {len(data.sections)} |",
        f"| Unit tests passed | {total_passed} |",
        f"| Unit tests failed | {total_tests - total_passed} |",
        f"| Code review sections | {sections_reviewed}/{len(data.sections)} |",
        f"| Review findings total | {total_findings} |",
        f"| Review findings fixed | {total_fixed} |",
    ]

    tr = data.test_results
    if tr:
        lines.extend([
            "",
            "## Test Execution Summary",
            "",
            "| Layer | Status | Passed | Total | Duration | Details |",
            "|-------|--------|--------|-------|----------|---------|",
        ])

        # Unit
        unit_status = "PASS" if tr.unit_passed == tr.unit_total and tr.unit_total > 0 else "FAIL"
        if tr.unit_total == 0:
            unit_status = "SKIP"
        lines.append(
            f"| Unit | {unit_status} | {tr.unit_passed} | {tr.unit_total} "
            f"| {tr.unit_duration_s}s | Vitest |"
        )

        # Integration
        if tr.integration_skipped:
            int_status = "SKIP"
            int_detail = tr.integration_skip_reason or "skipped"
            lines.append(f"| Integration | {int_status} | — | — | — | {escape_cell(int_detail)} |")
        elif tr.integration_total > 0:
            int_status = "PASS" if tr.integration_passed == tr.integration_total else "FAIL"
            lines.append(
                f"| Integration | {int_status} | {tr.integration_passed} | {tr.integration_total} "
                f"| {tr.integration_duration_s}s | Vitest (real DB) |"
            )
        else:
            lines.append("| Integration | — | 0 | 0 | — | not configured |")

        # pgTAP
        if tr.pgtap_skipped:
            pgtap_status = "SKIP"
            pgtap_detail = tr.pgtap_skip_reason or "skipped"
            lines.append(f"| pgTAP | {pgtap_status} | — | — | — | {escape_cell(pgtap_detail)} |")
        elif tr.pgtap_total > 0:
            pgtap_status = "PASS" if tr.pgtap_passed == tr.pgtap_total else "FAIL"
            lines.append(
                f"| pgTAP | {pgtap_status} | {tr.pgtap_passed} | {tr.pgtap_total} "
                f"| {tr.pgtap_duration_s}s | supabase test db |"
            )

        # Smoke
        smoke_status = tr.smoke_status.upper() if tr.smoke_status else "—"
        smoke_detail = f"GET {tr.smoke_url}" if tr.smoke_url else "—"
        if tr.smoke_response_ms:
            smoke_detail += f" ({tr.smoke_response_ms}ms)"
        lines.append(
            f"| Smoke | {smoke_status} | — | — | — | {escape_cell(smoke_detail)} |"
        )

        # E2E
        if tr.e2e_skipped:
            e2e_status = "SKIP"
            e2e_detail = tr.e2e_skip_reason or "skipped"
            lines.append(f"| E2E | {e2e_status} | — | — | — | {escape_cell(e2e_detail)} |")
        else:
            e2e_status = "PASS" if tr.e2e_passed == tr.e2e_total and tr.e2e_total > 0 else "FAIL"
            if tr.e2e_total == 0:
                e2e_status = "—"
            lines.append(
                f"| E2E | {e2e_status} | {tr.e2e_passed} | {tr.e2e_total} "
                f"| — | Playwright |"
            )

        # Design Fidelity
        if tr.design_fidelity_skipped:
            vis_status = "SKIP"
            vis_detail = tr.design_fidelity_skip_reason or "skipped"
            lines.append(f"| Design Fidelity | {vis_status} | — | — | — | {escape_cell(vis_detail)} |")
        elif tr.design_fidelity_total > 0:
            vis_status = "PASS" if tr.design_fidelity_passed == tr.design_fidelity_total else "WARNING"
            vis_detail = "Code-level mockup comparison"
            if tr.design_fidelity_report_path:
                vis_detail += f" ([detail](design-fidelity-report.json))"
            lines.append(
                f"| Design Fidelity | {vis_status} | {tr.design_fidelity_passed} | {tr.design_fidelity_total} "
                f"| — | {escape_cell(vis_detail)} |"
            )

        # Consistency
        if tr.consistency_skipped:
            cons_status = "SKIP"
            cons_detail = tr.consistency_skip_reason or "skipped"
            lines.append(f"| Consistency | {cons_status} | — | — | — | {escape_cell(cons_detail)} |")
        elif tr.consistency_total > 0:
            cons_status = "PASS" if tr.consistency_passed == tr.consistency_total else "WARNING"
            lines.append(
                f"| Consistency | {cons_status} | {tr.consistency_passed} | {tr.consistency_total} "
                f"| — | Cross-page UI check |"
            )

        lines.append("")
    else:
        lines.extend([
            "",
            "_No test execution results found. Run `/shipwright-test` to generate `shipwright_test_results.json`._",
            "",
        ])

    return lines


def _per_split_results(data: ComplianceData) -> list[str]:
    """Per-split test results with layer breakdown and section summary."""
    if not data.sections:
        return []

    lines = ["## Per-Split Results", ""]

    # Group sections by split
    splits_seen: dict[str, list] = {}
    for sec in data.sections:
        splits_seen.setdefault(sec.split, []).append(sec)

    # Read per-split E2E results if available
    split_e2e = _collect_split_e2e_results(data.project_root)

    for split_name, sections in splits_seen.items():
        unit_passed = sum(s.tests_passed for s in sections)
        unit_total = sum(s.tests_total for s in sections)
        total_sections = len(sections)
        complete_sections = sum(1 for s in sections if s.status == "complete")
        total_findings = sum(s.review_findings for s in sections)
        review_types = {s.review_type for s in sections if s.review_type}
        review_label = ", ".join(sorted(review_types)) if review_types else "—"

        # E2E data for this split
        e2e_info = split_e2e.get(split_name, {})
        e2e_passed = e2e_info.get("passed", 0)
        e2e_total = e2e_info.get("total", 0)

        lines.append(f"### Split: {split_name}")
        lines.append("")
        lines.append("| Layer | Passed | Total | Status |")
        lines.append("|-------|--------|-------|--------|")

        # Unit layer
        if unit_total > 0:
            u_status = "PASS" if unit_passed == unit_total else "FAIL"
        else:
            u_status = "—"
        lines.append(f"| Unit | {unit_passed} | {unit_total} | {u_status} |")

        # E2E layer (if data available)
        if e2e_total > 0:
            e_status = "PASS" if e2e_passed == e2e_total else "WARNING"
            lines.append(f"| E2E | {e2e_passed} | {e2e_total} | {e_status} |")
        else:
            lines.append("| E2E | — | — | — |")

        lines.append("")
        lines.append(
            f"Sections: {complete_sections}/{total_sections} complete "
            f"| Review: {review_label} ({total_findings} findings)"
        )
        lines.append("")

    return lines


def _collect_split_e2e_results(project_root: Path) -> dict[str, dict]:
    """Read per-split E2E results from archived and current test results.

    Returns: {"01-foundation": {"passed": 6, "total": 7}, ...}
    Maps split number prefixes from spec filenames to split names.
    """
    import json

    result: dict[str, dict] = {}

    # Get split names from project config
    project_config_path = project_root / "shipwright_project_config.json"
    split_names: dict[str, str] = {}  # "01" -> "01-foundation"
    if project_config_path.exists():
        try:
            config = json.loads(project_config_path.read_text(encoding="utf-8"))
            for split in config.get("splits", []):
                name = split.get("name", "")
                if len(name) >= 2:
                    split_names[name[:2]] = name
        except (json.JSONDecodeError, OSError):
            pass

    # Current test results have aggregate E2E — distribute to last split
    current = project_root / "shipwright_test_results.json"
    if current.exists():
        try:
            data = json.loads(current.read_text(encoding="utf-8"))
            e2e = data.get("e2e", {})
            if e2e.get("total", 0) > 0:
                # E2E tests run after all splits — assign to project-level
                # For now, report as aggregate across all splits
                result["_aggregate"] = {
                    "passed": e2e.get("passed", 0),
                    "total": e2e.get("total", 0),
                }
        except (json.JSONDecodeError, OSError):
            pass

    return result


def _e2e_details(data: ComplianceData) -> list[str]:
    """E2E test failure details and Playwright report link."""
    lines: list[str] = []

    # Playwright HTML report link
    report_path = data.project_root / "playwright-report" / "index.html"
    if report_path.exists():
        lines.extend([
            "## Playwright Report",
            "",
            "**Interactive E2E report:** [playwright-report/index.html](../../playwright-report/index.html)",
            "",
        ])

    # Failure details
    tr = data.test_results
    if tr and not tr.e2e_skipped and tr.e2e_failures:
        lines.extend(["## E2E Test Failures", ""])
        for failure in tr.e2e_failures:
            lines.append(f"- {failure}")
        lines.append("")

    return lines


def _code_review_evidence(data: ComplianceData) -> list[str]:
    """Code review evidence table."""
    if not data.sections:
        return []

    _REVIEW_LABELS = {
        "full-review": "Full review",
        "self-review": "Self-review only",
    }

    lines = [
        "## Code Review Evidence",
        "",
        "| Section | Review Type | Findings | Fixed | Deferred | Status |",
        "|---------|-------------|----------|-------|----------|--------|",
    ]
    for sec in data.sections:
        review_label = _REVIEW_LABELS.get(sec.review_type, "Unknown")
        deferred = sec.review_findings - sec.review_findings_fixed
        if sec.review_type == "self-review":
            status = "SELF-REVIEW"
        elif deferred == 0:
            status = "PASS"
        else:
            status = "OPEN"
        lines.append(
            f"| {escape_cell(sec.name)} | {escape_cell(review_label)} "
            f"| {sec.review_findings} | {sec.review_findings_fixed} "
            f"| {deferred} | {status} |"
        )
    lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Event-based generation
# ---------------------------------------------------------------------------

def _test_progression(data: ComplianceData) -> list[str]:
    """Test progression timeline from work events."""
    if not data.work_events:
        return []

    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]
    new_from_iterate = sum(we.tests_new for we in iterate_events)

    # Latest test counts
    latest = data.work_events[-1]

    lines = [
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total test checkpoints | {len(data.work_events)} |",
        f"| Total unit tests (latest) | {latest.tests_passed}/{latest.tests_total} |",
    ]

    if data.test_runs:
        last_run = data.test_runs[-1]
        lines.append(f"| Total E2E tests (latest) | {last_run.e2e_passed}/{last_run.e2e_total} |")

    if new_from_iterate:
        lines.append(f"| New tests from iterations | +{new_from_iterate} |")

    lines.extend([
        "",
        "## Test Progression",
        "",
        "| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |",
        "|---|-------|--------|-------|-----------|-------------|--------|------|",
    ])

    for i, we in enumerate(reversed(data.work_events), 1):
        name = we.section if we.source == "build" else (we.description or we.id)
        source = we.source
        layer = _classify_work_event_layer(we)

        # New tests display
        if we.source == "iterate":
            new_parts = []
            if we.tests_new:
                new_parts.append(f"+{we.tests_new}")
            if we.tests_modified:
                new_parts.append(f"{we.tests_modified} mod")
            new_cell = ", ".join(new_parts) if new_parts else "+0"
        else:
            new_cell = f"+{we.tests_total}" if we.tests_total > 0 else "—"

        suite = f"{we.tests_passed}/{we.tests_total}" if we.tests_total > 0 else "—"
        baseline = data.baseline_failure_count
        if we.tests_passed == we.tests_total and we.tests_total > 0:
            result = "PASS"
        elif we.tests_total > 0 and baseline > 0 and (we.tests_total - we.tests_passed) <= baseline:
            result = "PASS (baseline)"
        elif we.tests_total > 0:
            result = "FAIL"
        else:
            result = "—"
        date = we.timestamp[:10]

        lines.append(
            f"| {i} | {escape_cell(name)} | {escape_cell(source)} "
            f"| {escape_cell(layer)} | {escape_cell(new_cell)} | {escape_cell(suite)} "
            f"| {escape_cell(result)} | {escape_cell(date)} |"
        )

    lines.append("")
    return lines


def _classify_work_event_layer(we) -> str:
    """Classify which test layers a work_completed event exercised.

    Iterate B.3 (ADR-057): solo-dev quick-read column on the Test
    Progression table. Derived from the existing ``tests`` block —
    no new event field. Heuristic:

    - ``e2e_run=True`` and ``tests.total > 0`` → ``"mixed"``
    - ``e2e_run=True`` only                    → ``"e2e"``
    - ``tests.total > 0`` only                 → ``"unit"``
    - otherwise                                → ``"—"``

    Integration / pgtap layers don't land on per-event work-completed
    records today; they only appear on full-suite ``test_run`` events
    where the Full Suite Runs table already breaks them out. Promoting
    them to per-work-event granularity is deferred (would require a
    new ``tests.layers`` array on the work_completed wire format).
    """
    has_unit = we.tests_total > 0
    has_e2e = bool(we.e2e_run)
    if has_unit and has_e2e:
        return "mixed"
    if has_e2e:
        return "e2e"
    if has_unit:
        return "unit"
    return "—"


def _full_suite_runs(data: ComplianceData) -> list[str]:
    """Full test suite runs from test_run events.

    Iterate B.3 (ADR-057): the table now splits a 4-layer breakdown
    (Unit / Integration / pgTAP / E2E) sourced from the new
    ``layers.integration`` and ``layers.pgtap`` keys on test_run events.
    Old events that don't carry them render as ``—``.
    """
    if not data.test_runs:
        return []

    lines = [
        "## Full Suite Runs",
        "",
        "| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |",
        "|-----|---------|------|-------------|-------|-----|-------|------|",
    ]

    for i, tr in enumerate(data.test_runs, 1):
        unit = f"{tr.unit_passed}/{tr.unit_total}" if tr.unit_total > 0 else "—"
        integration = (
            f"{tr.integration_passed}/{tr.integration_total}"
            if tr.integration_total > 0 else "—"
        )
        pgtap = (
            f"{tr.pgtap_passed}/{tr.pgtap_total}"
            if tr.pgtap_total > 0 else "—"
        )
        e2e = f"{tr.e2e_passed}/{tr.e2e_total}" if tr.e2e_total > 0 else "—"
        smoke = tr.smoke_status or "—"
        date = tr.timestamp[:10]
        trigger = tr.trigger or "—"

        lines.append(
            f"| {i} | {escape_cell(trigger)} | {escape_cell(unit)} "
            f"| {escape_cell(integration)} | {escape_cell(pgtap)} "
            f"| {escape_cell(e2e)} | {escape_cell(smoke)} | {escape_cell(date)} |"
        )

    lines.append("")
    return lines


_SYNTHESIS_CAP = 30
_DASH = "—"


def _full_suite_runs_from_work_events(data: ComplianceData) -> list[str]:
    """Synthesize the Full Suite Runs table from work_completed events.

    Iterate-2026-05-21-empirical-followups AC-2. Fallback for the common
    empirical case where no `test_run`-type events have been recorded on
    the wire (verified on both shipwright and webui: zero `test_run`
    events in `shipwright_events.jsonl`). Renders the same 8-column
    table shape as the test_run-based path so the section is structurally
    indistinguishable to operators.

    Selection semantics (per external-review OpenAI #3 + Gemini #5):

    1. Filter on ``we.tests_total > 0`` FIRST — zero-test events (pure
       docs / tooling iterates) don't qualify and don't consume the cap
       budget.
    2. Cap at the last 30 in `data.work_events` file order — preserves
       collector append order from `shipwright_events.jsonl`.

    Column mapping:

    - ``Run``: 1-based index after filter+cap.
    - ``Trigger``: ``we.source`` (`iterate` / `build`).
    - ``Unit``: ``we.tests_passed / we.tests_total``.
    - ``Integration`` / ``pgTAP`` / ``Smoke``: em-dash. The
      ``work_completed`` wire format doesn't carry these layers; the
      test_run path is the only producer that can populate them.
    - ``E2E``: em-dash ALWAYS in the synthesis branch. ``we.e2e_run``
      is a boolean signal without counts; promoting a boolean to a
      count would mislead operators. Documented limitation; a future
      iterate can lift this when real `test_run` events become routine
      (per OpenAI #2 in the plan review).
    - ``Date``: ``we.timestamp[:10]``.

    Returns ``[]`` (renders no section) when no qualifying events exist,
    matching the test_run path's empty-data behavior.
    """
    if not data.work_events:
        return []

    qualifying = [we for we in data.work_events if we.tests_total > 0]
    if not qualifying:
        return []

    # Cap at the last 30 in file order (filter-first per OpenAI #3).
    rows = qualifying[-_SYNTHESIS_CAP:]

    lines = [
        "## Full Suite Runs",
        "",
        "| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |",
        "|-----|---------|------|-------------|-------|-----|-------|------|",
    ]

    for i, we in enumerate(rows, 1):
        trigger = we.source or _DASH
        unit = f"{we.tests_passed}/{we.tests_total}"
        date = we.timestamp[:10] if we.timestamp else _DASH

        lines.append(
            f"| {i} | {escape_cell(trigger)} | {escape_cell(unit)} "
            f"| {_DASH} | {_DASH} "
            f"| {_DASH} | {_DASH} | {escape_cell(date)} |"
        )

    lines.append("")
    return lines


def _code_review_evidence_events(data: ComplianceData) -> list[str]:
    """Code review evidence from work events."""
    events_with_review = [we for we in data.work_events if we.review_type]
    if not events_with_review:
        return []

    _REVIEW_LABELS = {
        "full-review": "Full review",
        "self-review": "Self-review only",
    }

    lines = [
        "## Code Review Evidence",
        "",
        "| Event | Review Type | Findings | Fixed | Status |",
        "|-------|------------|----------|-------|--------|",
    ]

    for we in events_with_review:
        name = we.section if we.source == "build" else (we.description or we.id)
        review_label = _REVIEW_LABELS.get(we.review_type, we.review_type)
        deferred = we.review_findings - we.review_fixed
        if we.review_type == "self-review" and we.review_findings == 0:
            status = "PASS"
        elif deferred == 0:
            status = "PASS"
        else:
            status = "OPEN"

        lines.append(
            f"| {escape_cell(name)} | {escape_cell(review_label)} "
            f"| {we.review_findings} | {we.review_fixed} | {status} |"
        )

    lines.append("")
    return lines


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate Test Evidence Report and write to .shipwright/compliance/test-evidence.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test-evidence.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _format_findings(total: int, fixed: int) -> str:
    """Format review findings."""
    if total == 0:
        return "0"
    return f"{total} ({fixed} fixed)"


# ---------------------------------------------------------------------------
# Triage producer (Iterate B.3 / ADR-057)
# ---------------------------------------------------------------------------

_TRIAGE_SOURCE = "test-evidence"
_TRIAGE_DEDUP_PREFIX = "test-fail:"
_FAILURE_DETAIL_TOP_N = 10

# Layer → (severity, kind) per ADR-054 D3 layer-based default-action.
# e2e / integration / pgtap → "high" (Fix-now blocks merge for solo dev).
# unit → "low" (visible, still on the inbox top section, but quieter —
# unit-test rot is less merge-blocking than integration/e2e).
_LAYER_TRIAGE: dict[str, tuple[str, str]] = {
    "e2e":         ("high", "bug"),
    "integration": ("high", "bug"),
    "pgtap":       ("high", "bug"),
    "unit":        ("low",  "bug"),
}


def _import_triage_api():
    """Lazy import of triage helpers (mirrors sbom_generator pattern)."""
    if str(_SHARED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS))
    try:
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
        )
        return append_triage_item_idempotent, mark_status, read_all_items
    except ImportError:
        return None, None, None


def _failing_layers(tr) -> tuple[list[tuple[str, int, int, int]], set[str]]:
    """Return ``(failures, evaluated_layers)`` from the latest test_run.

    ``failures`` is a list of ``(layer, passed, total, failed)`` for
    every layer with ``failed > 0`` (explicit count when the producer
    supplied ``--<layer>-failed`` — reviewer-flagged Gemini-H1; falls
    back to ``total - passed`` only when ``failed`` is absent).
    ``evaluated_layers`` is the set of layer names that appeared in
    the event's ``layers`` dict at all, used to scope auto-dismiss
    (reviewer-flagged OpenAI-M6: an omitted layer is "unknown", not
    "green").

    ``smoke`` is handled separately — its semantic is a single status
    string, not a pass/total pair.
    """
    rows: list[tuple[str, int, int, int]] = []
    evaluated: set[str] = set()
    for layer, passed, total, failed, was_evaluated in (
        ("unit",        tr.unit_passed,        tr.unit_total,        tr.unit_failed,        tr.unit_evaluated),
        ("integration", tr.integration_passed, tr.integration_total, tr.integration_failed, tr.integration_evaluated),
        ("pgtap",       tr.pgtap_passed,       tr.pgtap_total,       tr.pgtap_failed,       tr.pgtap_evaluated),
        ("e2e",         tr.e2e_passed,         tr.e2e_total,         tr.e2e_failed,         tr.e2e_evaluated),
    ):
        if not was_evaluated:
            continue
        evaluated.add(layer)
        # Prefer explicit failed count; fall back to passed/total
        # delta only when failed is absent.
        actual_failed = failed if failed is not None else max(0, total - passed)
        if actual_failed > 0:
            rows.append((layer, passed, total, actual_failed))
    return rows, evaluated


# Iterate B.3 code-review-M1: strip newlines too — keeping `\n` defeats
# the markdown safety purpose because an embedded newline in a failure
# ID breaks the triage card layout. Whitespace runs collapse to one
# space so the rendered detail line stays single-row.
_CONTROL_CHARS = "".join(chr(c) for c in range(0, 32) if c != 9) + chr(127)


def _sanitize(text: str, max_len: int = 4096) -> str:
    """Strip control chars (incl. newlines/CR), collapse whitespace, cap length.

    Reviewer-flagged Gemini-L5 + OpenAI-M11 (spec review) +
    OpenAI-M1 (code review): test IDs and failure strings come from
    semi-untrusted output (test runners); they can contain ANSI,
    control chars, and embedded newlines that break the surrounding
    markdown render. We strip all `\\x00..\\x1f` (except tab) plus
    `\\x7f`, then collapse any remaining whitespace runs to single
    spaces. Length-capped to keep one pathological case from bloating
    the inbox.
    """
    if not isinstance(text, str):
        return ""
    # Replace control chars with a space so text fragments stay
    # separated (e.g. `foo\nbar` becomes `foo bar`, not `foobar`).
    clean = "".join(" " if c in _CONTROL_CHARS else c for c in text)
    # Collapse any whitespace run (incl. tabs) to one space.
    clean = " ".join(clean.split())
    if len(clean) > max_len:
        clean = clean[: max_len - 12] + "...(truncated)"
    return clean


def _failure_detail(layer: str, passed: int, total: int, failed: int, e2e_failures: list[str]) -> str:
    """Render a triage detail line for a failing layer.

    For the ``e2e`` layer, also include the top-10 failure IDs from
    ``shipwright_test_results.json`` (consumer of `data.test_results.e2e_failures`
    in `data_collector`); the other layers don't carry per-test
    failure lists on the wire yet, so the detail just states the count
    and refers the operator to `test-evidence.md` for the full picture.

    Failure IDs are sanitized via ``_sanitize`` to strip ANSI / control
    characters that test runners sometimes embed in failure messages.
    """
    if layer == "e2e" and e2e_failures:
        cleaned = sorted(_sanitize(f) for f in e2e_failures)
        shown = cleaned[:_FAILURE_DETAIL_TOP_N]
        extra = len(cleaned) - len(shown)
        footer = f" (+{extra} more)" if extra > 0 else ""
        # Wrap each ID in backticks so any residual markdown
        # metacharacters can't break the surrounding render.
        listed = "; ".join(f"`{x}`" for x in shown)
        return _sanitize(
            f"{failed}/{total} failing in {layer}. "
            f"Top {len(shown)}: {listed}{footer}"
        )
    return _sanitize(
        f"{failed}/{total} failing in {layer}. "
        f"See test-evidence.md for the full breakdown."
    )


def _layer_launch_payload(layer: str) -> str:
    """Render the layer-scoped Fix-now payload.

    ``/shipwright-iterate --type bug`` opens a fresh session pre-loaded
    with the failing-layer context. Solo dev pastes the fence content
    into the new session.
    """
    return (
        f"/shipwright-iterate --type bug\n"
        f"\n"
        f"Context: {layer} tests are red. Source: triage card test-fail:{layer}.\n"
        f"Fix the failing tests in the {layer} layer; "
        f"compliance auto-dismisses this card on the next clean run."
    )


def emit_test_failure_triage(
    project_root: Path,
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> dict:
    """Emit ``source="test-evidence"`` triage items per failing test layer.

    Iterate B.3 (ADR-057): closes ADR-054 D2/D3 on the producer side.
    Reads the latest ``test_run`` event from ``shipwright_events.jsonl``
    and emits one triage item per layer where ``passed < total``:

    - ``source = "test-evidence"``
    - ``dedup_key = "test-fail:<layer>"``
    - ``severity / kind`` from ``_LAYER_TRIAGE`` (high+bug for
      e2e/integration/pgtap; low+bug for unit)
    - ``event_id = <latest test_run event id>`` (dogfoods B0's
      cross-link field; the RTM consumer in B.4 reads this)
    - ``launchPayload = "/shipwright-iterate --type bug"`` with the
      failing-layer context inline

    Auto-dismiss: any currently-``triage`` ``source="test-evidence"``
    item whose ``dedupKey`` is NOT in this run's set of failing layers
    is marked ``dismissed`` with ``reason="testEvidenceResolved"``.
    Promoted / dismissed items stay terminal (HIGH-2 contract).

    Returns ``{"appended": N, "dismissed": N, "error"?: str}``.
    """
    project_root = Path(project_root).resolve()
    append_idempotent, mark_status_fn, read_all_items = _import_triage_api()
    if append_idempotent is None:
        return {
            "appended": 0,
            "dismissed": 0,
            "error": "triage_api_unavailable",
        }

    from scripts.lib.data_collector import collect_all
    data = collect_all(project_root)
    if not data.test_runs:
        # No test_run events recorded yet → no failures, no dismissals.
        return {"appended": 0, "dismissed": 0}

    # Latest = last in file order (collect_events preserves append order
    # from shipwright_events.jsonl). Reviewer-flagged OpenAI-M4: document
    # the selection rule so future refactors don't accidentally switch
    # to e.g. timestamp-based ordering.
    latest = data.test_runs[-1]
    failures, evaluated = _failing_layers(latest)
    e2e_failures = (
        data.test_results.e2e_failures
        if (data.test_results and data.test_results.e2e_failures) else []
    )

    appended = 0
    errors: list[str] = []
    current_keys: set[str] = set()
    # Reviewer-flagged OpenAI-M6: only dedup-keys for layers that were
    # actually evaluated in this run participate in the dismiss sweep;
    # an omitted layer is "unknown", not "green", and must not flip
    # its prior failure card to dismissed.
    evaluated_keys: set[str] = {
        f"{_TRIAGE_DEDUP_PREFIX}{layer}" for layer in evaluated
    }
    for layer, passed, total, failed in failures:
        dedup_key = f"{_TRIAGE_DEDUP_PREFIX}{layer}"
        current_keys.add(dedup_key)
        severity, kind = _LAYER_TRIAGE.get(layer, ("low", "bug"))
        title = f"Test failures in {layer} layer ({failed}/{total} failing)"
        detail = _failure_detail(layer, passed, total, failed, e2e_failures)
        payload = _layer_launch_payload(layer)
        try:
            new_id = append_idempotent(
                project_root,
                source=_TRIAGE_SOURCE,
                severity=severity,
                kind=kind,
                title=title[:160],
                detail=detail,
                dedup_key=dedup_key,
                run_id=run_id,
                commit=commit,
                match_commit=False,
                window_seconds=None,
                launch_payload=payload,
                event_id=latest.id or None,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            # Reviewer-flagged OpenAI-L12: do NOT include the full
            # exception message — could leak workspace paths. The
            # `{type(exc).__name__}` form keeps the surface minimal.
            errors.append(f"append:{layer}:{type(exc).__name__}")

    dismissed = 0
    try:
        for item in read_all_items(project_root):
            if item.get("source") != _TRIAGE_SOURCE:
                continue
            if item.get("status") != "triage":
                continue
            dk = item.get("dedupKey")
            if not isinstance(dk, str):
                continue
            if not dk.startswith(_TRIAGE_DEDUP_PREFIX):
                continue
            if dk in current_keys:
                continue
            if dk not in evaluated_keys:
                # Layer wasn't evaluated in the latest run → unknown,
                # not green. Leave the prior failure card open so the
                # operator can decide.
                continue
            try:
                mark_status_fn(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="testEvidence",
                    reason="testEvidenceResolved",
                )
                dismissed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"dismiss:{item.get('id', '?')}:{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"read_all:{type(exc).__name__}")

    result: dict = {"appended": appended, "dismissed": dismissed}
    if errors:
        result["error"] = "; ".join(errors)
    return result
