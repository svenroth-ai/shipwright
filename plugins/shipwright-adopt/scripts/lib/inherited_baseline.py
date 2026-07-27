"""What the codebase arrived broken or untested (FR-01.13, trg-1aa5a8ab).

An onboarded project is not required to arrive perfect, only to arrive honestly
described. Two facts must survive onboarding, and they must not be confused:

``known_failures`` / ``baseline_failure_count``
    tests that were **already failing** before Shipwright touched anything, in
    the shape ``shared/scripts/known_failures.load_accepted_baseline`` parses —
    the ONE reader both the audit and the test phase go through since #453.
    Until now nothing WROTE it: the file was a consumer contract with no
    producer, so every inherited red test read as this project's own failure.
    This module is that producer; the declaration stays hand-editable
    afterwards.

``inherited_coverage_gaps``
    capabilities **no test covers** — requirements with no ``@FR``-tagged test,
    and tests that are switched off. Recorded beside the failures, never inside
    them.

**Why the separation is load-bearing.** ``baseline_failure_count`` is what
``rtm_generator`` uses to turn a ``passed < total`` gap into
``COVERED (baseline)``. It buys forgiveness. Folding untested requirements or
disabled tests into it would spend that forgiveness on absences nobody observed,
and a genuine future failure would read as green. A missing test is not a failing
test, and this module refuses to let one become the other.

**Unobserved is not clean.** Onboarding does not run an arbitrary repository's
test suite, so by default no baseline is observed — and the register says exactly
that (``baseline_observed: false``, ``baseline_source: "not_run"``) rather than
writing a confident zero.

That is a **different fact** from the shared reader's ``present`` / ``malformed``,
and the two must not be conflated: ``present`` answers *"is there a declaration
to read?"*, ``baseline_observed`` answers *"did anyone actually run the suite?"*.
A register can be present, well-formed, and still describe a run that never
happened. Teaching the test phase to honour the flag is ``trg-12b4cf3f``.

Pure except ``write_register``. Imports no ``lib`` package (ADR-045).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Where the register lands — the path the compliance collector looks at.
REGISTER_REL = "shipwright_known_failures.json"

#: The ONLY fields copied out of an observed-baseline payload: exactly what
#: ``collect_known_failures`` reads. A payload assembled from raw test output can
#: carry an environment dump or a traceback with a home path in it, and this file
#: is committed at Step H — so the whitelist is a privacy boundary, not tidiness.
_ALLOWED_FAILURE_FIELDS = ("test", "description", "ticket", "added", "count")

_GAP_CLASSES = ("requirements_without_tests", "disabled_tests")

#: Upper bound on the persisted ``source`` label. It is a short human name for a
#: run ("adopt baseline run", "CI #4821"), and this register is committed — a
#: field with no ceiling is a field someone eventually pastes output into.
_MAX_SOURCE_LABEL = 120

_GAP_TITLES = {
    "requirements_without_tests":
        "Inherited: {n} requirement(s) arrived with no test covering them",
    "disabled_tests":
        "Inherited: {n} test(s) arrived switched off",
}
_GAP_DETAILS = {
    "requirements_without_tests":
        "Recorded at onboarding as inherited, not as this project's own gap: {n} "
        "derived requirement(s) have no `@FR`-tagged test. Onboarding does not "
        "block on them — it records them so they are visible instead of absent. "
        "Full list: `{register}` → `inherited_coverage_gaps`.",
    "disabled_tests":
        "Recorded at onboarding as inherited, not as this project's own gap: {n} "
        "test(s) are skipped, quarantined or focused, so a capability that looks "
        "covered is not. Review and either re-enable, quarantine with an expiry, "
        "or delete. Full list: `{register}` → `inherited_coverage_gaps`.",
}


class BaselineInputError(ValueError):
    """An observed-baseline payload that cannot be trusted.

    Raised rather than degraded, because the degraded reading of a broken
    payload is an empty register — which is indistinguishable from a clean
    inheritance and is the precise lie this module exists to prevent.
    """


@dataclass(frozen=True)
class ObservedBaseline:
    """A test run that actually happened, and what it found."""

    source: str
    failures: tuple[dict[str, Any], ...]

    @property
    def count(self) -> int:
        return sum(int(f["count"]) for f in self.failures)


def _clean_failure(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BaselineInputError(f"each failing test must be an object, got {type(raw).__name__}")
    test = str(raw.get("test") or "").strip()
    if not test:
        raise BaselineInputError("each failing test needs a non-empty `test` identifier")
    count = raw.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise BaselineInputError(f"`count` for {test!r} must be a positive integer, got {count!r}")
    entry = {"test": test, "count": count}
    for field in _ALLOWED_FAILURE_FIELDS:
        if field in ("test", "count"):
            continue
        entry[field] = str(raw.get(field) or "")
    return {k: entry[k] for k in _ALLOWED_FAILURE_FIELDS}


def parse_observed_failures(payload: Any) -> ObservedBaseline:
    """Validate a ``--failures-json`` payload. Fails closed.

    ``source`` and ``command`` are both required and non-empty: "observed" is a
    claim that a run happened, and a bare list of test names is not evidence of
    one. An empty ``failing_tests`` under a real command is legitimate — that is
    an observed GREEN baseline, which is a different fact from no run at all.
    """
    if not isinstance(payload, dict):
        raise BaselineInputError("the payload must be a JSON object")
    # Typed, not coerced. `str({"token": "secret"})` is a non-empty string, so a
    # `str(...)` + truthiness check accepts an object and then persists its repr
    # as `baseline_source` — reopening the very boundary dropping the command
    # closed (external code review).
    source, command = payload.get("source"), payload.get("command")
    for name, value in (("source", source), ("command", command)):
        if not isinstance(value, str) or not value.strip():
            raise BaselineInputError(
                f"`{name}` must be a non-empty string, got {type(value).__name__}"
            )
    source, command = source.strip(), command.strip()
    if len(source) > _MAX_SOURCE_LABEL:
        raise BaselineInputError(
            f"`source` is a short label for the run, max {_MAX_SOURCE_LABEL} "
            f"characters (got {len(source)}) — it is persisted in a committed file"
        )
    raw_failures = payload.get("failing_tests", [])
    if not isinstance(raw_failures, list):
        raise BaselineInputError("`failing_tests` must be a list")
    failures = tuple(_clean_failure(f) for f in raw_failures)

    declared = payload.get("baseline_failure_count")
    total = sum(int(f["count"]) for f in failures)
    if declared is not None:
        # Typed BEFORE comparing: `True == 1` and `1.0 == 1` in Python, so a bare
        # equality check accepts a boolean or a float as a declared count.
        if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
            raise BaselineInputError(
                f"`baseline_failure_count` must be a non-negative integer, got "
                f"{declared!r}"
            )
        if declared != total:
            raise BaselineInputError(
                f"`baseline_failure_count` ({declared}) disagrees with the listed "
                f"failures ({total}) — one of the two is wrong, so neither is trusted"
            )
    return ObservedBaseline(source=source, failures=failures)


def coverage_gaps(
    fr_ids: list[str], backfill_report: dict[str, Any], skip_inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Requirements with no tagged test, and tests that are switched off.

    A tag counts as coverage whether the backfill wrote it (``auto_written``) or
    it was already there (``already_tagged``) — both are real evidence. A tag
    naming an FR that is *not* in this catalogue is ignored: a stale or mistyped
    ``@FR`` must not stand in as evidence for a requirement it does not name.
    """
    covered: set[str] = set()
    for entry in backfill_report.get("auto_written") or []:
        if fr := entry.get("fr"):
            covered.add(str(fr))
    for entry in backfill_report.get("already_tagged") or []:
        covered.update(str(fr) for fr in (entry.get("frs") or []))

    known = list(dict.fromkeys(fr_ids))
    untested = [fr for fr in known if fr not in covered]
    disabled = list(skip_inventory or [])
    return {
        "requirements_without_tests": untested,
        "disabled_tests": disabled,
        "counts": {
            "requirements_without_tests": len(untested),
            "disabled_tests": len(disabled),
        },
    }


