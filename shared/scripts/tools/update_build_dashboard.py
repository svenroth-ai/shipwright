#!/usr/bin/env python3
"""Generate .shipwright/agent_docs/build_dashboard.md from pipeline state and event log.

Covers all pipeline phases (project through deploy), not just build.
Called by individual phase SKILLs at completion and by the Stop hook with status=paused.
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.config import collect_all_build_sections, read_config, read_events

STEP_LABELS = {
    1: "Read spec", 2: "Install deps", 3: "Write tests (red)",
    4: "Implement (green)", 5: "Refactor", 6: "Code review",
    7: "Apply fixes", 8: "Commit", 9: "Decision log",
    10: "Update state", 11: "Handoff check", 12: "Complete",
}

PIPELINE_PHASES = ["project", "design", "plan", "build", "test", "changelog", "compliance", "deploy"]


def _dashboard_header(now: str, sid: str, run_id: str | None) -> str:
    """The `> Updated: ... | Session: ...` banner line.

    When an iterate run_id is supplied (finalize_iterate F5b) it is
    appended as `| Run: {run_id}`. F5b renders the dashboard BEFORE the
    F6 commit + F7 event, so the new commit SHA cannot be in it — the
    run_id is the deterministic marker the finalization verifier
    (check_build_dashboard_has_run_id) keys on. Other callers (Stop hook,
    non-iterate phases) pass run_id=None and the line is unchanged.
    """
    line = f"> Updated: {now} | Session: {sid}"
    if run_id:
        line += f" | Run: {run_id}"
    return line


def format_status(section: dict, current_section: str | None, current_step: int | None, detail: str | None) -> str:
    """Format a section's status for the dashboard table."""
    name, status = section.get("name", "?"), section.get("status", "pending")
    if name == current_section and current_step:
        label = STEP_LABELS.get(current_step, f"step {current_step}")
        return f"**step {current_step}/12 — {label}**"
    return {"complete": "complete", "in_progress": "in_progress",
            "paused": "paused", "failed": "FAILED"}.get(status, "pending")


def _pipeline_status(run_config: dict, total_sections: int, completed_sections: int) -> str:
    """Format pipeline phase for the status column."""
    completed = set(run_config.get("completed_steps", []))
    current = run_config.get("current_step")
    in_split_loop = (current in ("plan", "build")
                     and "project" in completed and "design" in completed)

    def phase_status(phase: str) -> str:
        if in_split_loop and phase in ("test", "changelog", "deploy", "security"):
            return "pending"
        if phase in completed:
            return "complete"
        if phase == current:
            if phase == "build" and total_sections > 0:
                return f"**{completed_sections}/{total_sections} sections**"
            return "**in progress**"
        return "pending"
    return phase_status


def generate_pipeline_table(run_config: dict, total_sections: int, completed_sections: int) -> list[str]:
    """Generate the pipeline status table."""
    display_pipeline = list(PIPELINE_PHASES)
    for step in run_config.get("pipeline", []):
        if step not in display_pipeline:
            idx = display_pipeline.index("test") + 1 if step == "security" else len(display_pipeline)
            display_pipeline.insert(idx, step)
    pipeline = display_pipeline
    get_status = _pipeline_status(run_config, total_sections, completed_sections)
    lines = ["## Pipeline", "", "| Phase | Status |", "|-------|--------|"]
    for phase in pipeline:
        lines.append(f"| {phase.capitalize()} | {get_status(phase)} |")
    lines.append("")
    if run_config.get("status") == "needs_validation":
        for issue in run_config.get("validation_issues", []):
            lines.append(f"> **NEEDS DECISION — {issue.get('step', '?')}:** {issue.get('message', '')}")
        lines.append("")
    for note in run_config.get("validation_notes", []):
        lines.append(f"> **NOTE — {note.get('step', '?')}:** {note.get('message', '')}")
    if run_config.get("validation_notes"):
        lines.append("")
    return lines


def _generate_build_summary(all_sections: list[dict], completed_splits: list[str], total_splits: int) -> list[str]:
    """Generate a split summary table when all splits are done."""
    splits: dict[str, list[dict]] = {}
    for sec in all_sections:
        splits.setdefault(sec.get("split", "default"), []).append(sec)
    total_done = sum(1 for s in all_sections if s.get("status") == "complete")
    lines = [f"## Build Summary ({total_done}/{len(all_sections)} sections across {total_splits} splits)",
             "", "| Split | Sections | Unit Tests | Status |", "|-------|----------|-----------|--------|"]
    for split_name, secs in splits.items():
        sec_done = sum(1 for s in secs if s.get("status") == "complete")
        tp, tt = sum(s.get("tests_passed", 0) for s in secs), sum(s.get("tests_total", 0) for s in secs)
        test_str = f"{tp}/{tt}" if tt > 0 else "\u2014"
        lines.append(f"| {split_name} | {sec_done}/{len(secs)} | {test_str} | {'complete' if sec_done == len(secs) else 'in_progress'} |")
    lines.append("")
    return lines


