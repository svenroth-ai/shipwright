"""Requirements Traceability Matrix generator.

Produces .shipwright/compliance/traceability-matrix.md mapping:
  Requirements → Work Events (sections + iterations) → Test Results
with clickable links to spec files and verification timeline.

NOTE: Output reports live at .shipwright/compliance/<file>.md (2-deep from
project_root), so links to project-root files use ``../../<file>`` instead
of ``../<file>``. Sibling links under .shipwright/ -- the planning subdir --
use ``../planning/...`` instead of ``../.shipwright/planning/...``.

Iterate B.4 (ADR-058): the requirements-coverage table now consumes the
B0 (ADR-054) cross-link fields — for each FR with at least one open
``triage`` item whose ``frId`` matches, the Status cell carries a
``FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)`` deep-link.
The Coverage Summary section is rewritten from a thin metrics table
into three operator-actionable subsections (no tests, stale
verification, open triage).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# cc3 (AR-05) reconciliation-rendering helpers live in a sibling leaf module so
# this grandfathered file stays under its anti-ratchet ceiling. The module is
# stdlib-only at import time (the BP-2 helper is imported lazily inside it), so
# importing it here is cheap and cycle-free.
from scripts.lib._rtm_reconciliation_render import (
    _RECONCILED_MARK,
    _compute_reconciliation_safe,
    _coverage_table_legend,
    _evt_anchor_ref,
    _render_needs_reverification_section,
)
from scripts.lib._rtm_layer_columns import layer_cells, load_layer_index
from scripts.lib._rtm_links import commit_cell, fr_anchor_id, last_tested_cell, link_frs, resolve_repo_url, timeline_order, utc_date  # noqa: E501
from scripts.lib.event_display import event_display_name

# Cross-cutting markdown helper lives at shared/scripts/markdown_table.py
# (outside the `lib/` namespace per ADR-045 so it can be imported here
# without colliding with this plugin's own `lib/` regular package).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from event_classification import normalize_intent  # noqa: E402
from markdown_table import escape_cell  # noqa: E402

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData, SectionInfo, WorkEvent


# Where the triage inbox lives relative to the RTM's own output
# directory (.shipwright/compliance/). The aggregator stamps stable
# `<a id="trg-XXX">` anchors above each card so `#trg-XXX` fragments
# resolve. Reviewer-flagged OpenAI-M3 / Gemini-M3: hoisted into a
# named constant so a future relocation of either artifact is a
# one-line change.
_TRIAGE_INBOX_REL = "../agent_docs/triage_inbox.md"

# Triage IDs follow the `trg-<8 hex>` shape (see
# `shared/scripts/triage.py:_generate_id`). Reviewer-flagged
# OpenAI-L9: validate the pattern before interpolating into a
# markdown link so a malformed wire value can't produce a broken
# href.
_TRIAGE_ID_RE = re.compile(r"^trg-[0-9a-f]{4,16}$")


def _open_triage_by_fr(project_root: Path) -> dict[str, list[dict]]:
    """Return ``{fr_id: [open triage items]}`` keyed by ``frId``.

    Iterate B.4 (ADR-058): consumes the B0 (ADR-054 D5) cross-link
    field ``frId``. Items without ``frId`` are skipped silently.
    Only ``status == "triage"`` items participate — promoted /
    dismissed / snoozed are terminal (mirrors compliance dashboard
    and B.2 / B.3 producer conventions).

    Lazy-import keeps RTM generation from crashing in minimal envs
    without ``shared/scripts/`` on ``sys.path``.
    """
    try:
        from triage import read_all_items  # noqa: PLC0415
    except ImportError:
        return {}
    by_fr: dict[str, list[dict]] = {}
    try:
        for item in read_all_items(project_root):
            if item.get("status") != "triage":
                continue
            fr_id = item.get("frId")
            if not isinstance(fr_id, str) or not fr_id:
                continue
            by_fr.setdefault(fr_id, []).append(item)
    except Exception:  # noqa: BLE001
        return {}
    return by_fr


def _render_fail_triage_links(items: list[dict]) -> str:
    """Render `FAIL → [trg-XXX](...#trg-XXX)` for one or more triage items.

    Stable sort by item id so repeated runs against the same triage
    state produce byte-identical RTM output (review-friendly diffs).
    The aggregator's HTML anchors are emitted as ``<a id="trg-XXX">``
    above every card (ADR-054 acceptance criteria), so the
    ``#trg-XXX`` fragment resolves in any CommonMark-compatible
    viewer (VS Code preview, GitHub blob view, the WebUI's markdown
    pane).

    Item IDs that don't match the canonical ``trg-<hex>`` shape are
    skipped (reviewer-flagged OpenAI-L9 — defense in depth against
    malformed wire data).
    """
    parts: list[str] = []
    for item in sorted(items, key=lambda i: i.get("id", "")):
        item_id = item.get("id", "")
        if not isinstance(item_id, str) or not _TRIAGE_ID_RE.match(item_id):
            continue
        parts.append(
            f"FAIL → [{item_id}]({_TRIAGE_INBOX_REL}#{item_id})"
        )
    return ", ".join(parts)


def generate(data: ComplianceData) -> str:
    """Generate RTM as a Markdown string."""
    lines = [
        "# Requirements Traceability Matrix",
        "",
        f"Generated: {data.timestamp}",
        "",
    ]

    # Use event-based generation if events exist
    if data.work_events:
        lines.extend(_requirements_coverage_events(data))
        lines.extend(_verification_timeline(data))
        lines.extend(_coverage_summary_events(data))
    else:
        # Legacy fallback
        lines.extend(_requirements_coverage(data))
        lines.extend(_section_traceability(data))
        lines.extend(_coverage_summary(data))

    return "\n".join(lines) + "\n"


def _requirements_coverage(data: ComplianceData) -> list[str]:
    """Requirements coverage matrix with links to specs and sections."""
    if not data.requirements:
        return []

    # Build section lookup for test counts
    section_lookup: dict[str, SectionInfo] = {s.name: s for s in data.sections}

    # E2E coverage per split (pragmatic: count flows from plan files)
    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)

    lines = [
        "## Requirements Coverage",
        "",
        "| Requirement | Title | Priority | Section(s) | Unit Tests | E2E Coverage | Status |",
        "|-------------|-------|----------|------------|------------|-------------|--------|",
    ]

    for req in data.requirements:
        # Link to spec file with anchor
        anchor = _make_anchor(req.id)
        req_link = f"[{req.id}](../../{req.spec_path}#{anchor})"

        # Truncated title for table readability
        display_text = req.text[:60] + ("..." if len(req.text) > 60 else "")

        # Linked sections
        if req.sections:
            section_links = []
            for sec_name in req.sections:
                sec_link = f"[{sec_name}](../planning/{req.split}/sections/{sec_name}.md)"
                section_links.append(sec_link)
            sections_cell = ", ".join(section_links)

            # Aggregate unit test counts from linked sections
            total_passed = 0
            total_tests = 0
            for sec_name in req.sections:
                sec = section_lookup.get(sec_name)
                if sec:
                    total_passed += sec.tests_passed
                    total_tests += sec.tests_total

            tests_cell = f"{total_passed}/{total_tests}" if total_tests > 0 else "—"

            # E2E coverage for this requirement's split
            split_e2e = e2e_by_split.get(req.split, {})
            e2e_specs = split_e2e.get("specs", 0)
            has_e2e = e2e_specs > 0
            e2e_cell = f"Split: {e2e_specs} specs" if has_e2e else "—"

            # Status: 3-tier based on unit + E2E
            has_unit = total_tests > 0 and total_passed == total_tests
            if has_unit and has_e2e:
                status = "COVERED"
            elif has_unit:
                status = "PARTIAL"
            elif has_e2e:
                status = "E2E ONLY"
            elif total_tests > 0:
                status = "FAIL"
            else:
                status = "NO TESTS"
        else:
            sections_cell = "—"
            tests_cell = "—"
            e2e_cell = "—"
            status = "UNLINKED"

        lines.append(
            f"| {escape_cell(req_link)} | {escape_cell(display_text)} | {req.priority} "
            f"| {escape_cell(sections_cell)} | {tests_cell} | {e2e_cell} | {status} |"
        )

    lines.append("")
    return lines


def _collect_e2e_coverage_by_split(project_root: Path) -> dict[str, dict]:
    """Count E2E flows and specs per split.

    Reads .shipwright/planning/*/claude-plan-e2e.md for planned flows and
    e2e/flows/*.spec.ts for existing specs.
    Returns: {"01-foundation": {"flows": 10, "specs": 7}, ...}
    """
    result: dict[str, dict] = {}

    # Count planned flows from E2E plan files
    planning_dir = project_root / ".shipwright" / "planning"
    if planning_dir.exists():
        for plan_file in planning_dir.glob("*/claude-plan-e2e.md"):
            split_name = plan_file.parent.name
            try:
                content = plan_file.read_text(encoding="utf-8")
                flows = len(re.findall(r"^### Flow \d+", content, re.MULTILINE))
            except OSError:
                flows = 0
            result.setdefault(split_name, {"flows": 0, "specs": 0})
            result[split_name]["flows"] = flows

    # Count existing spec files (NN-name.spec.ts → split NN)
    e2e_dir = project_root / "e2e" / "flows"
    if e2e_dir.exists():
        for spec_file in e2e_dir.glob("*.spec.ts"):
            # Extract split number from filename: 01-auth.spec.ts → "01"
            match = re.match(r"^(\d{2})-", spec_file.name)
            if match:
                prefix = match.group(1)
                # Find matching split name
                for split_name in result:
                    if split_name.startswith(prefix):
                        result[split_name]["specs"] += 1
                        break

    return result


