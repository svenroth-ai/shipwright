"""Fold this run's recorded test totals into the F5b ``work_completed`` event.

Group D's D1 counts a spec FR as covered only when a ``work_completed`` event
names it AND carries ``tests.total > 0`` (``group_d._check_d1``). Test totals
reached an event only through ``record_event.py``'s ``--tests-*`` flags — the
legacy/out-of-band F7 path that the worktree flow deliberately skips.
``finalize_iterate`` (F5b), the only writer in that flow, built the event with no
``tests`` key at all, so as the worktree flow became the norm the log stopped
carrying test evidence (2026-05: 57 events with totals / 27 without · 2026-07:
66 / 96). D1 and D3 then reported the *recorder's* silence as the *project's*
gap.

This module closes that. It reads the ledger F5 wrote moments earlier rather
than re-running anything: F0 already ran the full suite, and a second run can
disagree with the recorded evidence — which would make the event less
trustworthy, not more.

Mirrors :mod:`lib.iterate_phase_groups` (the ``phase_timings`` fold) in shape
and in posture: additive, best-effort, and never a reason finalize aborts. The
one exception is an explicit caller-supplied block, which is validated at the
write boundary exactly as ``record_event`` validates its own — a corrupt
``tests`` block is refused, never appended to an append-only log.

Source of truth for the shape: ``shared/scripts/tests_block.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ``tests_block`` lives at shared/scripts/ top-level (not under lib/) so the
# compliance plugin can import it without colliding with its own ``lib``
# package — ADR-045. Reach it the same way its other consumers do.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tests_block import validate_tests_block  # noqa: E402

#: Results file written by F5, read here at F5b.
RESULTS_FILENAME = "shipwright_test_results.json"

#: Layers whose counts are summed into the event block. ``e2e`` is summed too
#: (see :func:`derive_tests_block`) but is tracked separately for ``e2e_run``.
_COUNTED_LAYERS = ("unit", "integration", "e2e", "smoke", "pgtap")


def _int_or_none(value: object) -> int | None:
    """``value`` as a non-negative int, else ``None``. ``bool`` is not an int
    here — ``True`` must never be read as a passing test."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _read_latest(project_root: Path | str, run_id: str) -> dict | None:
    """``iterate_latest`` for ``run_id``, or ``None``.

    ``None`` for every degraded state: absent file, unreadable, malformed JSON,
    non-dict shape, and — deliberately — a block belonging to a *different* run.

    The run_id guard is load-bearing. ``shipwright_test_results.json`` is a
    DERIVED SNAPSHOT: the restore the F11 verifier itself prescribes resets it to
    the previous run's content (trg-81fbf8ed observed a ledger check greening on
    the prior run's counts). Reading it unguarded would launder a foreign run's
    totals into this run's event — a fabricated coverage claim, which is worse
    than the missing key this module exists to fix.
    """
    path = Path(project_root) / RESULTS_FILENAME
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[iterate_tests_block] {RESULTS_FILENAME} unreadable ({exc!r}) "
              "— no tests block", file=sys.stderr)
        return None
    if not isinstance(doc, dict):
        return None
    latest = doc.get("iterate_latest")
    if not isinstance(latest, dict):
        return None
    if latest.get("run_id") != run_id:
        print(f"[iterate_tests_block] {RESULTS_FILENAME} holds run_id="
              f"{latest.get('run_id')!r}, finalizing {run_id!r} — no tests block "
              "(stale derived snapshot)", file=sys.stderr)
        return None
    return latest


def derive_tests_block(project_root: Path | str, run_id: str) -> dict | None:
    """Build the event ``tests`` block from this run's recorded ledger.

    Mapping — ``iterate_latest.<layer>`` → block, for every layer in
    :data:`_COUNTED_LAYERS`:

    ==================  =========================================================
    ``passed``          Σ ``layer.passed`` over layers reporting an int
    ``total``           Σ ``layer.total`` over layers reporting an int
    ``skipped``         Σ ``layer.skipped``; **omitted** when no layer reported
                        an int, so the absent/present predicate every reader
                        keys on (``isinstance(skipped, int)``) is preserved
    ``e2e_run``         ``True`` iff the ``e2e`` layer reported ``total > 0``
    ==================  =========================================================

    A layer with ``status: not_run`` carries a ``reason`` and no counts, so it
    contributes nothing. Returns ``None`` when the ledger is absent/stale/
    unusable, when no layer reported a count, when ``total`` is 0 (zero tests is
    not evidence — writing it would look like a claim), or when the assembled
    block fails :func:`validate_tests_block` (a producer bug in F5's file:
    diagnosed and dropped, never raised — finalize must not abort on it).
    """
    latest = _read_latest(project_root, run_id)
    if latest is None:
        return None

    passed = total = 0
    skipped = 0
    saw_count = False
    saw_skipped = False
    e2e_total = 0

    for name in _COUNTED_LAYERS:
        layer = latest.get(name)
        if not isinstance(layer, dict):
            continue
        layer_total = _int_or_none(layer.get("total"))
        if layer_total is None:
            continue
        # A layer reporting a total MUST also report a usable ``passed``.
        # Coercing a malformed/absent one to 0 would turn unreadable source
        # data into a confident "every test in this layer failed" claim — the
        # opposite of best-effort. Skip the layer instead; if that leaves
        # nothing countable the block is dropped entirely.
        layer_passed = _int_or_none(layer.get("passed"))
        if layer_passed is None:
            print(f"[iterate_tests_block] layer {name!r} reports total="
                  f"{layer_total} with no usable 'passed' — layer skipped",
                  file=sys.stderr)
            continue
        saw_count = True
        total += layer_total
        passed += layer_passed
        layer_skipped = _int_or_none(layer.get("skipped"))
        if layer_skipped is not None:
            saw_skipped = True
            skipped += layer_skipped
        if name == "e2e":
            e2e_total = layer_total

    if not saw_count or total <= 0:
        return None

    block: dict = {"passed": passed, "total": total}
    if saw_skipped:
        block["skipped"] = skipped
    block["e2e_run"] = e2e_total > 0

    try:
        validate_tests_block(block)
    except ValueError as exc:
        print(f"[iterate_tests_block] derived block rejected by the shared "
              f"validator ({exc}) — no tests block. Check "
              f"{RESULTS_FILENAME}.iterate_latest", file=sys.stderr)
        return None
    return block


def fold_into_event(event: dict, project_root: Path | str, run_id: str) -> dict:
    """Set ``event['tests']`` from this run's ledger. Returns ``event``.

    Precedence: an explicit block supplied by the caller (F5b's
    ``--event-extras-json``) wins and is left byte-unchanged — but it is
    VALIDATED first, matching ``record_event.py``'s own write-boundary check.
    An explicit block that is not a dict, or that fails the shared validator,
    raises ``ValueError``: silently writing a corrupt block into an append-only
    log, or silently substituting derived numbers for the ones the caller asked
    for, are both worse than halting.

    Derivation itself is best-effort — any problem leaves ``event`` untouched,
    exactly as it was before this module existed.
    """
    if "tests" in event:
        explicit = event["tests"]
        if not isinstance(explicit, dict):
            raise ValueError(
                f"event 'tests' must be an object, got {type(explicit).__name__}")
        validate_tests_block(explicit)
        return event

    try:
        block = derive_tests_block(project_root, run_id)
    except Exception as exc:  # noqa: BLE001 — must never break finalize
        print(f"[iterate_tests_block] tests fold skipped: {exc!r}", file=sys.stderr)
        return event
    if block:
        event["tests"] = block
    return event
