"""FR-01.06 #5 e2e gate the AC-evidence ledger walk found nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
sub-iterate ``e3-checks-test-security``). Split out of ``test_checks.py`` from
the start (mirrors ``_project_gate_extras.py`` / ``_project_gate_manifest.py``
's precedent of keeping the phase-own dispatcher small) rather than waiting
for a bloat-gate crossing. The shared path-safety helpers this module, the
sibling ``_test_gate_specs.py`` (#6), and ``_test_gate_fidelity.py`` (#7) all
import now live in ``_test_gate_paths.py`` — split out a second time when
this file crossed 300 lines again (round 5, Tier-3 CI review on PR #748).

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
from pathlib import Path

from .common import CheckResult, Severity
from ._test_gate_paths import _project_file_or_escape

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


def _skipped_claim_contradicted_by_evidence(pw_path: Path | None) -> tuple[int, str | None]:
    """Whether a readable ``e2e-results.json`` at ``pw_path`` shows any
    non-zero stats field, contradicting a recorded ``e2e.skipped: true``
    claim. Returns ``(contradiction_count, error)``. ``error`` is set when
    the file EXISTS but cannot be validated (malformed JSON, unreadable, or
    a missing/wrong-shaped ``stats`` block, or a malformed individual field)
    — Tier-3 CI review (PR #748): round 4 fixed the file-level cases (that
    "0, no contradiction" result used to also cover a genuinely absent
    file — the only case that still means "no contradiction, no error").
    Round 5 closed the field-level gap round 4 left: a malformed *present*
    field (``expected: true`` or ``expected: "bad"``) was silently excluded
    from the sum instead of erroring, so a garbage stats block with every
    field malformed summed to 0 and read as "no contradiction" — the same
    fail-open ``_stat_field`` already guards against on the non-skipped
    reconciliation path below, now applied here too."""
    if pw_path is None:
        return 0, None
    try:
        pw_data = json.loads(pw_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return 0, f"exists but is malformed/unreadable ({exc})"
    stats = pw_data.get("stats") if isinstance(pw_data, dict) else None
    if not isinstance(stats, dict):
        return 0, "exists but has no stats block to validate the claim against"
    contradiction = 0
    for key in ("expected", "unexpected", "skipped", "flaky"):
        value, error = _stat_field(stats, key)
        if error:
            return 0, f"exists but has an invalid stats field ({error})"
        if value > 0:
            contradiction += 1
    return contradiction, None


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
    results_path, results_escaped = _project_file_or_escape(project_root, "shipwright_test_results.json")
    pw_path, pw_escaped = _project_file_or_escape(project_root, "e2e-results.json")

    # Stage-2 code-reviewer (2026-09-12, PR #748 re-review): the Tier-3 CI
    # fix that made a symlink-escaping design-fidelity-report.json FAIL
    # instead of SKIP was never extended to this sibling check's own two
    # fixed-name reads — an escaping file folded into the same None as a
    # genuinely absent one, which could suppress the reconciliation (SKIP)
    # or defeat the `skipped: true` contradiction check below (a None
    # pw_path always contradicts nothing). Check both before either read
    # falls through to its absence-handling branch.
    if results_escaped:
        return CheckResult(
            name, False,
            "shipwright_test_results.json exists but resolves outside the "
            "project root (symlink escape) — treated as a suppression "
            "attempt, not an absent artifact",
        )
    if pw_escaped:
        return CheckResult(
            name, False,
            "e2e-results.json exists but resolves outside the project root "
            "(symlink escape) — treated as a suppression attempt, not an "
            "absent artifact",
        )

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
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
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
    if e2e.get("skipped") is True:
        # `skipped` is OVERLOADED in this record and only the boolean means
        # "the layer did not run": playwright_runner.parse_playwright_json
        # writes `skipped: <int>` (a count of skipped TESTS in a layer that
        # very much ran), and iterate_tests_block reads it back through
        # `_int_or_none`. A truthy test would therefore treat a normal run
        # with >=1 skipped test as a skipped LAYER -- either hard-failing it
        # as a fabricated claim below, or silently skipping the whole
        # reconciliation. Identity against True, never truthiness.
        #
        # External review round 2 (GLM, medium): a "skipped" claim is the
        # same fabrication/staleness class this check exists to catch if
        # the tool's own output contradicts it — check before trusting it.
        contradiction, evidence_error = _skipped_claim_contradicted_by_evidence(pw_path)
        if evidence_error:
            return CheckResult(
                name, False,
                f"e2e layer recorded as skipped, but e2e-results.json {evidence_error} "
                f"— the 'skipped' claim cannot be validated against it",
            )
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
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
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

    # Tier-3 CI review (PR #748): `bool` is an `int` subclass in Python, so
    # `True == 1` and `False == 0` — a malformed recorded count of `True`
    # would silently "reconcile" against an expected value of 1 with the
    # plain `!=` comparison below. Reject non-bool-non-negative-ints before
    # comparing, the same discipline `_stat_field` already applies to the
    # Playwright side.
    recorded_errors = [
        f"{label}={value!r} is not a non-negative integer"
        for label, value in (
            ("total", recorded_total),
            ("passed", recorded_passed),
            ("flaky", recorded_flaky),
        )
        if isinstance(value, bool) or not isinstance(value, int) or value < 0
    ]
    if recorded_errors:
        return CheckResult(
            name, False,
            "shipwright_test_results.json's e2e layer has unrecognized/malformed "
            "recorded field(s) — " + "; ".join(recorded_errors),
        )

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