def build_register(
    *,
    fr_ids: list[str],
    backfill_report: dict[str, Any],
    skip_inventory: list[dict[str, Any]],
    observed: ObservedBaseline | None,
    adopted_at: str,
) -> dict[str, Any]:
    """The ``shipwright_known_failures.json`` document.

    The first two keys are the established consumer contract, byte-compatible
    with what ``collect_known_failures`` parses. Everything else is additive; the
    collector reads by ``.get`` and no schema constrains this file, so the extra
    keys are inert for it and available to the test phase when it learns to read
    them.
    """
    failures = [dict(f) for f in observed.failures] if observed else []
    return {
        "schema_version": 1,
        "generated_by": "shipwright-adopt",
        "adopted_at": adopted_at,
        "baseline_observed": observed is not None,
        "baseline_source": observed.source if observed else "not_run",
        "known_failures": failures,
        "baseline_failure_count": observed.count if observed else 0,
        "inherited_coverage_gaps": coverage_gaps(fr_ids, backfill_report, skip_inventory),
    }


def write_register(project_root: Path, register: dict[str, Any]) -> Path:
    """Write the register. Idempotent — a re-adopt overwrites in place."""
    out = Path(project_root) / REGISTER_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return out


def gap_triage(register: dict[str, Any]) -> list[dict[str, Any]]:
    """One follow-up per non-empty gap class.

    This is the destination the test phase's journey-coverage routing needs: a
    brownfield gap becomes a tracked follow-up here instead of blocking a run
    there. Dedup keys name the CLASS, never the count, so a re-adopt that finds
    one more gap updates nothing and duplicates nothing — the live numbers are in
    the register, and the card is the pointer to it.
    """
    counts = (register.get("inherited_coverage_gaps") or {}).get("counts") or {}
    cards: list[dict[str, Any]] = []
    for gap_class in _GAP_CLASSES:
        n = int(counts.get(gap_class) or 0)
        if n == 0:
            continue
        cards.append({
            "dedup_key": f"adopt-inherited-gaps::{gap_class}",
            "severity": "medium",
            "kind": "maintenance",
            "title": _GAP_TITLES[gap_class].format(n=n),
            "detail": _GAP_DETAILS[gap_class].format(n=n, register=REGISTER_REL),
            "fr_id": None,
        })
    return cards


__all__ = [
    "REGISTER_REL",
    "BaselineInputError",
    "ObservedBaseline",
    "build_register",
    "coverage_gaps",
    "gap_triage",
    "parse_observed_failures",
    "write_register",
]
