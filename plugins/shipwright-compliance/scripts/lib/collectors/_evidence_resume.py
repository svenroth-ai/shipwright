"""Which evidence entries a RESUMED F0 run REUSED instead of executing.

``stage_f0_evidence`` writes ``resumed_local`` into the staged provenance sidecar when F0
resumed a red run (``units: {unit_id: {mode, base, rerun_tests}}``). A reused-green unit's
testcases, and a failed-only unit's testcases other than the re-run ones, passed on an OLDER
tree - they are green evidence, not an execution at this head. This module turns that marker
into a predicate over evidence ids so ``build_index`` can tag them ``reused`` (the tag is
descriptive: the entry still reads ``executed: pass``, so resume keeps its speed-up).

A unit whose ``base`` is empty (tests at the repo root) cannot be attributed by id prefix and
is treated as executed - the F11 warning still names it. Malformed input is "nothing reused".
"""

from __future__ import annotations

import re
from typing import Callable

REUSE_GREEN = "reused-green"
FAILED_ONLY = "failed-only"
_PARAM_SUFFIX = re.compile(r"\[[^\]]*\]$")


def _norm(ident: str, base: str) -> str:
    """``tests/test_x.py::Cls::test_y[p]`` (unit-relative node id) -> the evidence id
    ``<base>/tests/test_x.py::test_y`` (``read_junit`` drops the class and the param)."""
    path, _, rest = ident.partition("::")
    name = _PARAM_SUFFIX.sub("", rest).rsplit("::", 1)[-1]
    return f"{base}/{path}::{name}".replace("\\", "/")


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
            ids = reran if isinstance(reran, list) else []
            partial[base + "/"] = {_norm(i, base) for i in ids if isinstance(i, str)}
    if not whole and not partial:
        return None

    def reused(test_id: str) -> bool:
        if any(test_id.startswith(p) for p in whole):
            return True
        return any(test_id.startswith(p) and test_id not in reran for p, reran in partial.items())

    return reused