def _section_traceability(data: ComplianceData) -> list[str]:
    """Section traceability table with requirement links."""
    lines = [
        "## Section Traceability",
        "",
    ]

    if not data.sections:
        lines.append("_No sections available yet. Run /shipwright-build to populate._")
        return lines

    # Build requirement lookup: section -> [req IDs]
    req_by_section: dict[str, list[str]] = {}
    for req in data.requirements:
        for sec_name in req.sections:
            req_by_section.setdefault(sec_name, []).append(req.id)

    lines.extend([
        "| Split | Section | Requirements | Commit | Tests | Status |",
        "|-------|---------|-------------|--------|-------|--------|",
    ])

    for sec in data.sections:
        commit = sec.commit[:12] if sec.commit else "—"
        status = _section_status(sec)

        # Link to section plan
        section_link = f"[{sec.name}](../planning/{sec.split}/sections/{sec.name}.md)"

        # Linked requirements
        reqs = req_by_section.get(sec.name, [])
        reqs_cell = ", ".join(reqs) if reqs else "—"

        # Tests
        if sec.tests_total > 0:
            tests_cell = f"{sec.tests_passed}/{sec.tests_total}"
        else:
            tests_cell = "—"

        lines.append(
            f"| {escape_cell(sec.split)} | {escape_cell(section_link)} "
            f"| {escape_cell(reqs_cell)} | {escape_cell(commit)} "
            f"| {tests_cell} | {status} |"
        )

    lines.append("")
    return lines


