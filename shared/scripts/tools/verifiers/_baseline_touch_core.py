"""Touched set of one diff and the scope rule applied to it (BP brief section 2, library API).

``touched_set`` derives from the merge-base diff, never from a declaration: T-spec (normative
text changed), T-test (a bound test modified or deleted), static test-dir attribution and,
when a base-run context database is supplied, T-code. ``moved`` tests are listed, never
touched. FRs absent at the merge base are new and never existing. ``evaluate_hold`` is the
consequence: ``touched & existing - (scope | moved | broad)``. Scope is an INPUT here; where
it may come from (a brief on main, an operator label) is the caller's rule, not this module's.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ._baseline_touch_binding import test_touched
from ._baseline_touch_coverage import CodeTouch, code_touched
from ._baseline_touch_git import GitRev
from ._baseline_touch_spec import existing_frs, spec_touched
from ._baseline_touch_static import static_touched

__all__ = ["TouchedSet", "touched_set", "evaluate_hold"]


@dataclass
class TouchedSet:
    spec: set[str] = field(default_factory=set)
    test: dict[str, set[str]] = field(default_factory=dict)
    static: dict[str, set[str]] = field(default_factory=dict)
    code: dict[str, set[str]] = field(default_factory=dict)
    fan_out: dict[str, set[str]] = field(default_factory=dict)
    moved: list[tuple[str, str]] = field(default_factory=list)
    new_frs: set[str] = field(default_factory=set)
    existing: set[str] = field(default_factory=set)
    unattributed: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)   # fail-closed reasons
    code_measured: bool = False

    def sources(self) -> dict[str, set[str]]:
        """FR -> the sources ('spec', 'test', 'static', 'code') that touched it."""
        out: dict[str, set[str]] = {}
        for name, frs in (("spec", self.spec), ("test", self.test), ("static", self.static), ("code", self.code)):
            for fr in frs:
                out.setdefault(fr, set()).add(name)
        return {fr: s for fr, s in out.items() if fr in self.existing}

    def digest(self) -> str:
        blob = json.dumps({fr: sorted(s) for fr, s in sorted(self.sources().items())}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()


def touched_set(rev: GitRev, contexts: dict | None = None, require_code: bool = False) -> TouchedSet:
    """``require_code``: T-code is expected (CI); missing contexts then fail closed, never read as "no code touched"."""
    changes = rev.changed()
    changed_paths = {p for _s, o, n in changes for p in (o, n)}
    result = TouchedSet(existing=existing_frs(rev))
    result.spec, result.new_frs = spec_touched(rev, changed_paths)
    result.new_frs |= result.spec - result.existing
    result.spec &= result.existing
    tests = test_touched(rev, changes)
    result.test, result.moved = tests.touched, tests.moved
    result.incomplete += [f"unreadable test file {u}" for u in tests.unreadable]
    result.static, notes = static_touched(rev, changes)
    result.incomplete += notes
    if contexts is not None:
        code: CodeTouch = code_touched(rev, changes, contexts)
        result.code, result.fan_out, result.unattributed = code.touched, code.fan_out, code.unattributed
        result.incomplete += code.incomplete
        result.code_measured = True
    elif require_code:
        result.incomplete.append("baseline evidence incomplete: no coverage contexts supplied")
    return result


def evaluate_hold(touched: TouchedSet, scope: frozenset[str] = frozenset(), n: int | None = None) -> dict:
    """The verdict with no label and no brief (``scope`` empty) is what a single iterate gets."""
    broad = {key for key, frs in touched.fan_out.items() if n is not None and len(frs) > n}
    broad_frs: set[str] = set()
    if broad:  # an FR is broad-only when every function reaching it is broad
        broad_frs = {fr for fr, keys in touched.code.items() if keys <= broad and fr not in touched.spec
                     and fr not in touched.test and fr not in touched.static}
    pending = {fr for fr in touched.sources() if fr not in scope and fr not in broad_frs}
    return {
        "held": bool(pending) or bool(touched.incomplete),
        "frs": sorted(pending),
        "listed_broad": sorted(broad_frs),
        "incomplete": list(touched.incomplete),
    }
