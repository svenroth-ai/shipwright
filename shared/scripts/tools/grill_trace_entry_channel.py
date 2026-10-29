"""Entry-channel guards for the grill-trace gate, split out of
``verify_grill_trace_completeness.py`` (300-LOC bloat guideline).

The gate used to pass a project that never ran an interview at all: with no
transcript and no traces ``grill_trace_coverage`` was SKIPPED, so a brief or seed
that bypassed the interview satisfied the gate by saying nothing. Every entry
channel (interview, Brief package, seed file) must leave the same two artifacts:
``shipwright_project_interview.md`` (a transcript, or the brief-mode pointer to the
signed-off package) and one grill-trace per requirement. Presence checks only,
never a judgment of quality (same honesty guard as the rest of the gate).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.grill_trace_format import GrillTrace, grill_traces_dir
from tools.grill_trace_fr_coverage import extract_fr_names
from tools.verifiers.common import CheckResult, Severity

TRANSCRIPT_NAME = "shipwright_project_interview.md"


def interview_expected(project_root: Path, planning_dir: Path) -> bool:
    """True once the project is past the interview: a spec.md carries FR rows, or the
    project config says ``complete``. Before that, "nothing recorded yet" is the normal state."""
    for spec in planning_dir.glob("*/spec.md"):
        try:
            if extract_fr_names(spec.read_text(encoding="utf-8", errors="ignore")):
                return True
        except OSError:
            continue
    try:
        config = json.loads((project_root / "shipwright_project_config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and config.get("status") == "complete"


def is_extension_scope(project_root: Path) -> bool:
    try:
        config = json.loads((project_root / "shipwright_project_config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and config.get("scope") == "extension"


def check_grill_trace_coverage(
    planning_dir: Path, traces: list[GrillTrace], *, interview_expected: bool = False,
) -> CheckResult:
    """No trace at all is a STOP once an interview is expected (or its transcript exists)."""
    name = "grill_trace_coverage"
    if traces:
        return CheckResult(name, True, f"{len(traces)} grill-trace record(s) found")
    transcript = planning_dir / TRANSCRIPT_NAME
    if transcript.exists():
        return CheckResult(
            name, False,
            f"{transcript} exists (an interview ran) but no grill-trace records "
            f"were written under {grill_traces_dir(planning_dir)}",
        )
    if interview_expected:
        return CheckResult(
            name, False,
            f"no interview transcript and no grill-trace records under {grill_traces_dir(planning_dir)}, "
            "yet the project already has requirements (spec.md FR rows or status complete): the "
            "interview was bypassed. Run the interview, or use a Brief package "
            "(brief_project_mode.py apply) whose approval is recorded",
        )
    return CheckResult(
        name, None, "no interview transcript yet — nothing to check",
        severity=Severity.SKIPPED.value,
    )


def check_transcript_present(planning_dir: Path, traces: list[GrillTrace]) -> CheckResult:
    """Traces without a transcript (or brief-mode pointer) are hand-written, with no recorded
    interview or signed-off package behind them."""
    name = "interview_transcript_present"
    if not traces:
        return CheckResult(name, None, "no traces — nothing to check", severity=Severity.SKIPPED.value)
    transcript = planning_dir / TRANSCRIPT_NAME
    if transcript.is_file() and transcript.read_text(encoding="utf-8", errors="ignore").strip():
        return CheckResult(name, True, "interview transcript (or brief-mode pointer) present")
    return CheckResult(
        name, False,
        f"{len(traces)} grill-trace record(s) exist but {transcript} is missing or empty: a trace "
        "needs the interview transcript, or the brief-mode pointer written by "
        "brief_project_mode.py apply, behind it",
    )


_BRIEF_POINTER_MARKER = "project brief mode: no interview was held"  # the line brief_project_mode.apply writes
# confirmed_by values that name no person: the agent attesting to its own work.
_SELF_ATTESTED = frozenset({"agent", "claude", "assistant", "ai", "model", "auto", "automatic", "seed", "self", "none", "n/a", "assumed"})


def _has_brief_dir(project_root: Path) -> bool:
    try:
        config = json.loads((project_root / "shipwright_run_config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and bool(config.get("brief_dir"))


def check_human_signoff(project_root: Path, planning_dir: Path, traces: list[GrillTrace]) -> CheckResult:
    """The recorded equivalent of an interview must not be the agent signing off on itself.
    A structural screen, NOT proof that a person confirmed anything (a free-text ``confirmed_by``
    cannot be verified; the Brief package route is the one with a verified approval). Structural:
    a brief-mode pointer or ``brief:`` trace needs a recorded ``brief_dir`` (whose hash and
    approval ``brief_mode_checks`` then verify), and ``confirmed_by`` must not be the agent
    attesting to itself. Never reads what the person said."""
    name = "human_signoff"
    if not traces:
        return CheckResult(name, None, "no traces — nothing to check", severity=Severity.SKIPPED.value)
    problems: list[str] = []
    brief_dir = _has_brief_dir(project_root)
    transcript = planning_dir / TRANSCRIPT_NAME
    pointer = transcript.is_file() and any(
        ln.strip().lower().startswith(_BRIEF_POINTER_MARKER)
        for ln in transcript.read_text(encoding="utf-8", errors="ignore").splitlines())
    if pointer and not brief_dir:
        problems.append("the transcript is a brief-mode pointer but run_config records no brief_dir (no approved package behind it)")
    for t in traces:
        who = t.confirmed_by.strip().lower()
        if who.startswith("brief:"):
            if not brief_dir:
                problems.append(f"{t.requirement_key}: confirmed_by {t.confirmed_by!r} but run_config records no brief_dir")
        elif who in _SELF_ATTESTED:
            problems.append(f"{t.requirement_key}: confirmed_by {t.confirmed_by!r} names no person")
    if problems:
        return CheckResult(name, False, "; ".join(problems))
    return CheckResult(name, True, f"{len(traces)} trace(s) carry a human or approved-package sign-off")