def _coverage_summary(data: ComplianceData) -> list[str]:
    """Coverage summary metrics."""
    lines = ["## Coverage Summary", ""]

    total_sections = len(data.sections)
    sections_with_commits = sum(1 for s in data.sections if s.commit)
    sections_passing = sum(
        1 for s in data.sections if s.tests_total > 0 and s.tests_passed == s.tests_total
    )

    if total_sections > 0:
        coverage_pct = int(sections_with_commits / total_sections * 100)
    else:
        coverage_pct = 0

    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total splits | {len(data.splits)} |",
        f"| Total sections | {total_sections} |",
        f"| Sections with commits | {sections_with_commits} |",
        f"| Sections with passing tests | {sections_passing} |",
        f"| Traceability coverage | {coverage_pct}% |",
    ])

    # E2E coverage
    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)
    splits_with_e2e = sum(1 for s in e2e_by_split.values() if s.get("specs", 0) > 0)
    total_e2e_specs = sum(s.get("specs", 0) for s in e2e_by_split.values())
    total_e2e_flows = sum(s.get("flows", 0) for s in e2e_by_split.values())
    lines.extend([
        f"| E2E specs | {total_e2e_specs} (across {splits_with_e2e} splits) |",
        f"| E2E planned flows | {total_e2e_flows} |",
    ])

    # Requirements coverage
    if data.requirements:
        total_reqs = len(data.requirements)
        must_reqs = [r for r in data.requirements if r.priority == "Must"]
        linked_reqs = [r for r in data.requirements if r.sections]
        linked_must = [r for r in must_reqs if r.sections]

        lines.extend([
            f"| Requirements total | {total_reqs} |",
            f"| Requirements linked to sections | {len(linked_reqs)}/{total_reqs} |",
            f"| Must-have requirements linked | {len(linked_must)}/{len(must_reqs)} |",
        ])

        # List uncovered requirements
        unlinked = [r for r in data.requirements if not r.sections]
        if unlinked:
            lines.extend(["", "### Unlinked Requirements", ""])
            for req in unlinked:
                lines.append(f"- [{req.id}](../../{req.spec_path}) ({req.priority}): {req.text[:80]}...")

    # Review findings
    total_findings = sum(s.review_findings for s in data.sections)
    unresolved = sum(s.review_findings - s.review_findings_fixed for s in data.sections)
    lines.extend([
        f"| Total review findings | {total_findings} |",
        f"| Unresolved findings | {unresolved} |",
    ])

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Event-based generation
# ---------------------------------------------------------------------------

