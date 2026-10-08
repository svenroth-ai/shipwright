"""Test Completeness gate — "testable ⇒ tested" (iterate-2026-05-30-test-completeness-gate).

Extracted from ``iterate_checks.py`` (at its size cap, ADR-125), which re-exports
every public name here so historical imports keep resolving.

**Every complexity answers, trivial included.** The gate used to SKIP a trivial
run, so the F11 report said "skipped" whether or not anybody had looked. A trivial
run now closes the ledger with ONE recorded default row —
``{"status": "n/a", "reason_code": "trivial-auto"}`` in its F5c entry (or F5's
``iterate_latest``) — and a trivial run with no block fails like any other. The
code is the ``review_not_run`` family's ``trivial-auto``: one definition of
"trivial, closed by default", not a second vocabulary. It is refused above
trivial, where ``n/a`` keeps needing a justification.
"""

from __future__ import annotations

from pathlib import Path

from lib.iterate_entry import find_entry_by_run_id
from lib.reason_codes import REASON_CODES, TRIVIAL_AUTO

from ._entry_details import _no_entry_detail, _wrong_shape_detail
from ._iterate_latest import read_iterate_latest, stale_detail
from .common import CheckResult, Severity

__all__ = [
    "TRIVIAL_DEFAULT_CODE",
    "UNTESTABLE_REASON_CODES",
    "check_test_completeness_ledger",
]

#: The closed set of *structural*, falsifiable reasons a behavior may be left
#: UNTESTABLE. "Could-test-but-didn't" is NOT in this set — that escape hatch is
#: the whole point of the gate. Mirrored in ``confidence-anti-patterns.md``
#: (reverse-drift test: ``shared/tests/test_untestable_vocab_doc_sync.py``).
UNTESTABLE_REASON_CODES: frozenset[str] = REASON_CODES["untestable"]

#: The one default row a trivial run closes the ledger with (and every review
#: type it did not run). Taken from the vocabulary, never re-spelled.
TRIVIAL_DEFAULT_CODE = TRIVIAL_AUTO

# Full enumeration is owed at these complexities; trivial owes the recorded row.
_COMPLETENESS_ENFORCED_COMPLEXITIES: frozenset[str] = frozenset({"small", "medium", "large"})
# The only two honest dispositions for a behavior. Any other value (e.g.
# "deferred", "untested", "acceptable") IS the escape hatch and fails.
_COMPLETENESS_VALID_DISPOSITIONS: frozenset[str] = frozenset({"tested", "untestable"})

_NAME = "test completeness ledger"
_TRIVIAL_ROW = '"test_completeness": {"status": "n/a", "reason_code": "trivial-auto"}'


