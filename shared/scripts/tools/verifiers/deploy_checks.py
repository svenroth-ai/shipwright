"""Deploy-phase verifier checks.

Iterate 12.4 brings the ``shipwright-deploy`` plugin to Minimum Phase
Completion Canon coverage at C1/C2/C3 only:

- **C4 skipped**: deployment is execution — the architectural
  decision was made upstream in plan.
- **C5 skipped**: deployment is operational history
  (``events.jsonl`` + ``phase_history``), not product change. The
  release narrative belongs to the changelog plugin's prepended
  ``## [vX.Y.Z]`` block; adding a deploy bullet to ``[Unreleased]``
  would duplicate and pollute the next version's notes.

Phase-own:

- ``check_test_gate_passed`` — pre-condition: the upstream test phase
  must have produced green results (by the layer's own ``status``
  verdict, or genuine-failure-count when ``status`` is absent — never
  the raw ``passed < total`` gap, which counts skips as failures).
- ``check_failed_liveness_recorded_as_failed`` — a release the smoke
  test found dead must be recorded as ``failed``, never silently as a
  restore.
- ``check_manual_rollback_proves_alive`` — an operator-requested
  rollback that actually mutated the host must be followed by fresh
  liveness evidence.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime as _datetime
from pathlib import Path

# ``known_failures`` lives at ``shared/scripts/`` top level (not under a
# ``lib/`` package) so importing it can never shadow a plugin's own
# ``scripts/lib`` namespace — ADR-045. Same shim as test_checks.py.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from known_failures import genuine_failure_count  # noqa: E402

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_phase_history_has_run,
    read_run_config,
)
from .handoff_phase_canon import check_c3_session_handoff_fresh_after_phase

# Both relative paths are the deploy plugin's own contract
# (``rollback_audit.py`` / ``smoke_test.py --output``), duplicated here as
# literals rather than imported: this module is shared/generic, and the
# rollback/smoke tooling lives under the shipwright-deploy plugin's own
# ``scripts/lib`` — a cross-plugin import of a plugin-local ``lib`` module
# risks exactly the sibling/registration collision ADR-045 exists to avoid.
_SMOKE_RESULT_RELATIVE = Path(".shipwright") / "deploy" / "smoke-test-result.json"
_ROLLBACK_HISTORY_RELATIVE = Path(".shipwright") / "deploy" / "rollback-history.jsonl"
# Written by rollback.py's own except handler ONLY when the primary
# rollback-history.jsonl write itself failed (lock timeout, unwritable
# dir) — the durable degraded marker Tier-3 PR review round 4 asked for as
# the alternative to failing rollback.py's own exit code closed on an
# audit-write failure (which would misreport a real, successful rollback
# as failed). Its presence, not its absence, is the check-manual-rollback
# oracle for "a manual rollback may have happened but left no clean trail".
_ROLLBACK_AUDIT_DEGRADED_RELATIVE = Path(".shipwright") / "deploy" / "rollback-audit-degraded.jsonl"

_FAILED_RELEASE_OUTCOMES = frozenset({"failed", "rolled-back", "rolled_back"})


# ---------------------------------------------------------------------------
# Phase-own
# ---------------------------------------------------------------------------

def _parse_iso_utc(value: object) -> _datetime | None:
    """Parse an ISO-8601 timestamp string into an aware ``datetime``, or
    ``None`` if ``value`` isn't a string or doesn't parse.

    External code review (e4-checks-deploy-changelog): comparing two ISO
    timestamp STRINGS lexicographically (the original version of the two
    staleness checks below) only sorts correctly when both writers use the
    identical format/offset convention — never actually verified across
    ``smoke_test.py`` (``isoformat(timespec="seconds")``) and
    ``append_phase_history.py`` (bare ``isoformat()``). Parsing both into
    real instants before comparing removes that assumption. Normalizes a
    trailing ``Z`` (not accepted by ``datetime.fromisoformat`` before
    Python 3.11) to ``+00:00``.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = _datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive timestamp (no offset — a plausible hand-written or
    # third-party phase_history[deploy].at) is treated as unparseable, not
    # coerced to UTC: an earlier version of this fix assumed local-UTC and
    # normalized it, but for a naive value written in a non-UTC local zone
    # that reads the instant hours away from reality — in exactly the
    # direction that can make a STALE phase_history entry appear to
    # post-date a failure and satisfy the staleness guard below, the one
    # fail-open outcome this reconciliation exists to prevent. Both
    # canonical producers write aware UTC, so this never fires for real
    # evidence; an unknown-zone timestamp is not evidence (doubt review,
    # e4-checks-deploy-changelog — a raise here is already caught and
    # surfaced as a fail-closed ask-level gate error one layer up in
    # validation_record.py, so returning None loses nothing that a crash
    # was protecting and gains a correct comparison direction).
    return None if parsed.tzinfo is None else parsed


def _load_json_object(path: Path) -> tuple[dict | None, str | None]:
    """Read ``path`` as JSON, returning ``(obj, None)`` on a well-formed
    object or ``(None, error)`` otherwise.

    A syntactically valid JSON value that is not an object (``[]``, a bare
    string, a number) is treated the same as malformed JSON — external code
    review (e4-checks-deploy-changelog): every caller in this module used to
    call ``.get()`` straight after ``json.loads``, which crashes with
    ``AttributeError`` on exactly this input rather than returning a
    ``CheckResult``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"root value is {type(data).__name__}, expected an object"
    return data, None


def check_test_gate_passed(project_root: Path) -> CheckResult:
    """The test phase must have produced ``shipwright_test_results.json``
    with a green unit layer before deploy can run. Mirrors
    ``_validate_test``'s unit gate so the deploy verifier can stand
    alone without importing phase_validators.
    """
    name = "test gate: unit tests passed upstream"
    path = project_root / "shipwright_test_results.json"
    if not path.exists():
        return CheckResult(
            name, False,
            "shipwright_test_results.json missing — test phase never completed",
        )
    data, error = _load_json_object(path)
    if error is not None:
        return CheckResult(name, False, f"malformed test results: {error}")
    # Two writers, two shapes: the full-pipeline /shipwright-test phase
    # writes unit/e2e/smoke/... at the TOP level (_validate_test's own
    # convention, which this check was written to mirror); /shipwright-
    # iterate's F5 step nests the identical sub-keys under iterate_latest.
    # Reading only the top level makes this gate a no-op in an iterate-run
    # repo (unit is always None there) — a real integration test against
    # this repo's own file caught it (e4-checks-deploy-changelog).
    view = data
    if not isinstance(data.get("unit"), dict):
        nested = data.get("iterate_latest")
        if isinstance(nested, dict):
            view = nested
    unit_raw = view.get("unit")
    unit = unit_raw if isinstance(unit_raw, dict) else {}
    total = unit.get("total", 0)
    passed = unit.get("passed", 0)
    if not isinstance(total, int) or total <= 0:
        return CheckResult(
            name, False,
            f"unit.total={total}, expected >0 (deploy blocked: no tests ran)",
        )
    if not isinstance(passed, int):
        passed = 0
    # A skipped test is not a failure. The layer's own ``status`` verdict is
    # authoritative when present (both writers set it); otherwise fall back
    # to genuine_failure_count, never the bare ``passed < total`` gap — that
    # arithmetic counts skips as failures and blocks a fully green run whose
    # skips are host-gated (caught against this repo's own real results
    # file, e4-checks-deploy-changelog — see known_failures.genuine_failure_count).
    status = unit.get("status")
    if isinstance(status, str):
        if status != "passed":
            return CheckResult(
                name, False,
                f"unit {passed}/{total}, status={status!r} (deploy blocked: tests failing)",
            )
    else:
        failures = genuine_failure_count(
            passed=passed, total=total,
            failed=unit.get("failed"), skipped=unit.get("skipped"),
        )
        if failures > 0:
            return CheckResult(
                name, False,
                f"unit {passed}/{total} ({failures} genuine failures — deploy blocked)",
            )
    smoke_raw = view.get("smoke")
    smoke = smoke_raw if isinstance(smoke_raw, dict) else {}
    if smoke.get("status") == "fail":
        return CheckResult(
            name, False,
            "smoke test failed upstream — deploy should have been blocked",
        )
    return CheckResult(name, True, f"unit {passed}/{total} passed, smoke OK")


def _last_jsonl_entry(path: Path, *, where: dict | None = None) -> tuple[dict | None, str | None]:
    """Return ``(entry, error)``: the last well-formed JSON object in a
    JSONL file matching every key/value in ``where`` (default: no filter —
    the overall last entry), or ``(None, None)`` when the file is absent or
    genuinely has no matching entry.

    ``error`` is set whenever a line could not be read as a matching
    candidate at all — a malformed line, a non-object line, or the file
    being unreadable — rather than being silently skipped. Tier-3 PR
    review, e4-checks-deploy-changelog round 4: an append-only trail whose
    whole design is "absence means pass" cannot tell "this kind of event
    never happened" apart from "a line recording it exists but could not be
    read", and a caller reconciling liveness evidence must fail closed on
    the latter — a manual rollback silently swallowed by a torn or
    unreadable line must not read the same as one that never occurred.
    ``entry`` still returns the best VALID match found among the readable
    lines, so a caller can act on real evidence even when an unrelated
    line elsewhere in the file is corrupt.

    External code review (e4-checks-deploy-changelog): the original
    unfiltered version was used to find "the last manual rollback", which
    is wrong whenever a LATER entry of a different kind exists — e.g. a
    manual rollback followed by an unrelated automatic one makes the
    overall-last entry ``invocation: auto``, silently excusing the earlier,
    never-verified manual rollback. Filtering by key/value finds the last
    entry of the KIND being asked about, not merely the last entry.
    """
    if not path.exists():
        return None, None
    last: dict | None = None
    error: str | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                error = f"{path.name} contains an unparseable line: {exc}"
                continue
            if not isinstance(parsed, dict):
                error = f"{path.name} contains a non-object line ({type(parsed).__name__})"
                continue
            if where and any(parsed.get(k) != v for k, v in where.items()):
                continue
            last = parsed
    except OSError as exc:
        return None, f"could not read {path.name}: {exc}"
    return last, error


def check_failed_liveness_recorded_as_failed(project_root: Path) -> CheckResult:
    """FR-01.08 criterion 4: a deploy-time liveness check that failed is
    recorded as a failed release — never silently as a completed one.

    Reconciles ``.shipwright/deploy/smoke-test-result.json`` (written by
    ``smoke_test.py --output``, a source the deploy phase does not get to
    rewrite after the fact) against the most recent
    ``phase_history[deploy]`` entry. A green latest smoke result, or no
    smoke result ever persisted, means there is nothing to reconcile.
    """
    name = "a failed liveness check is recorded as a failed deploy"
    path = project_root / _SMOKE_RESULT_RELATIVE
    if not path.exists():
        return CheckResult(name, True, "no smoke-test-result.json recorded yet")
    smoke, error = _load_json_object(path)
    if error is not None:
        return CheckResult(name, False, f"malformed smoke-test-result.json: {error}")
    if smoke.get("success") is not False:
        return CheckResult(name, True, "latest recorded liveness check succeeded")

    # ``read_run_config`` can return a non-dict root ([] / a bare string) on
    # a malformed shipwright_run_config.json — guarded the same way the two
    # ``_load_json_object`` reads above are, so this third read cannot crash
    # the check with AttributeError (external code review, e4-checks-deploy-changelog).
    run_config = read_run_config(project_root)
    history = run_config.get("phase_history") if isinstance(run_config, dict) else None
    entries = history.get("deploy") if isinstance(history, dict) else None
    if not isinstance(entries, list) or not entries:
        return CheckResult(
            name, False,
            "the latest recorded liveness check failed, but phase_history[deploy] "
            "has no entry at all — the failure was never recorded",
        )
    latest = entries[-1]
    # A malformed entry (`[null]`, `["bad"]`) would otherwise crash `.get()`
    # below with AttributeError instead of failing this check closed — Tier-3
    # PR review, e4-checks-deploy-changelog round 3. The outer
    # `validation_record.py` exception containment already turns any raise
    # here into a fail-closed ask-level gate error, but this check has its
    # own well-defined fail-closed `CheckResult` for exactly this situation
    # (an unreconcilable failed liveness check), so it should return that
    # rather than lean on the outer containment for something reachable here.
    if not isinstance(latest, dict):
        return CheckResult(
            name, False,
            f"the latest recorded liveness check failed, but the latest "
            f"phase_history[deploy] entry is malformed ({type(latest).__name__}, "
            "expected an object) — cannot confirm it records the failure",
        )

    # External review (round 1): a stale smoke-test-result.json could
    # otherwise be reconciled against an UNRELATED, older phase_history
    # entry that predates the failure and never had a chance to record it.
    # Requiring the phase_history entry's own completion instant (`at`) to
    # be no earlier than the failed liveness check's `checked_at` ties the
    # two to the same event, without inventing a new release-ID convention
    # this codebase does not otherwise have.
    checked_at = smoke.get("checked_at")
    recorded_at = latest.get("at")
    checked_dt = _parse_iso_utc(checked_at)
    # Fail-closed on BOTH sides of this comparison, not just one — external
    # code review round 2 (e4-checks-deploy-changelog): round 1 fixed the
    # fall-through when phase_history's `at` was missing, but left the
    # mirror-image gap open: a `success: false` smoke result with no
    # parseable `checked_at` used to skip staleness checking entirely too,
    # letting it be satisfied by an arbitrarily old `outcome: "failed"`
    # entry. A failed liveness check that cannot even prove WHEN it failed
    # cannot be reconciled at all.
    if checked_dt is None:
        return CheckResult(
            name, False,
            "the latest recorded liveness check reports success=false but has no "
            "parseable checked_at — cannot confirm which phase_history entry, if "
            "any, records it",
        )
    recorded_dt = _parse_iso_utc(recorded_at)
    # Fail-closed, not fail-open: a phase_history entry with no
    # parseable `at` cannot be CONFIRMED as recording this failure
    # either — external code review (e4-checks-deploy-changelog), the
    # original `isinstance` guard silently skipped this check entirely
    # (and fell through to the outcome check below) whenever `at` was
    # missing, letting an untimestamped `outcome: "failed"` entry
    # satisfy any failure regardless of age.
    if recorded_dt is None or recorded_dt < checked_dt:
        return CheckResult(
            name, False,
            f"the latest recorded liveness check failed at {checked_at}, but the "
            f"latest phase_history[deploy] entry ({recorded_at!r}) has no parseable "
            "timestamp confirming it, or predates the failure",
        )

    outcome = str(latest.get("outcome", "")).strip().lower()
    if outcome in _FAILED_RELEASE_OUTCOMES:
        return CheckResult(name, True, f"recorded as phase_history outcome={outcome!r}")
    return CheckResult(
        name, False,
        f"the latest recorded liveness check failed, but the latest "
        f"phase_history[deploy] outcome={outcome!r} (expected one of "
        f"{sorted(_FAILED_RELEASE_OUTCOMES)})",
    )


def check_manual_rollback_proves_alive(project_root: Path) -> CheckResult:
    """FR-01.08 criterion 8 (proves-alive half): an operator-requested
    rollback (``rollback.py --invocation manual``) is followed by a
    recorded liveness check that actually found the app alive — never
    left unverified, and never satisfied by a check that ran but reported
    the app still down (self-review, e4-checks-deploy-changelog: the
    criterion's own word is "proves", not "attempts").

    Reconciles the last ``invocation: manual`` entry in
    ``.shipwright/deploy/rollback-history.jsonl`` against
    ``.shipwright/deploy/smoke-test-result.json``'s ``success`` +
    ``checked_at``. No manual rollback recorded yet → nothing to reconcile.
    The "confirms first" half of this criterion has no artifact a script
    can verify (an interactive ``AskUserQuestion`` leaves no trace) and
    stays `judgement` — see the AC-evidence ledger.
    """
    name = "an operator-requested rollback is followed by a recorded liveness check that found the app alive"
    # ``mutated: True`` excludes a REFUSED manual rollback (a missing
    # --clone-name, an invalid --target-ref, an unreadable --profile —
    # rollback_report.refused() records these unconditionally with
    # mutated=False) — a rollback that changed nothing has nothing to prove
    # alive, and demanding liveness evidence for it is a false failure
    # (external code review, e4-checks-deploy-changelog).
    latest, history_error = _last_jsonl_entry(
        project_root / _ROLLBACK_HISTORY_RELATIVE,
        where={"invocation": "manual", "mutated": True},
    )
    if history_error is not None:
        # Fail closed, not "no operator-requested rollback recorded yet" —
        # Tier-3 PR review round 4: a corrupt or unreadable line in this
        # append-only trail could be exactly the manual-rollback record
        # being searched for, and this criterion's word is "proves", not
        # "assumes nothing happened".
        return CheckResult(
            name, False,
            f"cannot confirm whether an operator-requested rollback happened: {history_error}",
        )
    degraded, degraded_error = _last_jsonl_entry(
        project_root / _ROLLBACK_AUDIT_DEGRADED_RELATIVE,
        where={"invocation": "manual"},
    )
    if degraded_error is not None:
        return CheckResult(
            name, False,
            f"cannot confirm whether an operator-requested rollback happened: {degraded_error}",
        )
    if degraded is not None:
        degraded_at = _parse_iso_utc(degraded.get("at"))
        latest_at = _parse_iso_utc(latest.get("recorded_at")) if latest is not None else None
        if degraded_at is not None and (latest_at is None or degraded_at > latest_at):
            return CheckResult(
                name, False,
                f"a manual rollback's audit record failed to write at {degraded.get('at')} "
                f"({degraded.get('reason')}) — cannot confirm it was ever followed by a "
                "liveness check",
            )

    if latest is None:
        return CheckResult(name, True, "no operator-requested rollback recorded yet")

    smoke_path = project_root / _SMOKE_RESULT_RELATIVE
    if not smoke_path.exists():
        return CheckResult(
            name, False,
            "a manual rollback was recorded but no liveness check has been "
            "recorded since (no smoke-test-result.json)",
        )
    smoke, error = _load_json_object(smoke_path)
    if error is not None:
        return CheckResult(name, False, f"malformed smoke-test-result.json: {error}")

    checked_at = smoke.get("checked_at")
    recorded_at = latest.get("recorded_at")
    checked_dt = _parse_iso_utc(checked_at)
    recorded_dt = _parse_iso_utc(recorded_at)
    if checked_dt is None or recorded_dt is None:
        return CheckResult(name, False, "smoke-test-result.json or rollback entry missing a parseable timestamp")
    if checked_dt < recorded_dt:
        return CheckResult(
            name, False,
            f"the last recorded liveness check ({checked_at}) predates the last "
            f"manual rollback ({recorded_at}) — it was not re-checked afterward",
        )
    if smoke.get("success") is not True:
        return CheckResult(
            name, False,
            f"a liveness check ran at {checked_at} (after the {recorded_at} rollback), but it "
            f"reported success={smoke.get('success')!r} — the rollback did not prove the app alive",
        )
    return CheckResult(name, True, f"liveness checked at {checked_at}, after rollback at {recorded_at}")


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_deploy_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full deploy-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    results.append(check_test_gate_passed(project_root))
    results.append(check_failed_liveness_recorded_as_failed(project_root))
    results.append(check_manual_rollback_proves_alive(project_root))

    # Canon (C4 + C5 skipped)
    results.append(check_c1_phase_event_recorded(project_root, "deploy"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "deploy"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "deploy"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "deploy", run_id))

    # ADR integrity
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    return run_deploy_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_failed_liveness_recorded_as_failed",
    "check_manual_rollback_proves_alive",
    "check_test_gate_passed",
    "run_all_checks",
    "run_deploy_checks",
]
