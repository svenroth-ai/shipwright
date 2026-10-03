"""Which evidence entries a RESUMED F0 run REUSED instead of executing.

``stage_f0_evidence`` writes ``resumed_local`` into the staged provenance sidecar when F0
resumed a red run (``units: {unit_id: {mode, base, rerun_tests}}``). A reused-green unit's
testcases, and a failed-only unit's testcases other than the re-run ones, passed on an OLDER
tree - they are green evidence, not an execution at this head. This module turns that marker
into a predicate over evidence ids so ``build_index`` can tag them ``reused`` (the tag is
descriptive: the entry still reads ``executed: pass``, so resume keeps its speed-up).

A unit whose ``base`` is empty (tests at the repo root) cannot be attributed by id prefix and
is treated as executed - the F11 warning still names it. Malformed input (incl. a failed-only
unit with no usable ``rerun_tests``) is "nothing reused": never guessed into a blanket tag.
"""

from __future__ import annotations

from typing import Callable

REUSE_GREEN = "reused-green"
FAILED_ONLY = "failed-only"


def _norm(ident: str) -> str:
    """``<base>/tests/test_x.py::Cls::test_y[p]`` -> ``<base>/tests/test_x.py::test_y``.

    The ONE normalisation both sides of the comparison go through (a re-run node id after
    the unit base is prefixed, and an evidence id as ``read_junit`` built it): class and
    parametrization are dropped, the param from the FIRST ``[`` on (any ``]``/``::`` inside
    it included) - so an id the reader strips differently can only ever read as re-run."""
    path, _, rest = ident.partition("::")
    name = rest.split("[", 1)[0].rsplit("::", 1)[-1]
    return f"{path}::{name}".replace("\\", "/")


def reuse_predicate(resumed_local: object) -> Callable[[str], bool] | None:
    """``test_id -> reused?`` for a ``resumed_local`` marker, or None when nothing is reused."""
    units = resumed_local.get("units") if isinstance(resumed_local, dict) else None
    if not isinstance(units, dict):
        return None
    whole: list[str] = []                       # base prefixes of reused-green units
    partial: dict[str, set[str]] = {}           # base prefix -> ids that WERE re-executed
    for entry in units.values():
        base = str(entry.get("base") or "").strip("/") if isinstance(entry, dict) else ""
        if not base:
            continue
        if entry.get("mode") == REUSE_GREEN:
            whole.append(base + "/")
        elif entry.get("mode") == FAILED_ONLY:
            reran = entry.get("rerun_tests")
            ids = [i for i in reran if isinstance(i, str)] if isinstance(reran, list) else []
            if not ids:  # a failed-only unit always re-ran >= 1 test; none named = cannot attribute
                continue
            partial[base + "/"] = {_norm(f"{base}/{i}") for i in ids}
    if not whole and not partial:
        return None

    def reused(test_id: str) -> bool:
        if any(test_id.startswith(p) for p in whole):
            return True
        norm = _norm(test_id)
        return any(test_id.startswith(p) and norm not in reran for p, reran in partial.items())

    return reused