def check_test_completeness_ledger(project_root: Path, run_id: str) -> CheckResult:
    """Every behavior the diff introduces is ``tested`` (with evidence) or
    ``untestable`` (closed-vocabulary structural reason).

    Reads the F5c entry's ``test_completeness`` first, then
    ``shipwright_test_results.json.iterate_latest.test_completeness`` (F5) when
    it names this run. Severity ERROR at every complexity.

    Fail-closed conditions:

    1. no block at all — at trivial too (record the default row);
    2. malformed results JSON / a foreign or unattributed shared block;
    3. ``status`` not in {``complete``, ``n/a``};
    4. ``n/a`` at medium/large; ``n/a`` with ``trivial-auto`` above trivial;
       ``n/a`` with any other ``reason_code``; ``n/a`` with neither a code nor a
       non-empty ``justification``;
    5. ``status == "complete"`` with an empty ``behaviors`` list;
    6. any behavior ``disposition`` outside {``tested``, ``untestable``};
    7. any ``untestable`` behavior whose ``reason_code`` is outside
       ``UNTESTABLE_REASON_CODES``;
    8. any ``tested`` behavior citing no ``evidence``;
    9. ``counts.untested_testable`` missing or > 0;
    10. ``enumeration_basis`` reports more ``acs`` than ``covered_acs``.
    """
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(_NAME, False, _no_entry_detail(run_id))
    complexity = str(entry.get("complexity", "")).lower()
    if complexity != "trivial" and complexity not in _COMPLETENESS_ENFORCED_COMPLEXITIES:
        # Unreachable for a real entry (F5c validates the four values); kept for
        # hand-built legacy fixtures, exactly as before.
        return CheckResult(
            _NAME, True, f"skipped (complexity={complexity or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    # Prefer the PER-RUN entry: an iterate does not commit the shared results file,
    # so on a behind branch it can still hold HEAD's — the PREVIOUS run's — ledger,
    # failing a run that did everything right. Shared file = legacy fallback.
    block = entry.get("test_completeness")
    if block is not None and not isinstance(block, dict):
        return CheckResult(_NAME, False, _wrong_shape_detail("test_completeness", block))
    if not isinstance(block, dict):
        latest = read_iterate_latest(project_root, run_id)
        if not latest.is_current:
            hint = (f" At trivial that block is the one default row `{_TRIVIAL_ROW}`."
                    if complexity == "trivial" else "")
            return CheckResult(_NAME, False, stale_detail(latest, run_id, "test_completeness") + hint)
        block = (latest.block or {}).get("test_completeness")
    if not isinstance(block, dict):
        if complexity == "trivial":
            return CheckResult(
                _NAME, False,
                "no test_completeness block for this trivial iterate — trivial is "
                "no longer skipped: close the ledger with the one default row "
                f"`{_TRIVIAL_ROW}` in the F5c `--entry-json` (references/F5c.md)",
            )
        return CheckResult(
            _NAME, False,
            f"iterate_latest.test_completeness missing for a {complexity} "
            "iterate — populate the ledger at F5",
        )

    status = str(block.get("status", "")).lower()
    if status not in ("complete", "n/a"):
        return CheckResult(
            _NAME, False, f"test_completeness.status={status!r} not one of complete / n/a",
        )
    if status == "n/a":
        return _not_applicable(block, complexity)
    return _complete(block)


def _not_applicable(block: dict, complexity: str) -> CheckResult:
    """``n/a`` is the "no testable behavior" claim — honest only below medium."""
    if complexity in ("medium", "large"):
        # A real feature self-classifying n/a to skip enumeration is the
        # residual escape hatch this closes.
        return CheckResult(
            _NAME, False,
            f"status=n/a is not allowed at {complexity} complexity — a "
            f"{complexity} iterate has testable behavior by definition. "
            "Enumerate it (status=complete), or re-classify the iterate as "
            "small if the change is genuinely behaviorless",
        )
    code = block.get("reason_code")
    if code is not None:
        if code != TRIVIAL_DEFAULT_CODE:
            return CheckResult(
                _NAME, False,
                f"test_completeness.reason_code={code!r} — the only code an n/a "
                f"ledger takes is {TRIVIAL_DEFAULT_CODE!r} (trivial's default row)",
            )
        if complexity != "trivial":
            return CheckResult(
                _NAME, False,
                f"reason_code {TRIVIAL_DEFAULT_CODE!r} closes the ledger of a TRIVIAL "
                f"iterate only — a {complexity} run's n/a names why in a "
                "`justification` (e.g. 'markdown-only edit; no executable behavior "
                "changed'), or enumerates its behaviors",
            )
        return CheckResult(_NAME, True, f"n/a, trivial default row recorded ({TRIVIAL_DEFAULT_CODE})")
    justification = str(block.get("justification", "")).strip()
    if not justification:
        return CheckResult(
            _NAME, False,
            "status=n/a requires a justification (e.g. 'markdown-only "
            "edit; no executable behavior changed')"
            + (f", or at trivial the default row `{_TRIVIAL_ROW}`" if complexity == "trivial" else ""),
        )
    return CheckResult(_NAME, True, f"n/a, justified ({len(justification)} chars)")


def _complete(block: dict) -> CheckResult:
    """``status == "complete"`` — every enumerated behavior holds its contract."""
    behaviors = block.get("behaviors")
    if not isinstance(behaviors, list) or not behaviors:
        return CheckResult(
            _NAME, False,
            "status=complete but no behaviors enumerated — a small+ iterate "
            "that changed behavior must list at least one testable behavior",
        )

    for i, beh in enumerate(behaviors):
        if not isinstance(beh, dict):
            return CheckResult(_NAME, False, f"behavior[{i}] is not an object")
        label = str(beh.get("behavior", f"#{i}"))
        disposition = str(beh.get("disposition", "")).lower()
        if disposition not in _COMPLETENESS_VALID_DISPOSITIONS:
            return CheckResult(
                _NAME, False,
                f"behavior {label!r} has disposition={disposition!r} — only "
                "'tested' or 'untestable' are allowed. The "
                "'could-test-but-didn't' escape hatch is not permitted: test "
                "it, or classify it untestable with a structural reason_code",
            )
        if disposition == "untestable":
            reason_code = str(beh.get("reason_code", "")).strip()
            if reason_code not in UNTESTABLE_REASON_CODES:
                return CheckResult(
                    _NAME, False,
                    f"behavior {label!r} untestable with reason_code="
                    f"{reason_code!r}, not in the closed vocabulary "
                    f"{sorted(UNTESTABLE_REASON_CODES)}",
                )
        elif not str(beh.get("evidence", "")).strip():
            return CheckResult(
                _NAME, False,
                f"behavior {label!r} is 'tested' but cites no evidence — name "
                "the test + result",
            )

    counts = block.get("counts") if isinstance(block.get("counts"), dict) else {}
    untested_testable = counts.get("untested_testable", None)
    # NB: bool is a subclass of int — `untested_testable: false` must NOT
    # satisfy the "must be int == 0" contract.
    if (isinstance(untested_testable, bool)
            or not isinstance(untested_testable, int)
            or untested_testable > 0):
        return CheckResult(
            _NAME, False,
            f"counts.untested_testable={untested_testable!r} — every testable "
            "behavior must be tested (target 0)",
        )

    basis = block.get("enumeration_basis")
    if isinstance(basis, dict):
        acs, covered = basis.get("acs"), basis.get("covered_acs")
        if isinstance(acs, int) and isinstance(covered, int) and acs > covered:
            return CheckResult(
                _NAME, False,
                f"enumeration gap: {acs} acceptance criteria, only {covered} "
                "covered by ledger rows — enumerate the remainder",
            )

    tested = sum(
        1 for beh in behaviors if str(beh.get("disposition", "")).lower() == "tested"
    )
    untestable = len(behaviors) - tested
    return CheckResult(
        _NAME, True,
        f"complete: {tested} tested, {untestable} untestable (valid reason), "
        "0 untested-testable",
    )