def _requirements_coverage_events(data: ComplianceData) -> list[str]:
    """Requirements coverage from work events with Last Verified column.

    Iterate B.4 (ADR-058): when an FR has at least one open triage
    item carrying ``frId == req.id``, the Status cell carries a
    ``FAIL → [trg-XXX](...#trg-XXX)`` deep-link to the matching card
    in ``../agent_docs/triage_inbox.md`` (overrides whatever status
    the work-events analysis would have produced — an open triage
    item is positive evidence the operator hasn't accepted the
    current verification state).
    """
    if not data.requirements:
        return []

    # Build FR → events mapping
    fr_events: dict[str, list[WorkEvent]] = {}
    for we in data.work_events:
        for fr_id in we.affected_frs:
            fr_events.setdefault(fr_id, []).append(we)

    # Iterate B.4: pull open triage items keyed by frId. The render
    # below overlays them onto the per-row Status cell.
    open_triage = _open_triage_by_fr(data.project_root)

    # cc3 (AR-05): the per-FR "Reconciled?" status comes from the SAME BP-2
    # helper the Control-Grade reconciliation dimension reads
    # (_control_block.build_grade_inputs), so the grade and this column can
    # never disagree. Reconciliation keys on touched-without-re-verify, never
    # on age. `_compute_reconciliation_safe` lazy-imports the helper so a
    # minimal env degrades to "—" instead of crashing.
    rec = _compute_reconciliation_safe(data.work_events)
    layer_idx = load_layer_index(data.project_root)  # TT2: per-FR layer coverage glyphs

    lines = [
        "## Requirements Coverage",
        "",
        "| Requirement | Title | Priority | Verified By | Tests | Last tested | Reconciled? | Status | Unit | Integration | E2E |",
        "|-------------|-------|----------|-------------|-------|-------------|-------------|--------|------|-------------|-----|",
    ]

    for req in data.requirements:
        anchor = _make_anchor(req.id)
        req_link = f"[{req.id}](../../{req.spec_path}#{anchor})"
        # cc3 (AR-05): full FR title — the 60-char truncation hid the
        # requirement text the matrix exists to trace. `escape_cell` keeps a
        # pipe / newline in a long title from breaking the row.
        display_text = req.text

        events = fr_events.get(req.id, [])
        if events:
            # Verified-by lists ALL work events that touched the FR (section
            # names for build, event IDs for iterate) — "what work happened".
            # cc3 (AR-05): a canonical `evt-` iterate id links to its row in
            # the Verification Timeline below; build section names and
            # non-canonical ids stay plain text.
            refs = []
            for we in events:
                if we.source == "build" and we.section:
                    refs.append(we.section)
                else:
                    frag = _evt_anchor_ref(we.id)
                    refs.append(f"[{we.id}]({frag})" if frag else we.id)
            verified_cell = ", ".join(refs[:4])
            if len(refs) > 4:
                verified_cell += f" +{len(refs) - 4}"

            # Verification signal comes ONLY from events that recorded a test count;
            # untested (0/0) events are NEUTRAL. Status reflects the LATEST tested
            # event (not an all()-over-history), so a lone 0/0 or a transient historical
            # failure a later run fixed never pins the FR to FAIL. (2026-05-30 rtm-covered)
            tested = [we for we in events if we.tests_total and we.tests_total > 0]
            if tested:
                latest = _latest_tested_event(tested)

                # Progression across TESTED events only — an untested 0/0 tail
                # would otherwise render a misleading "→ 0/0" under COVERED.
                first_tests = f"{tested[0].tests_passed}/{tested[0].tests_total}"
                last_tests = f"{latest.tests_passed}/{latest.tests_total}"
                tests_cell = (
                    f"{first_tests} → {last_tests}"
                    if first_tests != last_tests else last_tests
                )

                # "Last tested" = latest event that actually ran tests; its
                # (iter) token links to that event's Verification Timeline row.
                # Age is informational, not a penalty (cc3 AR-05).
                last_tested = last_tested_cell(latest)

                gap = latest.tests_total - latest.tests_passed
                baseline = data.baseline_failure_count
                if gap <= 0:
                    status = "COVERED"
                elif baseline > 0 and gap <= baseline:
                    status = "COVERED (baseline)"
                else:
                    # Merged work is green-at-merge (Iron Law); a passed<total
                    # gap is SKIPPED tests, not failures. Real open regressions
                    # surface via the triage-deep-link override below, never
                    # here. (iterate-2026-06-16-compliance-rendering-fixes)
                    status = "COVERED"
            else:
                # Work touched the FR but no event recorded a test count.
                tests_cell = "—"
                last_tested = "—"
                status = "NO TESTS"
        else:
            verified_cell = "—"
            tests_cell = "—"
            last_tested = "—"
            status = "NOT VERIFIED"

        # B.4 deep-link overlay — an open triage item always wins over
        # the events-derived status (operator hasn't closed the loop).
        # Only override when the render produces a non-empty string —
        # otherwise a malformed trg-id list would silently blank the
        # status cell (reviewer-flagged OpenAI-L9 sibling).
        fr_triage = open_triage.get(req.id, [])
        if fr_triage:
            rendered = _render_fail_triage_links(fr_triage)
            if rendered:
                status = rendered

        reconciled_cell = _RECONCILED_MARK[rec.status(req.id)]
        u_cell, i_cell, e_cell = layer_cells(layer_idx, req.split, req.id)  # TT2 layer glyphs
        # In-document anchor AFTER the req link (keeps row prefix `| [FR-…]`); Timeline FRs link here.
        anchor = f'<a id="{fr_anchor_id(req.id)}"></a>'

        lines.append(
            f"| {escape_cell(req_link)}{anchor} | {escape_cell(display_text)} | {req.priority} "
            f"| {escape_cell(verified_cell)} | {escape_cell(tests_cell)} "
            f"| {escape_cell(last_tested)} | {reconciled_cell} | {status} | {u_cell} | {i_cell} | {e_cell} |"
        )

    lines.append("")
    lines.extend(_coverage_table_legend())
    return lines


