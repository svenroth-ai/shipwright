"""The ONE ready-set computation for ``kind == "sub_iterate"`` campaigns —
shared by ``loop_claim.py``'s ``next-batch`` (which then CLAIMS) and its
read-only ``readiness`` command (which never does).

Readiness is not "every ``depends_on`` unit is merged": ``next-batch`` also
requires each dependency's ``merged_commit`` to be an ancestor of the resolved
batch base and rejects branch strategies that have no single base. A consumer
that re-derived the simple rule (the Command Center WebUI's DAG view) would
show units as ready that ``next-batch`` then refuses — so the rule lives here
once: :func:`unit_blockers` is the single per-unit verdict, ``ready`` is
"no blockers", and ``blocked_by`` IS those blockers. A pending, not-ready row
therefore can never lack a reason.

**Versioned cross-repo output contract:** :func:`build_readiness` is the JSON
the WebUI renders. ``READINESS_SCHEMA_VERSION`` follows the grade/adopt
convention (major = removed/renamed/retyped field or reason, minor =
additive); the frozen wire shape and the closed ``REASONS`` vocabulary are
pinned by ``shared/tests/contracts/loop-readiness-<version>.json``.

**I/O:** ancestry may run ``git fetch origin`` — at most ONCE per call
(:class:`_Ancestry`), refreshing remote-tracking refs only, as ``next-batch``
does. Do not poll this tightly.

Import convention: ``lib.``-qualified for ``loop_state``; ``branch_base`` stays
bare-sibling-imported (one module identity, never two).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # bare-sibling — see module docstring's import-convention note
    from branch_base import fresh_remote_default_ref
except ImportError:  # pragma: no cover
    fresh_remote_default_ref = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.loop_state import is_valid_sha  # noqa: E402

#: Wire-contract version of :func:`build_readiness`'s payload.
READINESS_SCHEMA_VERSION = "1.0"

#: Closed vocabulary of ``blocked_by[].reason`` values (consumers may switch on it).
REASON_DEP_MISSING = "dependency_missing"
REASON_NOT_MERGED = "not_merged"
REASON_COMMIT_MISSING = "commit_missing"
REASON_COMMIT_NOT_ON_BASE = "commit_not_on_base"
REASON_UNSUPPORTED_STRATEGY = "unsupported_strategy"
REASON_FINALIZED = "campaign_finalized"
REASONS = frozenset({REASON_DEP_MISSING, REASON_NOT_MERGED, REASON_COMMIT_MISSING,
                     REASON_COMMIT_NOT_ON_BASE, REASON_UNSUPPORTED_STRATEGY, REASON_FINALIZED})

#: Strategies `next-batch` accepts (each resolves a real batch base).
SUPPORTED_STRATEGIES = ("serial", "independent")


def _is_ancestor(commit: str, base: str, *, cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", commit, base],
                            capture_output=True, text=True, timeout=15, cwd=cwd)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return r.returncode == 0


class _Ancestry:
    """Per-call ancestry oracle: one verdict per commit, and at most ONE
    ``git fetch origin`` per call (try once without fetching; on the first
    miss fetch and retry; still absent -> not on base). ``base=None`` fails
    closed."""

    def __init__(self, base: str | None, cwd: str | None):
        self._base, self._cwd = base, cwd
        self._memo: dict[str, bool] = {}
        self._fetched = False

    def on_base(self, commit: str) -> bool:
        if not self._base:
            return False
        if commit in self._memo:
            return self._memo[commit]
        ok = _is_ancestor(commit, self._base, cwd=self._cwd)
        if not ok and not self._fetched:
            self._fetched = True
            try:
                subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True,
                               timeout=60, cwd=self._cwd)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            ok = _is_ancestor(commit, self._base, cwd=self._cwd)
        elif not ok:
            # Already fetched this call: re-ask, since an earlier fetch may
            # have advanced the ref past this commit.
            ok = _is_ancestor(commit, self._base, cwd=self._cwd)
        self._memo[commit] = ok
        return ok


def _commit_blocker(dep_id: str, dep: dict | None, anc: _Ancestry) -> dict | None:
    """The ancestry half of a dependency's verdict (valid merged commit that
    is on the batch base) — exactly what :func:`_ancestry_ok` answers."""
    commit = dep.get("merged_commit") if dep else None
    if not commit or not is_valid_sha(commit):
        return {"id": dep_id, "reason": REASON_COMMIT_MISSING,
                "detail": f"{dep_id} has no verified merged_commit"}
    if not anc.on_base(commit):
        return {"id": dep_id, "reason": REASON_COMMIT_NOT_ON_BASE,
                "detail": f"{dep_id}'s merged commit is not an ancestor of the batch base"}
    return None


def _ancestry_ok(unit: dict, all_units: list[dict], base_branch: str | None, *, cwd: str | None = None) -> bool:
    """Ancestry-only check (no status rule): every dependency has a valid
    merged commit on `base_branch`. A dependency-free unit is trivially ok."""
    deps = unit.get("depends_on") or []
    if not deps:
        return True
    by_id = {str(u.get("id")).lower(): u for u in all_units}
    anc = _Ancestry(base_branch, cwd)
    return all(_commit_blocker(d, by_id.get(str(d).lower()), anc) is None for d in deps)


def resolve_batch_base(strategy: str, *, cwd: str | None) -> str | None:
    """`serial`/`independent` only — `stacked` has no single base for a
    parallel ready set (out of scope) and resolves to ``None``."""
    if strategy == "serial":
        return fresh_remote_default_ref(cwd=cwd) if fresh_remote_default_ref else None
    if strategy == "independent":
        return "main"
    return None


def unit_blockers(unit: dict, by_id: dict, anc: _Ancestry) -> list[dict]:
    """THE per-unit verdict: every unmet dependency, in `depends_on` order.
    Empty <=> launchable. Case-folded lookup (matches ``campaign_graph``'s
    write-time validation): missing -> not merged -> no/invalid commit ->
    commit not on base."""
    out = []
    for dep_id in unit.get("depends_on") or []:
        dep = by_id.get(str(dep_id).lower())
        if dep is None:
            b = {"id": dep_id, "reason": REASON_DEP_MISSING,
                 "detail": f"{dep_id!r} no longer exists in this campaign"}
        elif dep.get("status") != "merged":
            b = {"id": dep_id, "reason": REASON_NOT_MERGED,
                 "detail": f"{dep_id} has status {dep.get('status')!r}, not yet merged"}
        else:
            b = _commit_blocker(dep_id, dep, anc)
        if b:
            out.append(b)
    return out


def _pending_blockers(units: list[dict], base_branch: str | None, cwd: str | None) -> dict[str, list[dict]]:
    by_id = {str(u.get("id")).lower(): u for u in units}
    anc = _Ancestry(base_branch, cwd)
    return {u["id"]: unit_blockers(u, by_id, anc) for u in units if u["status"] == "pending"}


def ready_unit_ids(units: list[dict], base_branch: str | None, *, cwd: str | None = None) -> set[str]:
    """Ids of `pending` units that are launchable right now (no blockers).
    Used by ``next-batch``; :func:`build_readiness` reports the same verdicts."""
    return {uid for uid, blockers in _pending_blockers(units, base_branch, cwd).items() if not blockers}


def build_readiness(state: dict, *, cwd: str | None = None) -> dict:
    """Read-only readiness report for a ``sub_iterate`` `state` — no lock, no
    claim, no state write. Every pending unit's ``ready`` and ``blocked_by``
    come from ONE verdict."""
    units = state["units"]
    strategy = state.get("branch_strategy", "single-branch")
    finalized = bool(state.get("finalized"))
    supported = strategy in SUPPORTED_STRATEGIES
    # A finalized campaign claims nothing: skip base resolution (serial fetches).
    base_branch = resolve_batch_base(strategy, cwd=cwd) if supported and not finalized else None
    gate: list[dict] | None = None
    if finalized:
        gate = [{"id": None, "reason": REASON_FINALIZED, "detail": "campaign is finalized"}]
    elif base_branch is None:
        supported = False
        gate = [{"id": None, "reason": REASON_UNSUPPORTED_STRATEGY,
                 "detail": f"branch_strategy {strategy!r} has no batch base "
                           "(only 'serial'/'independent' are supported)"}]
    verdicts = {} if gate else _pending_blockers(units, base_branch, cwd)

    rows = []
    for u in units:
        pending = u["status"] == "pending"
        blocked = (list(gate) if gate else verdicts[u["id"]]) if pending else []
        rows.append({"id": u["id"], "state": u["status"],
                     "ready": pending and not blocked, "blocked_by": blocked})
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "loop_id": state.get("loop_id"),
        "branch_strategy": strategy,
        "base_branch": base_branch,
        "supported": supported,
        "finalized": finalized,
        "ready_ids": [r["id"] for r in rows if r["ready"]],
        "units": rows,
    }
