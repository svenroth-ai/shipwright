"""FR-01.06 #5 e2e gate the AC-evidence ledger walk found nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
sub-iterate ``e3-checks-test-security``). Split out of ``test_checks.py`` from
the start (mirrors ``_project_gate_extras.py`` / ``_project_gate_manifest.py``
's precedent of keeping the phase-own dispatcher small) rather than waiting
for a bloat-gate crossing. This module also owns the shared path-safety
helpers (:func:`_is_within`, :func:`_safe_project_file`) that the sibling
``_test_gate_specs.py`` (#6) and ``_test_gate_fidelity.py`` (#7) import —
both were split OUT of this file once it crossed 300 lines with all three
gates present.

:func:`check_e2e_counts_reconciled` — "recorded browser-test numbers are the
tool's own." ``step-3.5-e2e-verification.md`` instructs an agent to reconcile
``shipwright_test_results.json``'s ``e2e`` counts against Playwright's own
JSON reporter output (``e2e-results.json``) by hand; no code ever compared
them, so a hand-typed (or copy-pasted-from-a-prior-run) number would sail
through untouched. Reads Playwright's raw ``stats`` block directly — the same
fields step-3.5 names (``expected`` / ``unexpected`` / ``skipped`` /
``flaky``) — rather than importing this repo's own
``playwright_runner.parse_playwright_json``: that function lives under
``plugins/shipwright-test/scripts/lib/`` and a shared verifier never reaches
into a single plugin's own ``scripts/lib`` (ADR-045; every existing
cross-plugin reference in this package is a docstring citation, never an
import — confirmed against ``plan_checks.py``, ``iterate_checks.py`` before
writing this). Deliberately does not apply step-3.5's documented "chromium
project only" filter: ``playwright_runner.py`` itself performs no such
filtering today either (verified by reading its ``walk_suites``), so
filtering here would check the record against a number the pipeline's own
tool never actually produces — a stricter phantom reconciliation, not the
real one. **Fails rather than skips** when a non-skipped ``e2e`` layer is
recorded but ``e2e-results.json`` is absent — external review caught that
SKIP-on-absent-evidence let a fabricated/stale ``e2e`` block sail through
unverified, the exact defect class this check exists to catch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .common import CheckResult, Severity

# ---------------------------------------------------------------------------
# Shared path-safety helpers
# ---------------------------------------------------------------------------


def _is_within(root: Path, candidate: Path) -> bool:
    """Whether ``candidate``'s RESOLVED location stays inside ``root``'s
    RESOLVED location. ``os.path.commonpath`` (not ``str.startswith``,
    not ``Path.is_relative_to`` alone) so drive-letter/case normalization on
    Windows and a POSIX symlink both resolve to the same true answer."""
    try:
        resolved_root = str(root.resolve())
        common = os.path.commonpath([resolved_root, str(candidate.resolve())])
    except (OSError, ValueError):
        return False
    return common == resolved_root


def _safe_project_file(project_root: Path, relative_name: str) -> Path | None:
    """Resolve ``project_root / relative_name``, returning it only when it
    exists, is a regular file, and its RESOLVED location stays inside the
    RESOLVED project root.

    A project-controlled fixed-name artifact (``e2e-results.json``,
    ``shipwright_test_results.json``, ``design-fidelity-report.json``) could
    be committed as a symlink pointing outside the project tree — the same
    escape class PR #729 round 9 fixed for a plugin's own fixed candidate
    paths. Treated identically to "missing" (``None``) rather than raising,
    so a caller's existing SKIP-on-absence branch handles it for free.
    """
    candidate = project_root / relative_name
    try:
        if not candidate.is_file():
            return None
    except OSError:
        return None
    return candidate if _is_within(project_root, candidate) else None


# ---------------------------------------------------------------------------
# #5 — e2e counts reconciled against Playwright's own stats
# ---------------------------------------------------------------------------


def _stat_field(stats: dict, key: str) -> tuple[int, str | None]:
    """Read one Playwright ``stats`` field, returning ``(value, error)``.

    A genuinely ABSENT field defaults to ``0`` with no error — some reporter
    versions omit zero-count fields. A field that IS present but is not a
    non-negative integer (``bool`` is an ``int`` subclass in Python, so a
    stray ``true``/``false`` is rejected too, not silently counted as 1/0)
    is a distinct error rather than a silent ``0`` — external review (both
    reviewers) flagged the previous silent-coercion as hiding exactly the
    Playwright-format-drift this check's own docstring worries about.
    """
    if key not in stats:
        return 0, None
    value = stats[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0, f"{key}={value!r} is not a non-negative integer"
    return value, None


def _skipped_claim_contradicted_by_evidence(pw_path: Path | None) -> int:
    """Whether a readable ``e2e-results.json`` at ``pw_path`` shows any
    non-zero stats field, contradicting a recorded ``e2e.skipped: true``
    claim. Returns the count of non-zero fields found (0 when there is no
    contradiction — no file, unreadable, or a genuinely all-zero stats
    block, which is what an honestly-skipped run's own JSON output would
    also look like)."""
    if pw_path is None:
        return 0
    try:
        pw_data = json.loads(pw_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    stats = pw_data.get("stats") if isinstance(pw_data, dict) else None
    if not isinstance(stats, dict):
        return 0
    return sum(
        1
        for key in ("expected", "unexpected", "skipped", "flaky")
        if isinstance(stats.get(key), int)
        and not isinstance(stats.get(key), bool)
        and stats[key] > 0
    )


def check_e2e_counts_reconciled(project_root: Path) -> CheckResult:
    """FR-01.06 #5: recorded e2e counts in ``shipwright_test_results.json``
    are Playwright's own, not a hand-typed guess.

    SKIPPED only when there is genuinely nothing to reconcile: no
    ``shipwright_test_results.json`` at all, no ``e2e`` layer recorded, or the
    recorded ``e2e`` layer is itself marked ``skipped``. A non-skipped ``e2e``
    layer recorded WITHOUT a readable ``e2e-results.json`` FAILS rather than
    skips — that combination is exactly an unverifiable (or fabricated)
    record, the thing this check exists to catch.

    Keep this formula in sync with ``playwright_runner.parse_playwright_json``
    (``plugins/shipwright-test/scripts/lib/playwright_runner.py``) if that
    module's counting rules ever change — see the note in its own docstring.
    """
    name = "e2e counts reconciled against the playwright tool's own stats"
    results_path = _safe_project_file(project_root, "shipwright_test_results.json")
    pw_path = _safe_project_file(project_root, "e2e-results.json")

    if results_path is None:
        if pw_path is not None:
            return CheckResult(
                name, False,
                "e2e-results.json exists but shipwright_test_results.json is missing",
            )
        return CheckResult(
            name, True, "no shipwright_test_results.json — e2e not run this cycle",
            severity=Severity.SKIPPED.value,
        )

    try:
        recorded = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed shipwright_test_results.json: {exc}")

    e2e = recorded.get("e2e") if isinstance(recorded, dict) else None
    if not isinstance(e2e, dict):
        if pw_path is not None:
            return CheckResult(
                name, False,
                "e2e-results.json exists but shipwright_test_results.json has no "
                "e2e layer recorded",
            )
        return CheckResult(
            name, True, "no e2e layer recorded — e2e not run this cycle",
            severity=Severity.SKIPPED.value,
        )
    if e2e.get("skipped"):
        # External review round 2 (GLM, medium): a "skipped" claim is the
        # same fabrication/staleness class this check exists to catch if
        # the tool's own output contradicts it — check before trusting it.
        contradiction = _skipped_claim_contradicted_by_evidence(pw_path)
        if contradiction:
            return CheckResult(
                name, False,
                "e2e layer recorded as skipped, but e2e-results.json shows "
                f"playwright actually ran ({contradiction} non-zero stats "
                f"field(s)) — a 'skipped' claim the tool's own output "
                f"contradicts",
            )
        return CheckResult(
            name, True, "e2e layer recorded as skipped — nothing to reconcile",
            severity=Severity.SKIPPED.value,
        )

    if pw_path is None:
        return CheckResult(
            name, False,
            "e2e layer recorded (not skipped) but e2e-results.json is missing or "
            "unreadable, so the recorded counts cannot be verified against the "
            "tool's own output — if this project prunes e2e-results.json after "
            "the run, retain it (at least through this gate) or re-run e2e",
        )

    try:
        pw_data = json.loads(pw_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed e2e-results.json: {exc}")

    stats = pw_data.get("stats") if isinstance(pw_data, dict) else None
    if not isinstance(stats, dict):
        return CheckResult(
            name, False, "e2e-results.json has no stats block to reconcile against",
        )

    field_errors = []
    values = {}
    for key in ("expected", "unexpected", "skipped", "flaky"):
        value, error = _stat_field(stats, key)
        values[key] = value
        if error:
            field_errors.append(error)
    if field_errors:
        return CheckResult(
            name, False,
            "e2e-results.json stats block has unrecognized/malformed field(s) — "
            + "; ".join(field_errors),
        )

    expected = values["expected"]
    unexpected = values["unexpected"]
    skipped = values["skipped"]
    flaky = values["flaky"]

    expected_total = expected + unexpected + flaky + skipped
    expected_passed = expected + flaky

    recorded_total = e2e.get("total")
    recorded_passed = e2e.get("passed")
    recorded_flaky = e2e.get("flaky", 0)

    mismatches = []
    if recorded_total != expected_total:
        mismatches.append(f"total: recorded={recorded_total!r} tool={expected_total}")
    if recorded_passed != expected_passed:
        mismatches.append(f"passed: recorded={recorded_passed!r} tool={expected_passed}")
    if recorded_flaky != flaky:
        mismatches.append(f"flaky: recorded={recorded_flaky!r} tool={flaky}")

    if mismatches:
        return CheckResult(
            name, False,
            "e2e counts diverge from playwright's own stats — " + "; ".join(mismatches),
        )
    return CheckResult(
        name, True,
        f"e2e {recorded_passed}/{recorded_total} matches playwright's own stats block",
    )


__all__ = [
    "check_e2e_counts_reconciled",
]