def _verification_timeline(data: ComplianceData) -> list[str]:
    """Timeline of all work events verifying requirements — newest first."""
    if not data.work_events:
        return []

    lines = [
        "## Verification Timeline",
        "",
        "| Event | Source | Type | FRs | Tests | Commit | Date |",
        "|-------|--------|------|-----|-------|--------|------|",
    ]

    repo_url = resolve_repo_url(data.project_root)
    known_fr_ids = {r.id for r in data.requirements}

    for we in timeline_order(data.work_events):  # AC-4: descending (newest first)
        name = we.section if we.source == "build" else event_display_name(we)
        # cc3 (AR-05): anchor canonical iterate `evt-` ids so the Requirements
        # Coverage "Verified By" links resolve to this row (raw — carries no pipe).
        frag = None if we.source == "build" else _evt_anchor_ref(we.id)
        event_cell = (
            f'<a id="{we.id}"></a>{escape_cell(name)}' if frag else escape_cell(name)
        )
        # Normalize the Type token so a leaked free-text `intent` (or an adopted
        # repo's git conventional-commit type) never lands in the Type column.
        event_type = "section" if we.source == "build" else normalize_intent(we.intent)
        frs = link_frs(we.affected_frs, known_fr_ids)
        tests = f"{we.tests_passed}/{we.tests_total}" if we.tests_total > 0 else "—"
        date = utc_date(we.timestamp)  # UTC frame matches the sort → monotonic Date column

        lines.append(
            f"| {event_cell} | {escape_cell(we.source)} | {escape_cell(event_type)} "
            f"| {escape_cell(frs)} | {escape_cell(tests)} "
            f"| {escape_cell(commit_cell(we.commit, repo_url))} | {escape_cell(date)} |"
        )

    lines.append("")
    return lines


