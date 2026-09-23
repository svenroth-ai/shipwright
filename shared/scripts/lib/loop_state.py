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

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
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

# `lib.`-qualified (campaign-dag-scheduler R4) — this module is ALWAYS
# imported as `lib.loop_state` (see module docstring), so `shared/scripts`
# (unit_lease's own package root) is already on sys.path by the time this
# line runs; never a bare `import unit_lease`, which would give `unit_lease`
# two distinct module identities (ADR-045).
from lib.campaign_graph import id_charset_ok  # noqa: E402
from lib.unit_lease import is_unit_lease_stale  # noqa: E402

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

    **No subprocess/git calls happen here** (external Tier-3 review, PR
    #790 round 15 — raised as a BLOCK, verified incorrect against this
    exact function body and closed without a behavior change): this is a
    pure dict lookup against each `dep`'s already-populated
    `merged_commit` field. The git-based ancestry check that actually
    populates `merged_commit` runs elsewhere, cwd-aware in both places it
    matters — `loop_claim.py::_ancestry_ok` (called from `cmd_next_batch`
    right alongside this function, with `cwd=args.campaign_worktree`) and
    `loop_mark.py::cmd_mark_merged` (its own local `_is_ancestor`, same
    `cwd=args.campaign_worktree` threading, explicitly NOT delegating to
    this module's cwd-less `verify_merged_commit_ancestry` for that
    reason — see that function's own call site comment). This module's
    `verify_merged_commit_ancestry` only ever runs from `_load_units_from`
    at `autonomous_loop.py::cmd_init` time, a different command entirely.
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


# ---------------------------------------------------------------------------
# Campaign-dag-scheduler R4 — the 9-state unit state machine, fencing
# primitives, canonical state-root paths, and lease-based reconciliation.
#
# Everything below is ``kind == "sub_iterate"``-shaped data/logic EXCEPT
# :func:`reconcile_in_progress`, which also carries `kind == "section"`'s
# unchanged legacy path (see that function's own docstring) so
# ``autonomous_loop.py`` has exactly one call site instead of two.
# ---------------------------------------------------------------------------

#: Every legal unit status. ``blocked`` is derived (:func:`is_unit_ready`),
#: never stored on a row.
STATES = frozenset({
    "pending", "claimed", "running", "built", "reviewed",
    "merging", "merged", "failed", "held",
})

#: `cmd_finalize` (``kind == "sub_iterate"`` branch) refuses while any unit
#: sits outside this set.
TERMINAL = frozenset({"merged", "failed", "held"})

#: `cmd_init` resumes in place (never reinitializes) while any unit is here —
#: a runner or the merge lane currently owns it.
ACTIVE = frozenset({"claimed", "running", "merging"})

#: `cmd_init` also resumes in place for these — nothing currently owns them,
#: but each still carries real progress a reinit would silently discard.
RESUMABLE = frozenset({"pending", "built", "reviewed", "held"})

#: The state machine's edge table (plan v6, "R4 — concurrent state
#: mechanics"). Keyed by FROM state; each value is the set of legal TO
#: states. `cmd_mark` is exempt (`forced=True` below — "may cross any edge,
#: always audited"), since it is the one documented operator escape hatch;
#: every OTHER mutator (`loop_claim.py`'s atomic claim, `cmd_mark_running`,
#: `cmd_mark_merged`, `cmd_release`) stays inside this table. Each edge whose
#: target is `held` — and the `running -> failed` `drain_timeout` special
#: case — carries a caller-supplied `reason_code` (not structurally enforced
#: here, since a full drain sweep is a later sub-iterate's own delivery; this
#: table only fixes which edges EXIST).
TRANSITIONS: dict[str, frozenset[str]] = {
    "pending":  frozenset({"claimed", "held"}),
    "claimed":  frozenset({"running", "pending", "failed", "held"}),
    "running":  frozenset({"built", "failed", "pending", "held"}),
    "built":    frozenset({"reviewed", "merging", "failed", "held"}),
    "reviewed": frozenset({"merging", "built", "held"}),
    "merging":  frozenset({"merged", "held", "failed"}),
    "held":     frozenset({"pending"}),
    "merged":   frozenset(),
    "failed":   frozenset(),
}


def is_legal_transition(from_state: str, to_state: str, *, forced: bool = False) -> bool:
    """``True`` iff ``from_state -> to_state`` is a legal edge in the 9-state
    machine above. ``to_state`` must always be a real :data:`STATES` member —
    an unknown TARGET is never legal to land on, forced or not.

    ``from_state`` is checked against :data:`STATES` only when ``forced`` is
    ``False``. ``forced=True`` is ``cmd_mark``'s documented "may cross any
    edge" exemption (Stage-3 doubt review, HIGH #2): a row can carry a
    pre-R4 legacy status (``"complete"``, ``"escalated"``, ``"in_progress"``
    — a never-claimed row's `resolve_record_status`/`enforce_record_fencing`
    pass-through, or `_reconcile_legacy`'s own legacy write) that is not a
    member of :data:`STATES` at all; gating the exemption on `from_state`
    too made the one documented operator escape hatch unable to reach the
    exact rows that most need it. The audit trail still records the real
    (possibly-legacy) `from` value elsewhere; this function only judges
    whether the transition may proceed.
    """
    if to_state not in STATES:
        return False
    if forced:
        return True
    if from_state not in STATES:
        return False
    return to_state in TRANSITIONS.get(from_state, frozenset())


def now_iso() -> str:
    """UTC ISO-8601 timestamp — the one clock every ``loop_state.json``
    writer (``autonomous_loop.py``, ``loop_claim.py``) uses, so a row's
    ``claimed_at``/``finished_at``/... timestamps are always comparable."""
    return datetime.now(timezone.utc).isoformat()


def find_unit_row(state: dict, unit_id: str) -> dict | None:
    """Exact match first, case-folded fallback — mirrors ``lib.unit_lease``'s
    own ``_find_unit`` convention, so every ``loop_state.json`` consumer
    finds the same row either lookup style would."""
    units = state.get("units") or []
    for unit in units:
        if unit.get("id") == unit_id:
            return unit
    folded = str(unit_id).lower()
    for unit in units:
        if str(unit.get("id")).lower() == folded:
            return unit
    return None


def is_valid_sha(value) -> bool:
    """Full-match 40-char-hex check — the SAME pattern
    :func:`verify_merged_commit_ancestry` already enforces on its own
    ``commit`` input, exported here so ``loop_claim.py``'s ``cmd_mark``/
    ``cmd_mark_merged`` (a strict-format check, not a "verify against a
    resolved base" ancestry call) reuse one regex rather than a second copy.
    """
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def validate_attempt_token(unit: dict | None, attempt_id: str | None) -> bool:
    """``True`` iff `unit` exists and its own ``attempt_id`` matches
    `attempt_id` exactly — the one fencing check every claimed-or-later
    mutation performs before writing (`cmd_record`, `check_unit_attempt.py`,
    `loop_claim.py`'s `cmd_mark_running`/`cmd_mark_merged`). A missing unit
    or a falsy/mismatched token is always a rejection, never an ambiguous
    pass.
    """
    if unit is None or not attempt_id:
        return False
    return unit.get("attempt_id") == attempt_id


def runs_dir_for(state_path, loop_id: str, unit_id: str | None = None) -> Path:
    """Canonical, state-root-relative ``runs/`` directory (R4 work item 11):
    ``{state_path.parent}/runs/{loop_id}[/{unit_id}]`` — NEVER cwd-relative.
    `state_path` is always ``<root>/.shipwright/loop_state.json``, so its
    parent directory IS the ``.shipwright`` tree everything here is rooted
    under, regardless of the calling process's own working directory.

    `loop_id` is a `loop_state.json` value — a real one is always internally
    minted (`f"{{kind}}-{{timestamp}}"`, always inside the safe charset), but
    a hand-edited or corrupted state file could carry anything (external
    Tier-3 PR review, round 9). Rejected against the same
    `campaign_graph.id_charset_ok` charset :func:`rejected_payload_path`
    already enforces for `unit_id`, with the same resolved-path containment
    check kept as defense-in-depth.

    `unit_id`, when given, is a persisted unit row's ``id`` — the same
    untrusted-row threat model, and `rejected_payload_path` already
    charset-checks it before ever reaching this function. External Tier-3 PR
    review (GPT, round 11): this function itself did not, and two OTHER
    callers (`autonomous_loop.cmd_record`'s fallback-path and result-path
    writes) pass a raw `args.unit`/`unit["id"]` straight through without
    their own check — so the guarantee has to live here, not be re-derived
    by every caller. Checked the same way `loop_id` is, with the same
    containment check re-run AFTER `unit_id` is appended (the `loop_id`-only
    containment check above runs before that append and would not catch a
    traversing `unit_id` on its own).
    """
    if not id_charset_ok(loop_id):
        raise ValueError(f"runs-dir path refused: loop_id {loop_id!r} is not a safe identifier")
    if unit_id is not None and not id_charset_ok(unit_id):
        raise ValueError(f"runs-dir path refused: unit_id {unit_id!r} is not a safe identifier")
    state_root = Path(state_path).resolve().parent
    base = state_root / "runs" / loop_id
    resolved_base = base.resolve()
    if not resolved_base.is_relative_to(state_root):
        raise ValueError(
            f"runs-dir path {resolved_base} escaped the state root {state_root} — refusing")
    result = (base / unit_id) if unit_id else base
    if unit_id:
        resolved_result = result.resolve()
        if not resolved_result.is_relative_to(resolved_base):
            raise ValueError(
                f"runs-dir path {resolved_result} escaped {resolved_base} — refusing")
    return result


#: Safe filename-segment charset for an UNTRUSTED `attempt_id` (external code
#: review, OpenAI, high). A real, minted `attempt_id` is always
#: `f"{loop_id}-{unit_id}-a{attempt}"` (hyphens, alnum) — but the value
#: reaching :func:`rejected_payload_path` is the CALLER's `--attempt-id`, the
#: one this whole function exists to say is untrustworthy (a stale or
#: outright wrong token). A value containing path separators, `..`, or an
#: absolute-path prefix must never reach an f-string Path segment.
_SAFE_ATTEMPT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")


def _safe_rejected_filename(attempt_id: str) -> str:
    """`{attempt_id}.json` when `attempt_id` is a safe filename segment;
    otherwise a short digest of it — never the raw value, and never able to
    change the target directory (no ``/``, ``\\\\``, or ``..`` reaches the
    filesystem call either way)."""
    if _SAFE_ATTEMPT_ID_RE.fullmatch(attempt_id) and ".." not in attempt_id:
        return f"{attempt_id}.json"
    digest = hashlib.sha256(attempt_id.encode("utf-8", errors="surrogateescape")).hexdigest()[:32]
    return f"unsafe-token-{digest}.json"


def rejected_payload_path(state_path, loop_id: str, unit_id: str, attempt_id: str) -> Path:
    """``runs/{loop_id}/{unit_id}/rejected/{attempt_id}.json`` — where
    `cmd_record` parks a stale-attempt payload instead of writing it over the
    (unrelated, current-attempt-owned) state row.

    `attempt_id` is the CALLER's supplied token — by construction, arriving
    here at all means it did NOT match the row's real one, so it is
    untrusted input, not a value this function may assume is well-formed.
    :func:`_safe_rejected_filename` neutralizes anything that isn't a plain
    filename segment; the resolved-path containment assert below is
    defense-in-depth against a filesystem-specific traversal shape neither
    the regex nor the digest fallback anticipated.

    `unit_id` is ALSO untrusted here (code-review re-check, medium; hardened
    further by external review, high): it is a `loop_state.json` row value,
    not previously re-validated by this function against `campaign_graph.
    id_charset_ok` — a malformed row whose id bypassed that check could
    otherwise traverse. The loop-root containment check alone is
    insufficient: a `unit_id` such as `"A/../B"` never escapes `runs/
    {loop_id}/` at all (it resolves to the sibling `runs/{loop_id}/B/`,
    which IS relative to the loop root), yet still redirects a rejected
    payload meant for unit A into unit B's own real `rejected/` directory,
    overwriting its file. Rejecting any `unit_id` outside the canonical
    charset up front (no `/`, no `..`) closes that gap — the same charset
    `campaign_init.py` already enforces at write time, so a row that never
    passed it should never be trusted to build a path either. The loop-root
    containment check below is kept as defense-in-depth against a
    filesystem-specific shape this charset check does not anticipate.
    """
    if not id_charset_ok(unit_id):
        raise ValueError(f"rejected-payload path refused: unit_id {unit_id!r} is not a safe identifier")
    rejected_dir = runs_dir_for(state_path, loop_id, unit_id) / "rejected"
    candidate = rejected_dir / _safe_rejected_filename(attempt_id)
    resolved_candidate = candidate.resolve()
    loop_root = runs_dir_for(state_path, loop_id).resolve()
    if not resolved_candidate.is_relative_to(loop_root):
        raise ValueError(
            f"rejected-payload path {resolved_candidate} escaped the loop's "
            f"runs root {loop_root} — refusing to write"
        )
    return candidate


def handoff_dir_for(state_path, loop_id: str) -> Path:
    """Canonical, state-root-relative handoff directory — same rationale as
    :func:`runs_dir_for`.

    Written as ``project_root / ".shipwright" / "planning" / ...`` (an
    explicit ``.shipwright`` literal in the same expression), matching every
    other caller of the ``.shipwright/planning`` path in this codebase
    (``handoff_iterate.py``, ``journey_plan.py``, ``review_record_core.py``)
    — not stylistic: the repo's artifact-path-canon lint's AST-mode check
    only recognizes the legacy migration's directory NAME as an
    already-rooted, canonical Path-division segment when it can see the
    preceding ``.shipwright`` constant in the very same chain. This
    function's first draft chained that segment directly off
    ``.resolve().parent`` instead — no such sibling literal for the checker
    to see, even though `state_path`'s parent always IS that directory —
    and was flagged as an unlisted legacy-path reference.

    `loop_id` charset/containment-checked the same way :func:`runs_dir_for`
    is (external Tier-3 PR review, round 9) — see that function's docstring.
    """
    if not id_charset_ok(loop_id):
        raise ValueError(f"handoff-dir path refused: loop_id {loop_id!r} is not a safe identifier")
    project_root = Path(state_path).resolve().parents[1]
    # The `.shipwright` literal must stay directly chained onto the next
    # path segment below (see docstring above) — the artifact-path-canon
    # lint only recognizes this as an already-rooted canonical path when it
    # sees them together; the separate `shipwright_root` variable further
    # down is only for the containment check, never part of the returned
    # path's own construction.
    handoff_dir = project_root / ".shipwright" / "planning" / "handoffs" / loop_id
    resolved_handoff_dir = handoff_dir.resolve()
    shipwright_root = (project_root / ".shipwright").resolve()
    if not resolved_handoff_dir.is_relative_to(shipwright_root):
        raise ValueError(
            f"handoff-dir path {resolved_handoff_dir} escaped "
            f"{shipwright_root} — refusing")
    return handoff_dir


def _reconcile_legacy(state: dict, state_path) -> list[str]:
    """``kind == "section"`` reconciliation. Copied from the pre-R4
    ``autonomous_loop._reconcile_in_progress`` with exactly one change: the
    ``runs/`` lookup is now state-root-relative (:func:`runs_dir_for`)
    instead of cwd-relative (R4 work item 11) — every real caller already
    always ran with cwd == the state root's project directory (shipwright-
    build's SKILL.md always operates from the project root), so this cannot
    change observed behavior; it only removes the cwd assumption itself.
    Every other line is behaviorally identical to before this move.

    **Also reused for ``kind == "sub_iterate"``** rows stuck at legacy
    ``"in_progress"`` (`cmd_init_sub_iterate_payload`'s `legacy_active`
    branch — a row never touched by the new atomic-claim flow, so it still
    carries the pre-R4 vocabulary). Stage-3 doubt review (HIGH #2 second
    half): a `kind == "sub_iterate"` row must land on the 9-state vocabulary
    (:data:`STATES`), not a legacy string the new claim/mark/finalize
    machinery does not understand — ``"merged"`` is the closest TERMINAL
    equivalent to legacy ``"complete"`` for a row whose work is done, so
    that finalize's own compatibility boundary
    (`sub_iterate_finalize_summary`) and `cmd_mark --force`'s exemption
    (`is_legal_transition`) both see a real state on this row from here on.
    """
    warnings: list[str] = []
    runs_dir = runs_dir_for(state_path, state["loop_id"])
    is_sub_iterate = state.get("kind") == "sub_iterate"
    done_status = "merged" if is_sub_iterate else "complete"

    for unit in state["units"]:
        if unit["status"] != "in_progress":
            continue

        result_path = runs_dir / unit["id"] / "result.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("status") == "complete":
                    # External review (GPT, high): this row was only ever
                    # reached via a dead session's result.json, not a
                    # completed `campaign-mode.md` step 3g merge — the
                    # commit here is a pre-merge branch tip, not a verified
                    # merge. The earlier fix here routed `merged_commit`
                    # through `verify_merged_commit_ancestry` but still set
                    # `unit["status"] = done_status` unconditionally,
                    # marking the row TERMINAL/"merged" even when the
                    # verification failed — converting an unverified branch
                    # tip into a false completion `sub_iterate_
                    # finalize_summary`/campaign-mode step 3h would then
                    # publish as done. A sub_iterate row now only takes this
                    # branch when the commit genuinely verifies; otherwise
                    # it falls through to the branch-log check and, failing
                    # that, the reset-to-pending fallback below — the same
                    # "stays blocked, never wrongly unblocked" direction
                    # this module's docstring already requires.
                    if is_sub_iterate:
                        verified = verify_merged_commit_ancestry(result.get("commit"))
                        if verified is not None:
                            unit["status"] = done_status
                            unit["commit"] = result.get("commit")
                            unit["merged_commit"] = verified
                            unit["finished_at"] = now_iso()
                            unit["result_path"] = str(result_path)
                            warnings.append(f"Reconciled {unit['id']}: found result.json with status=complete")
                            continue
                        warnings.append(
                            f"Reconciled {unit['id']}: result.json commit never verified as "
                            "merged — not marking merged"
                        )
                    else:
                        unit["status"] = done_status
                        unit["commit"] = result.get("commit")
                        unit["finished_at"] = now_iso()
                        unit["result_path"] = str(result_path)
                        warnings.append(f"Reconciled {unit['id']}: found result.json with status=complete")
                        continue
            except (json.JSONDecodeError, OSError):
                pass

        # See the pre-R4 history of this exact check in
        # `.shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-autonomous-loop-bloat.md`:
        # a lease-touched row's `branch` field no longer implies `cmd_record`
        # reported back, so the branch-has-commits guess below must never
        # apply to it again, live lease or since-expired.
        if unit.get("lease_touched_at") is None and unit.get("branch"):
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"refs/heads/{unit['branch']}"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and unit.get("head_sha"):
                    log_result = subprocess.run(
                        ["git", "log", "--oneline", f"{unit['head_sha']}..{unit['branch']}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if log_result.returncode == 0 and log_result.stdout.strip():
                        if is_sub_iterate:
                            verified = verify_merged_commit_ancestry(unit.get("commit"))
                            if verified is not None:
                                unit["status"] = done_status
                                unit["merged_commit"] = verified
                                unit["finished_at"] = now_iso()
                                warnings.append(f"Reconciled {unit['id']}: branch has commits since head_sha")
                                continue
                            warnings.append(
                                f"Reconciled {unit['id']}: branch has commits since head_sha but "
                                "commit never verified as merged — not marking merged"
                            )
                        else:
                            unit["status"] = done_status
                            unit["finished_at"] = now_iso()
                            warnings.append(f"Reconciled {unit['id']}: branch has commits since head_sha")
                            continue
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        unit["status"] = "pending"
        # Stage-3 doubt review (LOW #2): a `kind == "sub_iterate"` row
        # falling through to here has NEVER been claimed through the new
        # atomic-claim flow (this function only runs for a legacy
        # `"in_progress"` row) — `_claim_unit`'s own `attempt_id is None`
        # sentinel already bumps `attempt` on ITS next claim; bumping it
        # again here would double-count the row's very first retry and
        # falsify "a reclaim never bumps attempt" for a row this function
        # never actually reclaimed (it only reset a legacy status).
        if is_sub_iterate:
            warnings.append(f"Reconciled {unit['id']}: reset to pending")
        else:
            unit["attempt"] = unit.get("attempt", 0) + 1
            warnings.append(f"Reconciled {unit['id']}: reset to pending (attempt {unit['attempt']})")

    return warnings


def _reconcile_leases(state: dict) -> list[str]:
    """``kind == "sub_iterate"`` reconciliation (R4): LEASE-EXPIRY-ONLY
    reclaim, entirely replacing the legacy result.json/branch-log salvage
    (see :func:`reconcile_in_progress`'s docstring for why that's safe: under
    the wave model, a unit that finishes normally is recorded via
    `cmd_record` at wave-return, BEFORE any reconcile call ever observes it —
    reconcile only ever meets a unit stuck here because a whole campaign
    SESSION died mid-wave, and the only trustworthy signal for "is anyone
    still actually building this" is the lease, not a git-log guess).

    Scoped to `claimed`/`running` only. `merging` is deliberately excluded:
    that state has no associated lease (the merge lane runs synchronously in
    the orchestrator's own process, never inside a leased per-unit
    worktree), so a `merging` row found here reflects a crash mid-merge —
    R5b's staleness-detection job, not this reconcile's.
    """
    warnings: list[str] = []
    for unit in state["units"]:
        if unit["status"] not in ("claimed", "running"):
            continue
        never_leased = "lease_expires_at" not in unit
        if never_leased or is_unit_lease_stale(unit):
            from_status = unit["status"]
            unit["status"] = "pending"
            # Fencing (see loop_claim.py's `_claim_unit`): a reclaim NEVER
            # bumps `attempt` — only the unit's NEXT claim does. `attempt_id`
            # deliberately survives this reset unchanged, as the sentinel
            # that next claim will detect it has already been used once.
            warnings.append(
                f"Reconciled {unit['id']}: lease "
                f"{'never touched' if never_leased else 'expired'} while "
                f"{from_status!r} — reset to pending "
                f"(attempt {unit.get('attempt', 0)} unchanged; next claim increments it)"
            )
    return warnings


def reconcile_in_progress(state: dict, kind: str, state_path) -> list[str]:
    """Reconcile every unit this `kind` considers "currently owned" against
    external evidence of real progress, dispatching on `kind`:

    - ``"sub_iterate"``: :func:`_reconcile_leases` (lease-expiry-only, R4).
    - anything else (``"section"``, or a missing/legacy `kind`): the
      untouched legacy path (:func:`_reconcile_legacy`) — shipwright-build's
      loop has no lease concept and no 9-state vocabulary; behavior here is
      unchanged from before this module existed.
    """
    if kind == "sub_iterate":
        return _reconcile_leases(state)
    return _reconcile_legacy(state, state_path)


# ---------------------------------------------------------------------------
# `autonomous_loop.py` dispatcher glue (R4). Kept HERE, not there: that
# module is bloat-baseline pinned with zero headroom, so every `kind ==
# "sub_iterate"`-only decision body this sub-iterate adds lives in this
# already-exception-filed module instead, leaving `autonomous_loop.py`'s own
# three call sites (`cmd_init`/`cmd_record`/`cmd_finalize`) a couple of lines
# each.
# ---------------------------------------------------------------------------

def cmd_init_sub_iterate_payload(state_path, existing: dict) -> tuple[dict, bool]:
    """The `kind == "sub_iterate"` resume/reinit decision (R4 work item 7).

    Returns ``(payload, mutated)``. `mutated` tells the caller whether
    `existing` was changed in place (via :func:`reconcile_in_progress`) and
    therefore needs saving before returning 0. An EMPTY `payload` (``{}``,
    always paired with ``mutated=False``) means "fall through to a real
    reinit", exactly like `kind == "section"` always has — either there are
    genuinely no units at all, or every remaining row carries a legacy
    status this function doesn't recognize as verified TERMINAL.
    """
    units = existing.get("units", [])
    active = [u for u in units if u["status"] in ACTIVE]
    # `cmd_next` (autonomous_loop.py) is still the live dispatch path for
    # `--branch-strategy serial` sub_iterate campaigns (campaign-mode.md) and
    # still writes the pre-R4 `"in_progress"` status — a value outside the
    # new ACTIVE/RESUMABLE/TERMINAL vocabulary entirely. Left unhandled here,
    # such a unit is invisible to both branches below and this function
    # would silently report `{"action": "resumed", "pending": 0}` for a
    # campaign with a genuinely stuck in-flight unit (external code review,
    # GLM, high). Reconciled via the untouched legacy path, exactly as it
    # always was — compat-scoped to units the OLD `cmd_next` actually
    # claimed, never generalized onto `kind == "sub_iterate"` as a whole.
    legacy_active = [u for u in units if u["status"] == "in_progress"]
    if active or legacy_active:
        warnings = []
        if active:
            warnings += reconcile_in_progress(existing, "sub_iterate", state_path)
        if legacy_active:
            warnings += _reconcile_legacy(existing, state_path)
        return {"action": "reconciled", "warnings": warnings}, True

    resumable = [u for u in units if u["status"] in RESUMABLE]
    if resumable:
        return {"action": "resumed", "pending": len(resumable)}, False

    if units and all(u["status"] in TERMINAL for u in units):
        # Every unit already TERMINAL (merged/failed/held) under the NEW
        # 9-state vocabulary: resume in place with nothing left to claim,
        # rather than reinitializing a finished campaign.
        return {"action": "resumed", "pending": 0}, False

    # Either genuinely empty, or every row already excluded above still
    # carries a legacy status this function doesn't recognize (pre-R4
    # `"complete"`, `"failed"`, `"escalated"`, ...). Those are NOT verified
    # TERMINAL under the new vocabulary — `"escalated"` in particular means
    # unresolved human action, not "done" — so falsely reporting them as
    # `resumed, pending: 0` would hide that from the caller. Fall through to
    # a real reinit, exactly like `kind == "section"` always has for a
    # fully-done state (external Tier-3 PR review, GPT, round 5).
    return {}, False


def sub_iterate_finalize_summary(state: dict) -> tuple[dict | None, dict | None]:
    """`kind == "sub_iterate"` finalize (R4 work item 10): exactly one of
    ``(error, summary)`` is non-``None``. Refuses (`error`) while any unit
    sits outside :data:`TERMINAL`; `summary` counts derive from that set once
    it does not. The `merged -> complete` / `failed -> failed` /
    `held -> {failed, pending}` (by `reason_code`) mapping onto
    `status.json`'s 5-token vocabulary is `campaign-mode.md` step 3h's job
    (R5b) — this function only guarantees every unit is genuinely one of
    `merged`/`failed`/`held` before that mapping ever runs.

    **Compatibility precondition (Stage-3 doubt review, HIGH #1):** this
    function's own :data:`TERMINAL` refusal only understands the 9-state
    vocabulary — it has no fallback for a row still carrying pre-R4 legacy
    statuses (`"complete"`, `"escalated"`, `"in_progress"`). The caller
    (`autonomous_loop.cmd_finalize`) MUST only reach this function once the
    campaign has actually been touched by the new atomic-claim flow (at
    least one unit carries a real `attempt_id`); otherwise it falls through
    to the legacy summary branch unchanged. A future direct caller must
    apply that same gate — this function does not re-check it, to keep its
    own contract ("every remaining unit really is TERMINAL") unambiguous.
    """
    units = state["units"]
    non_terminal = [u for u in units if u["status"] not in TERMINAL]
    if non_terminal:
        return {
            "error": "refused",
            "reason": "one or more units are outside TERMINAL = {merged, failed, held}",
            "non_terminal_ids": [u["id"] for u in non_terminal],
        }, None

    merged = [u for u in units if u["status"] == "merged"]
    failed = [u for u in units if u["status"] == "failed"]
    held = [u for u in units if u["status"] == "held"]
    return None, {
        "loop_id": state["loop_id"],
        "kind": state["kind"],
        "merged": len(merged),
        "failed": len(failed),
        "held": len(held),
        "total": len(units),
        "commits": [u["merged_commit"] for u in merged if u.get("merged_commit")],
    }


def resolve_record_status(kind: str, unit: dict, raw_status: str) -> str:
    """`cmd_record`'s own status write, remapped onto the 9-state vocabulary
    ONLY for a unit that has actually been claimed through the new atomic-
    claim flow (carries a real `attempt_id` — see `enforce_record_fencing`'s
    docstring for why that is the compatibility boundary, not `kind` alone).
    A never-claimed sub_iterate row (today's production campaign loop,
    pre-R5a) and every `kind == "section"` row both pass `raw_status`
    through UNCHANGED, exactly as before this function existed — this is
    additive, not a redefinition of `cmd_record`'s historical contract.

    `"complete" -> "built"` (`running -> built`, runner finished — 3f-bis
    picks it up from there); anything else (`"failed"`, `"escalated"`, or an
    already-invalid value `_validate_result` let through) `-> "failed"`,
    matching `_map_unit_status`'s own `failed`/`escalated -> failed`
    collapse — an escalated unit never got to run further either way.
    """
    if kind != "sub_iterate" or unit.get("attempt_id") is None:
        return raw_status
    return "built" if raw_status == "complete" else "failed"


def enforce_record_fencing(state_path, state_peek: dict, unit_id: str, attempt_id: str | None,
                            raw_text: str, *, target_status: str | None = None) -> int | None:
    """`cmd_record`'s `kind == "sub_iterate"` fencing pre-check (R4 work
    items 4/5). Returns a non-``None`` exit code (``1`` missing token, ``5``
    stale token) when `cmd_record` must reject immediately WITHOUT touching
    state, else ``None`` to proceed with the normal record path. Only ever
    called once the caller has confirmed ``state_peek["kind"] ==
    "sub_iterate"``.

    **Compatibility scope, deliberate:** the fencing invariant is stated as
    "every mutation of a CLAIMED-OR-LATER unit" — a row that has never been
    claimed through the new atomic-claim flow (`loop_claim.cmd_next_batch`,
    which is the ONLY minter of `attempt_id`) carries no `attempt_id` at
    all, and there is nothing yet to fence against. This matters concretely:
    `campaign-mode.md` step 3f (unedited by this sub-iterate — that flip is
    R5a's) still calls `record` with no `--attempt-id` today, for every
    currently-running campaign, via the untouched single-unit
    `autonomous_loop.cmd_next`/`cmd_record` path — a fencing check that
    unconditionally required the flag the moment merged would break every
    live campaign before R5a ever wires the new claim mechanics in. So: a
    unit row with no `attempt_id` yet skips this check entirely (`None` —
    proceed normally, byte-identical to pre-R4 behavior); only once a row
    has actually been claimed (carries a real `attempt_id`) does a
    `cmd_record` call for it need to supply a matching one.

    **Call it twice, trust only the second (external code review, OpenAI,
    high).** `cmd_record`'s early call (no `target_status`, a fast fail
    before the cost of parsing/validating `raw_text`) reads a `state_peek`
    taken BEFORE that lock was released — a reclaim can legally happen in
    the gap between that read and the eventual write. Every actual MUTATION
    must call this function AGAIN, passing the state loaded fresh inside
    the SAME lock acquisition that performs the write, with `target_status`
    set to whatever this call is about to write. `target_status` also closes
    a separate gap (external code review, OpenAI, medium): a fencing-token
    match alone said nothing about whether the row's CURRENT status may
    legally reach `target_status` at all. `target_status=None` (the
    fast-fail call) skips this second check on purpose — no target is known
    yet at that point.
    """
    unit_row = find_unit_row(state_peek, unit_id)
    if unit_row is None or unit_row.get("attempt_id") is None:
        return None
    if not attempt_id:
        print("ERROR: --attempt-id is required to record a unit claimed via the atomic-claim flow",
              file=sys.stderr)
        return 1
    if not validate_attempt_token(unit_row, attempt_id):
        loop_id = state_peek.get("loop_id", "")
        try:
            path = rejected_payload_path(state_path, loop_id, unit_id, attempt_id)
        except ValueError as exc:
            # `unit_id` here is the CALLER's `--unit` value, not yet proven
            # to be one of this loop's real rows at this point in the
            # fencing check — a malformed one must fail closed with a clean
            # error, not an uncaught traceback (external review, high).
            print(f"ERROR: refusing to record stale-attempt payload: {exc}", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw_text, encoding="utf-8")
        print(json.dumps({"recorded": False, "status": "stale_attempt", "unit": unit_id}))
        return 5
    if target_status is not None and not is_legal_transition(unit_row["status"], target_status):
        print(f"ERROR: unit {unit_id!r} is {unit_row['status']!r}, cannot record a "
              f"{target_status!r} result (not a legal transition) — a reclaim or a "
              "duplicate/out-of-order record call is the likely cause", file=sys.stderr)
        return 1
    return None