def _generate_test_results(project_root: Path) -> list[str]:
    """Generate test results table from shipwright_test_results.json."""
    try:
        data = json.loads((project_root / "shipwright_test_results.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    lines = ["## Test Results", "", "| Layer | Passed | Total | Status |", "|-------|--------|-------|--------|"]
    for key, label in [("unit", "Unit"), ("integration", "Integration"), ("pgtap", "pgTAP"), ("smoke", "Smoke"), ("e2e", "E2E"), ("consistency", "Consistency"), ("design_fidelity", "Design Fidelity")]:
        layer = data.get(key, {})
        if layer.get("status") == "skip" or layer.get("skipped") is True:
            lines.append(f"| {label} | \u2014 | \u2014 | SKIP |")
        elif "passed" in layer and "total" in layer:
            p, t = layer["passed"], layer["total"]
            if t == 0: st = "SKIP"
            elif p == t: st = "PASS"
            elif label in ("E2E", "Consistency"): st = "WARNING"
            else: st = "FAIL"
            lines.append(f"| {label} | {p} | {t} | {st} |")
        else:
            lines.append(f"| {label} | \u2014 | \u2014 | SKIP |")
    lines.append("")
    return lines


def generate_dashboard(
    project_root: Path, phase: str | None = None, section: str | None = None,
    step: int | None = None, detail: str | None = None,
    status: str | None = None, session_id: str | None = None,
    run_id: str | None = None,
) -> str:
    """Generate dashboard markdown content. Uses events if available.

    ``run_id`` (optional) is embedded in the header by iterate finalization
    (F5b) so the finalization verifier has a deterministic marker.
    """
    # Try event-based generation first
    event_dashboard = _generate_from_events(
        project_root, session_id, section, step, detail, run_id
    )
    if event_dashboard is not None:
        return event_dashboard

    # Legacy: config-based generation
    run_config = read_config("run", project_root)
    build_info = collect_all_build_sections(project_root)
    sections = build_info["current"]
    total, completed = len(sections), sum(1 for s in sections if s.get("status") == "complete")
    all_sections = build_info["all"]
    total_all = len(all_sections)
    completed_all = sum(1 for s in all_sections if s.get("status") == "complete")
    current_split = build_info["current_split"]
    completed_splits, total_splits = build_info["completed_splits"], build_info["total_splits"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sid = session_id or os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")
    completed_steps = set(run_config.get("completed_steps", [])) if run_config else set()

    lines = ["# Shipwright Build Dashboard", _dashboard_header(now, sid, run_id), ""]
    if run_config:
        lines.extend(generate_pipeline_table(run_config, total_all, completed_all))
    if phase and detail:
        lines.append(f"> **Last update ({phase}):** {detail}")
        lines.append("")

    # Build Summary (all splits done) vs Section table (in progress)
    if "build" in completed_steps and total_splits > 1:
        lines.extend(_generate_build_summary(all_sections, completed_splits, total_splits))
    else:
        split_label = ""
        if current_split:
            splits_done = len(completed_splits)
            if total > 0 and completed == total:
                splits_done += 1
            split_label = f" — Split: {current_split} ({splits_done}/{total_splits} splits)"
        if total > 0:
            lines.append(f"## Build Sections ({completed}/{total} complete){split_label}")
        elif completed_splits and current_split and current_split not in completed_splits:
            lines.append(f"## Build Sections{split_label}")
            lines.append("")
            lines.append(f"Split **{current_split}** — awaiting `/shipwright-plan`. "
                          f"Previous splits: {', '.join(completed_splits)} (archived).")
        elif sections is not None and run_config:
            lines.append(f"## Build Sections{split_label}")
        lines.append("")
        if sections:
            lines.append("| # | Section | Status | Commit |")
            lines.append("|---|---------|--------|--------|")
            for i, sec in enumerate(sections, 1):
                lines.append(f"| {i} | {sec.get('name', '?')} | {format_status(sec, section, step, detail)} | {sec.get('commit', '--')} |")
            lines.append("")

    if "test" in completed_steps:
        lines.extend(_generate_test_results(project_root))

    if section:
        lines.append("## Current Activity")
        activity = f"Section: {section}"
        if step:
            activity += f" — {STEP_LABELS.get(step, f'step {step}')}"
        if detail:
            activity += f" ({detail})"
        lines.append(activity)
        lines.append("")

    # Resume / status info
    next_section = next((s.get("name") for s in sections if s.get("status") != "complete"), None)
    split_done = total > 0 and completed == total
    all_done = split_done and (len(completed_splits) + 1 >= total_splits if total_splits > 0 else True)

    if status == "paused" or (completed < total and total > 0 and not section):
        lines.append("## Resume Info")
        lines.append(f"Next: `/shipwright-run` (auto-resumes from {next_section})" if next_section else "Next: `/shipwright-run`")
        lines.append("")
    elif split_done and all_done:
        lines.append("## Status")
        lines.append("All sections complete. Ready for `/shipwright-test`.")
        lines.append("")
    elif split_done and not all_done:
        lines.append("## Status")
        lines.append(f"Split {current_split} complete. Next: `/shipwright-run` to start next split.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Event-based dashboard generation
# ---------------------------------------------------------------------------


def _read_iterate_test_results(project_root: Path) -> dict | None:
    """Read iterate_latest from shipwright_test_results.json."""
    try:
        data = json.loads((project_root / "shipwright_test_results.json").read_text(encoding="utf-8"))
        return data.get("iterate_latest")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _test_status_from_iterate(project_root: Path, latest_event: dict) -> list[str]:
    """Build Test Status parts from iterate data.

    Prefers layered data from shipwright_test_results.json (iterate_latest).
    Falls back to flat tests dict from the work_completed event.
    """
    layered = _read_iterate_test_results(project_root)
    if layered:
        parts = [f"Last run: {layered.get('date', latest_event.get('ts', '')[:10])}"]
        unit = layered.get("unit", {})
        integration = layered.get("integration", {})
        pgtap = layered.get("pgtap", {})
        e2e = layered.get("e2e", {})
        smoke = layered.get("smoke", {})
        if unit and unit.get("total", 0) > 0:
            parts.append(f"Unit: {unit.get('passed', 0)}/{unit.get('total', 0)}")
        if integration and integration.get("total", 0) > 0:
            parts.append(f"Integration: {integration.get('passed', 0)}/{integration.get('total', 0)}")
        if pgtap and pgtap.get("total", 0) > 0:
            parts.append(f"pgTAP: {pgtap.get('passed', 0)}/{pgtap.get('total', 0)}")
        if e2e and e2e.get("total", 0) > 0:
            parts.append(f"E2E: {e2e.get('passed', 0)}/{e2e.get('total', 0)}")
        if smoke and smoke.get("status"):
            parts.append(f"Smoke: {smoke['status']}")
        parts.append("(iterate)")
        return parts

    # Flat fallback from event's tests dict
    tests = latest_event.get("tests", {})
    if tests.get("total", 0) > 0:
        parts = [f"Last run: {latest_event.get('ts', '')[:10]}"]
        parts.append(f"Tests: {tests.get('passed', 0)}/{tests.get('total', 0)}")
        if tests.get("e2e_run"):
            parts.append("(incl. E2E)")
        parts.append("(iterate)")
        return parts

    return []


# ---------------------------------------------------------------------------

def _generate_from_events(project_root: Path, session_id: str | None = None,
                          section: str | None = None, step: int | None = None,
                          detail: str | None = None,
                          run_id: str | None = None) -> str | None:
    """Generate dashboard from event log. Returns None if no events exist."""
    events = read_events(project_root)
    if not events:
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sid = session_id or os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")

    work_events = [e for e in events if e.get("type") == "work_completed"]
    build_events = [e for e in work_events if e.get("source") == "build"]
    iterate_events = [e for e in work_events if e.get("source") == "iterate"]
    phase_events = [e for e in events if e.get("type") == "phase_completed"]
    test_runs = [e for e in events if e.get("type") == "test_run"]

    lines = ["# Project Activity Dashboard", _dashboard_header(now, sid, run_id), ""]

    # --- Recent Changes (iterate events, newest first) ---
    if iterate_events:
        lines.extend([
            f"## Recent Changes ({len(iterate_events)} iterations)",
            "",
            "| Type | Description | Tests | Commit | FRs | Date |",
            "|------|-------------|-------|--------|-----|------|",
        ])
        for we in reversed(iterate_events):
            intent = we.get("intent", "change")
            desc = we.get("description", "—")
            tests = we.get("tests", {})
            new_str = f"+{tests.get('new', 0)} new, " if tests.get("new") else ""
            tests_cell = f"{new_str}{tests.get('passed', 0)}/{tests.get('total', 0)}"
            commit = we.get("commit", "—")[:7]
            frs = ", ".join(we.get("affected_frs", [])[:3])
            date = we.get("ts", "")[:10]
            lines.append(f"| {intent} | {desc} | {tests_cell} | {commit} | {frs} | {date} |")
        lines.append("")

    # --- Test Status ---
    # Pick freshest source: test_run event vs iterate work_completed
    latest_test_ts = test_runs[-1].get("ts", "") if test_runs else ""
    latest_iter_ts = iterate_events[-1].get("ts", "") if iterate_events else ""
    use_iterate = bool(iterate_events) and latest_iter_ts > latest_test_ts

    if use_iterate:
        parts = _test_status_from_iterate(project_root, iterate_events[-1])
        if parts:
            lines.extend(["## Test Status", " | ".join(parts), ""])
    elif test_runs:
        latest = test_runs[-1]
        layers = latest.get("layers", {})
        unit = layers.get("unit", {})
        e2e = layers.get("e2e", {})
        smoke = layers.get("smoke", {})
        parts = [f"Last run: {latest.get('ts', '')[:10]}"]
        if unit:
            parts.append(f"Unit: {unit.get('passed', 0)}/{unit.get('total', 0)}")
        if e2e:
            skipped = e2e.get("total", 0) - e2e.get("passed", 0)
            e2e_str = f"E2E: {e2e.get('passed', 0)}/{e2e.get('total', 0)}"
            if skipped:
                e2e_str += f" ({skipped} skipped)"
            parts.append(e2e_str)
        if smoke:
            parts.append(f"Smoke: {smoke.get('status', '—')}")
        lines.extend(["## Test Status", " | ".join(parts), ""])

    # --- Pipeline ---
    if phase_events:
        completed_phases = {e["phase"] for e in phase_events}
        lines.extend(["## Pipeline", "", "| Phase | Status | Completed |", "|-------|--------|-----------|"])
        for phase in PIPELINE_PHASES:
            if phase in completed_phases:
                ts = next((e.get("ts", "")[:10] for e in phase_events if e["phase"] == phase), "—")
                lines.append(f"| {phase} | complete | {ts} |")
            else:
                lines.append(f"| {phase} | — | — |")
        lines.append("")

    # --- Build History ---
    if build_events:
        splits_seen: dict[str, list[dict]] = {}
        for we in build_events:
            splits_seen.setdefault(we.get("split", "default"), []).append(we)

        # Merge in completed sections from build config that may be missing from events
        # (defends against event deduplication bugs or skipped record_event calls)
        build_info = collect_all_build_sections(project_root)
        for sec in build_info["all"]:
            if sec.get("status") == "complete":
                split = sec.get("split", "default")
                if not any(e.get("section") == sec["name"] for e in splits_seen.get(split, [])):
                    splits_seen.setdefault(split, []).append({
                        "section": sec["name"], "commit": sec.get("commit", "?"),
                        "split": split,
                        "tests": {"passed": sec.get("tests_passed", 0), "total": sec.get("tests_total", 0)},
                        "review": {"type": sec.get("review_type", "self")},
                        "affected_frs": [],
                    })

        total_entries = sum(len(secs) for secs in splits_seen.values())
        lines.append(f"## Build History ({total_entries} events)")
        lines.append("")

        for split_name, secs in splits_seen.items():
            first_date = secs[0].get("ts", "")[:10] if secs else ""
            lines.extend([
                f"### {split_name} ({len(secs)} sections, {first_date})",
                "",
                "| Section | Tests | Review | Commit | FRs |",
                "|---------|-------|--------|--------|-----|",
            ])
            for we in secs:
                tests = we.get("tests", {})
                tests_cell = f"{tests.get('passed', 0)}/{tests.get('total', 0)}" if tests.get("total") else "—"
                review = we.get("review", {})
                review_cell = review.get("type", "—").replace("-review", "")
                commit = we.get("commit", "—")[:7]
                frs = ", ".join(we.get("affected_frs", [])[:3])
                lines.append(f"| {we.get('section', '—')} | {tests_cell} | {review_cell} | {commit} | {frs} |")
            lines.append("")

    # --- Current Activity ---
    if section:
        lines.append("## Current Activity")
        activity = f"Section: {section}"
        if step:
            activity += f" — {STEP_LABELS.get(step, f'step {step}')}"
        if detail:
            activity += f" ({detail})"
        lines.append(activity)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Update build dashboard")
    p.add_argument("--project-root", required=True)
    p.add_argument("--phase")
    p.add_argument("--section")
    p.add_argument("--step", type=int, choices=range(1, 13))
    p.add_argument("--detail")
    p.add_argument("--status", choices=["in_progress", "complete", "paused", "failed"])
    p.add_argument("--session-id")
    p.add_argument("--run-id", help="Iterate run id — embedded in the dashboard header (F5b)")
    a = p.parse_args()
    project_root = Path(a.project_root).resolve()
    content = generate_dashboard(project_root, phase=a.phase, section=a.section,
                                 step=a.step, detail=a.detail, status=a.status,
                                 session_id=a.session_id, run_id=a.run_id)
    agent_docs = project_root / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    (agent_docs / "build_dashboard.md").write_text(content, encoding="utf-8")
    print(json.dumps({"success": True, "dashboard": str(agent_docs / "build_dashboard.md")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