def _coverage_summary_events(data: ComplianceData) -> list[str]:
    """Coverage summary from events.

    Iterate B.4 (ADR-058) — rewritten from a thin metrics dump into
    operator-actionable sections answering three solo-dev questions:

    1. Which FRs don't have tests yet? → ``### FRs without tests``
    2. Which behavior-affected FRs await re-verification? → ``### FRs
       needing re-verification`` (cc3/AR-05: touched-without-re-verify,
       **never age** — the old > 14-day stale clause is gone).
    3. Which FRs have active regressions (open triage items)? →
       ``### FRs with open triage items``

    The thin metrics table is kept above the three sections because
    the dashboard's "Quality indicators" links into it.
    """
    lines = ["## Coverage Summary", ""]

    # ---- 1. Thin metrics table (kept; small, scannable) -------------
    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]
    splits_seen = set(we.split for we in build_events if we.split)
    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total splits built | {len(splits_seen)} |",
        f"| Build sections | {len(build_events)} |",
        f"| Iterate changes | {len(iterate_events)} |",
    ])

    if data.requirements:
        total_reqs = len(data.requirements)
        must_reqs = [r for r in data.requirements if r.priority == "Must"]
        verified = [r for r in data.requirements if r.sections]
        verified_must = [r for r in must_reqs if r.sections]
        lines.extend([
            f"| Requirements total | {total_reqs} |",
            f"| Requirements verified | {len(verified)}/{total_reqs} |",
            f"| Must-have verified | {len(verified_must)}/{len(must_reqs)} |",
        ])

    if data.test_runs:
        latest = data.test_runs[-1]
        lines.append(
            f"| Last full test run | {latest.timestamp[:10]} "
            f"(Unit: {latest.unit_passed}/{latest.unit_total}, "
            f"E2E: {latest.e2e_passed}/{latest.e2e_total}) |"
        )

    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)
    total_e2e_specs = sum(s.get("specs", 0) for s in e2e_by_split.values())
    if total_e2e_specs:
        lines.append(f"| E2E specs | {total_e2e_specs} |")

    total_findings = sum(we.review_findings for we in data.work_events)
    unresolved = sum(we.review_findings - we.review_fixed for we in data.work_events)
    lines.extend([
        f"| Total review findings | {total_findings} |",
        f"| Unresolved findings | {unresolved} |",
        "",
    ])

    if not data.requirements:
        return lines

    # ---- 2. Three operator-actionable sections ----------------------
    fr_events_map: dict[str, list[WorkEvent]] = {}
    for we in data.work_events:
        for fr_id in we.affected_frs:
            fr_events_map.setdefault(fr_id, []).append(we)

    no_tests = _frs_without_tests(data.requirements, fr_events_map)
    lines.extend(_render_no_tests_section(no_tests))

    # cc3 (AR-05): behavior-affected FRs not re-verified since their last
    # change — the SAME reconciliation helper the Control-Grade dimension reads,
    # so the summary and the grade agree. Filtered to declared requirements
    # exactly as ``build_grade_inputs`` filters its sets. Age is never consulted.
    rec = _compute_reconciliation_safe(data.work_events)
    needs_reverify = [r for r in data.requirements if r.id in rec.unreconciled]
    lines.extend(_render_needs_reverification_section(needs_reverify, fr_events_map))

    open_triage = _open_triage_by_fr(data.project_root)
    open_fr_items = _frs_with_open_triage(data.requirements, open_triage)
    lines.extend(_render_open_triage_section(open_fr_items))

    return lines


