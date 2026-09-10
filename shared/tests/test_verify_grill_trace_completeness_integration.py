"""End-to-end ``run_all_checks`` coverage for
shared/scripts/tools/verify_grill_trace_completeness.py, plus the required
acceptance criterion — the honesty guard: a well-formed but low-quality
trace passes, because the gate checks completeness, never prose quality.
Split out of test_verify_grill_trace_completeness.py at the 300-LOC
guideline; the per-check unit tests live there.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.grill_trace_format import parse_trace
from tools.verify_grill_trace_completeness import (
    check_greenfield_assumed,
    run_all_checks,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "verify_grill_trace_completeness.py"


def _payload(**overrides) -> dict:
    payload = {
        "requirement_key": "user-login",
        "requirement_text": "The system SHALL authenticate users via email/password.",
        "surface": "project",
        "evidence": ["turn 3: user described login as required"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "n/a:no new term introduced",
            "rationale": "n/a:not hard to reverse",
            "out_of_scope": "answered",
        },
        "fit_criterion": "a valid email/password pair returns a session token",
        "glossary_delta": [],
        "confirmed_by": "user confirmed in turn 5",
        "terms_used": [],
    }
    payload.update(overrides)
    return payload


def _write_trace(planning_dir: Path, payload: dict) -> Path:
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['requirement_key']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# End-to-end: run_all_checks against a real planning tree
# ---------------------------------------------------------------------------

def test_run_all_checks_all_green_for_a_well_formed_trace(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    assert all(r.ok is not False for r in results)


def test_run_all_checks_reports_the_one_failure_when_a_trace_has_a_blank_dimension(tmp_path):
    """A missing dimensions KEY is now rejected earlier, at parse_trace()
    (external code review, P4.2) — read_trace_dir() surfaces that as
    malformed_trace instead. Use a dimension VALUE outside the closed
    vocabulary instead, which still parses fine and is check_blank_dimension's
    own job to catch."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    payload = _payload()
    payload["dimensions"]["glossary"] = "maybe"
    _write_trace(planning_dir, payload)
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    failures = [r for r in results if r.ok is False]
    assert len(failures) == 1
    assert "blank_dimension" in failures[0].name


def test_run_all_checks_flags_coverage_gap_when_transcript_exists_with_no_traces(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    planning_dir.mkdir(parents=True)
    (planning_dir / "shipwright_project_interview.md").write_text("x", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir)

    by_name = {r.name: r for r in results}
    assert by_name["grill_trace_coverage"].ok is False
    # No spec.md anywhere yet — the FR-join check has nothing to check against.
    assert by_name["fr_trace_coverage"].is_skipped


def test_run_all_checks_reports_a_malformed_trace_file_instead_of_crashing(tmp_path):
    """A grill-trace JSON file that fails to parse/validate must surface as
    a red CheckResult, never a raw traceback out of the CLI (external code
    review, P4.2 — GLM finding #1)."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True)
    (directory / "broken.json").write_text("{not valid json", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir)

    assert len(results) == 1
    assert results[0].name == "malformed_trace"
    assert results[0].ok is False


def test_run_all_checks_reports_a_malformed_context_md_instead_of_crashing(tmp_path):
    """A hand-edited CONTEXT.md with a duplicate '## Language' heading makes
    context_md_format.read_terms() raise ValueError (its own documented
    failure contract) — interview-protocol.md sanctions hand-editing
    CONTEXT.md's Relationships/Flagged-ambiguities sections after an
    interview session, so this is a reachable state, not a theoretical one.
    run_all_checks() must surface it as a red CheckResult, never let it
    propagate out of the standalone CLI as a raw traceback (doubt-reviewer,
    P4.2 Stage-3 review)."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text(
        "# CONTEXT.md — demo domain glossary\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n\n"
        "## Language\n\n**Widget** — a duplicate-heading hand-edit mistake.\n",
        encoding="utf-8",
    )

    results = run_all_checks(
        tmp_path, planning_dir=planning_dir, glossary_path=glossary, context_path=context_path,
    )

    by_name = {r.name: r for r in results}
    assert by_name["malformed_context"].ok is False
    assert "malformed_context" in by_name
    # The remaining per-trace checks (blank_dimension, undefined_term, ...)
    # never ran — known_terms couldn't be computed, so run_all_checks()
    # returns early rather than guessing at a partial term set.
    assert not any("undefined_term" in name for name in by_name)


