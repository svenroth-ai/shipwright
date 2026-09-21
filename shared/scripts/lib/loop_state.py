"""Loop-state unit loading, terminal-status mapping, and the ``depends_on``
readiness predicate.

Campaign ``campaign-dag-scheduler`` R1
(``.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md``).
``_load_units_from`` moves here from ``autonomous_loop.py`` — R1's share of
this new module; R4 adds more (atomic claim, lease-based reconcile). Only the
``kind == "sub_iterate"`` branch changes behavior; ``kind == "section"`` is
copied verbatim (shipwright-build has no ``depends_on`` concept, and
``autonomous_loop.py::cmd_next``'s existing single-unit contract for it is
preserved at the interface level — see that module's own docstring).

Three fixes over the historical ``sub_iterate`` loader:
``depends_on`` joins the fixed unit-record key set (previously silently
dropped); every unit is retained for the campaign's whole life (never
dropped once loaded — a later :func:`is_unit_ready` check needs to see a
dependency's terminal status, not just the still-pending ones); and a source
``status.json`` terminal status maps explicitly onto the unit-status
vocabulary — ``complete -> merged`` (with a fresh fetch-then-verify ancestry
check of the recorded commit, never trusted blindly) and
``failed``/``escalated -> failed``.

Import convention: always ``lib.loop_state`` (see ``campaign_graph.py``'s
module docstring for the full ADR-045 rationale). This module imports
``branch_base`` the SAME bare-sibling way ``autonomous_loop.py`` does —
never ``lib.branch_base`` — so ``branch_base`` is never loaded under two
different module names; it self-bootstraps its own directory onto
``sys.path`` first (doubt review finding, high) rather than assuming an
importer already put it there — every importer besides
``autonomous_loop.py`` adds only the parent ``shared/scripts``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Self-bootstrap (doubt review, campaign-dag-scheduler R1, high): the bare
# `from branch_base import ...` below needs `shared/scripts/lib` on
# sys.path. `autonomous_loop.py` happens to add it before importing this
# module (its own line 25), but every OTHER `lib.loop_state` importer in
# this diff's neighbourhood (`campaign_init.py`, `campaign_progress.py`,
# `shared/tests/conftest.py`) adds only the PARENT `shared/scripts` — under
# any of those, the bare import raised ImportError, was silently swallowed
# below, and `verify_merged_commit_ancestry` returned `None` before ever
# checking the SHA, permanently and invisibly. This module must not depend
# on its importer having already added its own directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # bare-sibling — see module docstring's import-convention note
    from branch_base import resolve_default_branch
except ImportError:  # pragma: no cover - defensive; the self-bootstrap
    # above makes this unreachable under normal operation.
    resolve_default_branch = None  # type: ignore[assignment]

#: Full-match hex-SHA check, not just length — `commit` is operator-editable
#: (status.json's `commit` field) and flows unquoted into `git merge-base`
#: argv below; a value git would parse as an option (e.g. a leading `-`)
#: must never reach that call. Same pattern
#: `audit_compliance_lifecycle.py::_merge_sha` already applies, reused rather
#: than reinvented (external code review, medium severity).
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def verify_merged_commit_ancestry(commit: str | None) -> str | None:
    """Fresh fetch + ancestry check of `commit` against ``origin/<default>``.

    Returns `commit` back when verified, else ``None`` — a migrated
    ``complete`` row's commit is NEVER trusted blindly (a rewritten/force-
    pushed history must not silently satisfy a dependency edge that no
    longer actually merged). **Doubt review correction (low):** "verified"
    means only "`commit` is reachable from `origin/<default>`'s history" —
    it does NOT prove this unit's own PR merged (any pre-existing ancestor,
    including the unit's own fork-point, verifies) or that the change
    survives (a since-reverted commit still verifies). R4 inherits this
    weaker, accurate contract, not a stronger one. Best-effort: any git
    failure (no repo, no network, unknown commit, no
    ``resolve_default_branch`` available) yields
    ``None`` rather than a crash — the caller then correctly treats that
    dependency as unverified/blocking. This fail-safe direction matters
    because of the KNOWN LIMITATION below: worst case is "stays blocked",
    never "wrongly unblocked".

    **Known limitation (external plan review, R1 — flagged for R4/R5b):**
    `campaign-mode.md` step 3g merges a sub-iterate's PR with `gh pr merge
    --squash`, which mints a BRAND NEW commit on `origin/<default>` — the
    original pre-merge branch-tip commit `campaign_progress.py`'s
    `update-status --commit {commit}` records at step 3h is genuinely NEVER
    an ancestor of `origin/<default>` after a squash merge (unlike a
    fast-forward or a true merge commit, squash discards the original SHA
    from the target's history entirely). Until a later sub-iterate teaches
    step 3h to record the ACTUAL post-merge SHA (e.g. `gh pr view --json
    mergeCommit -q .mergeCommit.oid` after 3g completes, not the runner's own
    pre-merge branch commit), this check will correctly-but-uselessly return
    `None` for every real squash-merged unit — `is_unit_ready` then stays
    permanently blocked rather than falsely unblocking, so the degradation
    is safe (inert) rather than dangerous (silently wrong), but it does mean
    `depends_on` gating is not yet load-bearing against a REAL campaign run
    until that follow-up lands.

    **Second, more severe known limitation (external code review round 3,
    GLM — high severity; flagged for R4):** the ``complete -> merged``
    mapping above only fires inside :func:`_load_units_from`, which only
    runs at a fresh ``cmd_init``. Within ONE CONTINUOUS campaign session
    (no restart between units), `cmd_record` writes a finished unit's
    `loop_state.json` status as `"complete"` verbatim (`autonomous_loop.py`'s
    own contract — accurate, since the real merge, step 3g, hasn't happened
    yet at record time) and nothing promotes it to `"merged"` again until a
    session restart. So `is_unit_ready` sees that dependency as unmerged for
    the REST of that session. **Doubt review correction (high):** a session
    restart does NOT close the gap either — a fresh `cmd_init` DOES run
    `_load_units_from`'s `complete -> merged` mapping, but the squash-merge
    limitation just above still leaves `merged_commit` `None`, since nothing
    anywhere writes a truthy `merged_commit` before R4/R5b's
    `cmd_mark_merged` lands. So `depends_on` currently provides no live
    benefit on ANY path — not "only a safety net across a restart", but no
    working gate at all yet.
    The plan's own text anticipates the actual fix: a new, fencing-validated
    `loop_claim.py::cmd_mark_merged` (R4/R5b) that runs AFTER step 3g's real
    merge and performs this exact promotion with the real post-merge SHA —
    this is why that command's SHA input is explicitly required to be
    strict-hex-validated (the same `_SHA_RE` guard this function now also
    applies to its own read-side `commit` argument, for the same reason:
    both values flow unquoted into `git merge-base` argv).
    """
    if not commit or resolve_default_branch is None:
        return None
    # Doubt review (low): `commit` is operator-editable (status.json), and a
    # truthy non-str (e.g. an int) would reach `_SHA_RE.fullmatch` and raise
    # TypeError, escaping this function's documented "any failure yields
    # None" contract.
    if not isinstance(commit, str) or not _SHA_RE.fullmatch(commit):
        return None
    try:
        fetch = subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, timeout=60)
        if fetch.returncode != 0:
            # A failed fetch means whatever "origin/<default>" already exists
            # locally is STALE — it may still contain `commit` even after a
            # real force-push rewrote history remotely (external code review
            # finding, high severity: never treat a stale local ref as a
            # fresh verification). Fail closed, exactly like any other git
            # failure below.
            return None
        default = resolve_default_branch()
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, f"origin/{default}"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return commit if r.returncode == 0 else None


def _map_unit_status(source_status: str | None) -> str:
    """Map a ``status.json`` terminal status onto the loop unit vocabulary.

    ``complete``/``done -> merged`` (ancestry verified separately by the
    caller — ``done`` is the historical loader's OTHER finished-status token,
    kept for parity: the pre-R1 loader dropped ``complete``/``done`` rows
    identically for both ``section`` and ``sub_iterate`` kinds; a code-review
    finding caught that this rewrite silently stopped recognizing ``done``,
    which would have re-claimed and rebuilt an already-finished unit from
    scratch); ``failed``/``escalated -> failed`` (recoverable only via R4's
    ``cmd_mark``); anything else (pending / in_progress / missing) starts
    fresh as ``pending``.
    """
    if source_status in ("complete", "done"):
        return "merged"
    if source_status in ("failed", "escalated"):
        return "failed"
    return "pending"


def _load_units_from(units_path, kind: str, *, text: str | None = None) -> list[dict]:
    """Load units from a plugin-specific source file, or `text` (stdin)
    directly. See module docstring for the ``sub_iterate`` fixes over the
    historical loader; ``section`` is unchanged."""
    data = json.loads(text) if text is not None else json.loads(units_path.read_text(encoding="utf-8"))

    if kind == "section":
        raw = data.get("sections", [])
        return [
            {
                "id": s.get("name", s.get("id", f"unit-{i}")),
                "spec_path": s.get("spec_path", ""),
                "status": "pending",
                "attempt": 0,
                "started_at": None,
                "finished_at": None,
                "commit": None,
                "head_sha": None,
                "branch": None,
                "result_path": None,
                "handoff_path": None,
                "failure_reason": None,
            }
            for i, s in enumerate(raw)
            if s.get("status") not in ("complete", "done")
        ]
    elif kind == "sub_iterate":
        raw = data.get("sub_iterates", [])
        units = []
        for i, s in enumerate(raw):
            mapped_status = _map_unit_status(s.get("status"))
            # Prefer the durable `merged_commit` (the actual post-merge SHA,
            # once a later sub-iterate's step 3h writes it — see this
            # module's own "Known limitation" note) over the legacy `commit`
            # field; today `merged_commit` is always absent/None on freshly
            # written rows, so this is a no-op until that follow-up lands,
            # but it forward-guards against the exact regression a code
            # review finding named: verifying the pre-merge branch SHA
            # forever once a real post-merge SHA becomes available.
            commit = (s.get("merged_commit") or s.get("commit")) if mapped_status == "merged" else None
            merged_commit = verify_merged_commit_ancestry(commit) if mapped_status == "merged" else None
            units.append({
                "id": s.get("id", s.get("slug", f"unit-{i}")),
                "spec_path": s.get("spec_path", ""),
                "status": mapped_status,
                "attempt": 0,
                "started_at": None,
                "finished_at": None,
                "commit": commit,
                "head_sha": None,
                "branch": s.get("branch"),
                "result_path": None,
                "handoff_path": None,
                "failure_reason": None,
                "depends_on": list(s.get("depends_on") or []),
                "merged_commit": merged_commit,
            })
        return units
    else:
        print(f"ERROR: Unknown kind: {kind}", file=sys.stderr)
        sys.exit(1)
        return []  # unreachable: satisfies py/mixed-returns, sys.exit(1) always raises


def is_unit_ready(unit: dict, all_units: list[dict]) -> bool:
    """``True`` iff every one of `unit`'s ``depends_on`` ids is ``merged``
    with a VERIFIED ``merged_commit`` (never a bare status flag). Empty
    ``depends_on`` is trivially ready. A referenced id absent from
    `all_units` (a stale edge — the target row disappeared) blocks rather
    than being silently ignored.

    **Case-folded lookup** (external code review finding — high severity):
    ``campaign_graph.validate_dependency_graph`` resolves ``depends_on``
    existence case-insensitively at write time, so a case-mismatched edge
    (``depends_on: ["r0"]`` for unit ``R0``) is write-time VALID; an
    exact-case lookup here would then never find it and block the dependent
    forever — a deadlock the write-time validator explicitly promised
    wouldn't happen. Resolve via the same case-fold `campaign_graph.py` uses.
    """
    by_id = {str(u.get("id")).lower(): u for u in all_units}
    for dep_id in unit.get("depends_on") or []:
        dep = by_id.get(str(dep_id).lower())
        if dep is None or dep.get("status") != "merged" or not dep.get("merged_commit"):
            return False
    return True


def describe_blocker(unit: dict, all_units: list[dict]) -> str:
    """Name the specific blocking unit/edge for an unready `unit` — ``""``
    when `unit` is already ready (mirrors :func:`is_unit_ready`, including
    its case-folded lookup)."""
    by_id = {str(u.get("id")).lower(): u for u in all_units}
    for dep_id in unit.get("depends_on") or []:
        dep = by_id.get(str(dep_id).lower())
        if dep is None:
            return f"{unit.get('id')} depends on {dep_id!r}, which no longer exists in this campaign"
        if dep.get("status") != "merged":
            return f"{unit.get('id')} is blocked on {dep_id} (status={dep.get('status')!r}, not yet merged)"
        if not dep.get("merged_commit"):
            return f"{unit.get('id')} is blocked on {dep_id} (merged, but its commit failed ancestry verification)"
    return ""