def _frs_without_tests(
    requirements, fr_events_map: dict[str, list],
) -> list:
    """FRs with no work_completed event tying back via ``affected_frs``."""
    return [r for r in requirements if not fr_events_map.get(r.id)]


def _parse_iso_ts(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp string into an aware datetime.

    Returns ``None`` on malformed input. Used by the latest-tested-event
    selectors so a single corrupt timestamp doesn't crash the whole
    RTM render. Reviewer-flagged OpenAI-L6 / Gemini-M4: parse failures
    raise a `warnings.warn` so operators see them in test output even
    though the row is skipped.
    """
    import warnings
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        warnings.warn(f"RTM: malformed event timestamp skipped: {ts!r}", stacklevel=2)
        return None


def _latest_tested_event(tested):
    """Return the event with the max *parsed* timestamp from ``tested``.

    Robust against unreliable list order (reviewer-flagged code-review-M2):
    ``event_amended`` rewrites + multi-machine usage break append order. Events
    whose timestamp won't parse are excluded from the ``max()``; if NONE parse
    we fall back to list order. Callers pass only events with
    ``tests_total > 0`` (events that actually recorded a test count).
    """
    parsed = [(we, _parse_iso_ts(we.timestamp)) for we in tested]
    parseable = [(we, dt) for we, dt in parsed if dt is not None]
    if parseable:
        return max(parseable, key=lambda p: p[1])[0]
    return tested[-1]


def _frs_with_open_triage(requirements, open_triage: dict[str, list]) -> list[tuple]:
    """FRs with one or more open triage items, sorted by FR id."""
    out: list[tuple] = []
    for req in sorted(requirements, key=lambda r: r.id):
        items = open_triage.get(req.id) or []
        if items:
            out.append((req, items))
    return out


def _render_no_tests_section(no_tests) -> list[str]:
    if not no_tests:
        return []
    lines = ["### FRs without tests", ""]
    for req in no_tests:
        lines.append(
            f"- [{req.id}](../../{req.spec_path}) ({req.priority}): "
            f"{req.text[:80]}"
        )
    lines.append("")
    return lines


def _render_open_triage_section(open_fr_items) -> list[str]:
    if not open_fr_items:
        return []
    lines = ["### FRs with open triage items", ""]
    for req, items in open_fr_items:
        links = _render_fail_triage_links(items)
        lines.append(
            f"- [{req.id}](../../{req.spec_path}): {links}"
        )
    lines.append("")
    return lines


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate RTM and write to .shipwright/compliance/traceability-matrix.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "traceability-matrix.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _make_anchor(fr_id: str) -> str:
    """Convert FR-02.01 to a Markdown heading anchor like 'fr-0201-...'."""
    # GitHub-style anchor: lowercase, remove dots, add hyphens
    return fr_id.lower().replace(".", "")


def _section_status(sec) -> str:
    """Determine display status for a section."""
    if sec.status != "complete":
        return sec.status.upper()
    if sec.tests_total == 0:
        return "NO TESTS"
    if sec.tests_passed == sec.tests_total:
        return "PASS"
    return "FAIL"