def test_cli_exits_non_zero_cleanly_on_a_malformed_context_md_instead_of_a_traceback(tmp_path):
    """The exact command step-8-completion.md tells the agent to run as a
    first convenience check (`uv run verify_grill_trace_completeness.py`)
    must degrade to a clean non-zero exit, never a raw Python traceback,
    when CONTEXT.md is malformed (doubt-reviewer, P4.2 Stage-3 review)."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    (tmp_path / "CONTEXT.md").write_text(
        "# CONTEXT.md — demo domain glossary\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n\n"
        "## Language\n\n**Widget** — a duplicate-heading hand-edit mistake.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-root", str(tmp_path),
         "--planning-dir", str(planning_dir)],
        capture_output=True, text=True, check=False,
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "malformed_context" in proc.stdout


def test_run_all_checks_flags_fr_without_a_matching_trace_even_when_others_exist(tmp_path):
    """The gap external plan review found: a PARTIALLY recorded interview
    (some requirements traced, one not) passes the plain grill_trace_coverage
    guard but must not pass the FR-join check."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload(requirement_key="user-login"))
    spec = planning_dir / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "## 2. Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | User login | Must | ... | interview | unit |\n"
        "| FR-01.02 | Auth | Password reset | Must | ... | interview | unit |\n",
        encoding="utf-8",
    )
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    by_name = {r.name: r for r in results}
    assert by_name["grill_trace_coverage"].ok is True  # at least one trace exists
    assert by_name["fr_trace_coverage"].ok is False
    assert "FR-01.02" in by_name["fr_trace_coverage"].detail


# ---------------------------------------------------------------------------
# Honesty guard — required acceptance criterion: completeness only, never
# prose quality. Two separate traces (external plan review, P4.2 — the
# combined single-test version conflated "passes despite low quality" with
# "still catches a real gap", which read as internally unclear):
# ---------------------------------------------------------------------------

def test_low_quality_but_structurally_complete_trace_passes_every_check(tmp_path):
    """One-word evidence/confirmation, a terse fit criterion, a curt
    n/a-reason — the gate must not judge any of that, only structural shape
    (shared/grill-trace-format.md §3). Runs the FULL run_all_checks() gate,
    not just three individually-called check functions (external code
    review, P4.2 finding OpenAI-D) — and uses no 'assumed:' value at all,
    since /shipwright-project's surface treats ANY 'assumed' as its own
    separate STOP (greenfield_assumed) regardless of prose quality; mixing
    that STOP into a low-quality-prose test would conflate two different
    things this gate checks."""
    payload = _payload(
        evidence=["x"],
        confirmed_by="ok",
        fit_criterion="y",
        terms_used=[],
    )
    payload["dimensions"]["rationale"] = "n/a:n"
    payload["dimensions"]["out_of_scope"] = "n/a:n"
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, payload)
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    assert all(r.ok is not False for r in results), [r for r in results if r.ok is False]


def test_low_quality_trace_still_catches_a_real_completeness_gap():
    """The mirror of the test above: the SAME low-quality prose style
    (terse, one-word) does not mask a genuine STOP condition. `assumed:idk`
    on the project surface is a real declined-to-ask, not a prose-quality
    defect — proving the gate discriminates on structure, not eloquence."""
    payload = _payload(evidence=["x"], confirmed_by="ok")
    payload["dimensions"]["rationale"] = "assumed:idk"
    trace = parse_trace(payload)

    assert check_greenfield_assumed(trace).ok is False
