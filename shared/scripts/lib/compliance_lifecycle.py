"""Lifecycle authority rules for compliance-audit backlog convergence.

Detection and global-backlog mutation deliberately have separate roots.  A branch
may report what it sees, while only merge/release scopes may converge the backlog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALL_GROUPS = frozenset("ABCDEFGHI")
MERGE_GROUPS = ALL_GROUPS - {"E"}


@dataclass(frozen=True)
class Coverage:
    """Coverage is complete only when every expected group actually ran.

    ``not_applicable`` is an intentional scope exclusion; ``missing`` is a
    failure to obtain evidence. They must never be collapsed.
    """

    scope: str
    expected: frozenset[str]
    not_applicable: frozenset[str]
    ran: frozenset[str]
    missing: frozenset[str]
    import_gate_error: str | None

    @property
    def complete(self) -> bool:
        return not self.import_gate_error and not self.missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "expected": sorted(self.expected),
            "not_applicable": sorted(self.not_applicable),
            "ran": sorted(self.ran),
            "missing": sorted(self.missing),
            "import_gate_error": self.import_gate_error,
            "complete": self.complete,
        }


def coverage_for(report: Any, scope: str) -> Coverage:
    """Classify complete coverage for a named lifecycle authority scope."""
    if scope == "merge":
        expected, not_applicable = MERGE_GROUPS, frozenset({"E"})
    elif scope in {"branch_feedback", "release"}:
        expected, not_applicable = ALL_GROUPS, frozenset()
    else:
        raise ValueError(f"unknown compliance lifecycle scope: {scope!r}")
    ran = frozenset(str(g).upper() for g in getattr(report, "groups_run", ()))
    return Coverage(
        scope=scope,
        expected=expected,
        not_applicable=not_applicable,
        ran=ran,
        missing=expected - ran,
        import_gate_error=getattr(report, "import_gate_error", None),
    )


def may_mirror(coverage: Coverage) -> bool:
    """Only an authoritative, fully-covered merge/release may change triage."""
    return coverage.scope in {"merge", "release"} and coverage.complete
