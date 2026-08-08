"""Run-id resolution for the Stop-time audits (plan § 5.3).

Split out of ``_resolution.py`` (300-LOC ceiling; unrelated concerns already
hosted there — same reasoning as the earlier ``_engagement`` split).
``_resolution`` re-exports :func:`resolve_run_id` so existing
``phase_quality.resolve_run_id`` callers are unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402
# Imported as MODULES, and eagerly. Eagerly because a function-local import
# would execute after the Stop hook's once-per-Stop claim is taken, turning a
# packaging fault into a burned claim + a silently unaudited Stop; the measured
# cost of doing it here instead is 2.7 ms on a 61 ms package import. As modules
# because attribute lookup happens at call time, which keeps
# ``monkeypatch.setattr(worktree_isolation, "read_run_pointer", ...)`` working
# from either namespace (ADR-045: patch the module object, never a rebound name).
from lib import repo_root, worktree_isolation  # noqa: E402

from ._constants import is_sentinel_run  # noqa: E402
from ._worktree_identity import (  # noqa: E402
    fast_main_root,
    is_worktree_of,
    pointer_owned_by_session,
)


def pointer_run_id(project_root: Path, session_id: str) -> str | None:
    """The canonical iterate run_id for ``session_id``, or ``None``.

    ``setup_iterate_worktree.py`` writes a per-session run pointer at B1a —
    before any build work, for every iterate, unconditionally — into
    ``<main_root>/.shipwright/iterate_active/<session_id>.json``. It is keyed by
    exactly the value the Stop hook already holds, which makes it the only
    evidence that answers *which run is THIS session executing*; the other
    sources in :func:`resolve_run_id` are project- or process-global and can
    name a different run entirely.

    The pointer lives in the MAIN tree while an iterate's cwd is its worktree,
    so the main root is resolved first. ``main_repo_root_or`` returns
    ``project_root`` unchanged for a plain checkout, a non-git directory, and
    any git failure — so one code path covers all three shapes.

    **Fail-open, but narrowly.** ``read_run_pointer`` catches ``JSONDecodeError``
    and ``OSError``, but it neither checks the decoded value's *shape* (valid
    non-object JSON is returned as-is) nor catches ``UnicodeDecodeError`` from
    ``read_text(encoding="utf-8")`` — a ``ValueError`` subclass. That gap is
    load-bearing here: :func:`resolve_run_id` runs in
    ``audit_phase_quality_on_stop`` OUTSIDE its per-phase ``try`` and AFTER the
    once-per-Stop claim is taken, so a raise would kill the audit for every
    phase while the sibling fan-out invocations no-op on the burned claim —
    the same shape as the ``isinstance(data, dict)`` bug recorded in
    :func:`resolve_run_id`. Hence ``OSError``/``ValueError``/``RecursionError``
    here and an explicit ``dict`` check, rather than a blanket
    ``except Exception`` that would also mask a genuine defect in the imported
    helpers.

    A pointer is honoured only when it is an object, its payload
    ``session_id`` names the session being audited (a filename alone is not
    proof of ownership — two session ids can sanitise to the same name), its
    ``worktree_path`` still exists, and its ``run_id`` is a non-empty,
    non-sentinel string. Nothing else in the payload is consumed.

    **Why the liveness check.** Pointers are reaped only by
    ``prune_stale_run_pointers``, which runs only from
    ``setup_iterate_worktree`` and only unlinks pointers whose worktree is
    gone — so an orphaned pointer can outlive its run and would otherwise keep
    binding a finished run to later, unrelated work in the same session. The
    sibling consumer of this same artifact (``iterate_stop_finalize``) already
    refuses a pointer whose worktree is not a live directory; this matches it.
    On its own this bounds, but does not eliminate, staleness: a worktree
    RETAINED after its PR merges still looks live. What closes the gap is
    ``lib.run_pointer_retirement.retire_run_pointer`` — F11 calls it on a
    DELIVERED exit, giving the pointer an explicit end-of-run signal instead
    of leaving liveness to infer from the worktree directory alone
    (trg-276994a4, fixed).
    """
    if is_sentinel_run(session_id):
        return None

    try:
        # NB: unconditional `git rev-parse` — the pointer lives in the MAIN
        # tree, and only git can tell us where that is from a linked worktree.
        main_root = repo_root.main_repo_root_or(project_root)
        pointer = worktree_isolation.read_run_pointer(main_root, session_id)
    except (OSError, ValueError, RecursionError):
        # ValueError covers UnicodeDecodeError + JSONDecodeError; RecursionError
        # comes from json.loads on a deeply-nested pointer and is NOT a
        # ValueError (same reasoning as lib/jsonl_records).
        return None

    if not isinstance(pointer, dict):
        return None
    payload_session = pointer.get("session_id")
    # isinstance before compare: coercing via str() would let a non-string
    # payload bind whenever its repr matches — `42` against an audited "42",
    # `true` against "True" — which is exactly the structural spoofing this
    # check exists to refuse.
    if not isinstance(payload_session, str):
        return None
    if payload_session.strip() != session_id:
        return None
    if not _worktree_is_live(pointer.get("worktree_path")):
        return None

    run_id = pointer.get("run_id")
    # is_sentinel_run strips and lower-cases internally, so " unknown " and
    # "UNKNOWN" are both refused here — the check does not need a pre-strip.
    if not isinstance(run_id, str) or is_sentinel_run(run_id):
        return None
    # Returned verbatim apart from surrounding whitespace. Normalising it is
    # deliberate: the resolved id becomes an audit KEY (finding filenames, the
    # already_audited triple, triage card labels), and a padded copy would key
    # the same run as if it were a different one.
    return run_id.strip()


def pointer_worktree_root(cwd: Path, session_id: str) -> Path | None:
    """This session's active iterate worktree, resolved from ``cwd`` — or
    ``None``. Used by ``audit_phase_quality_on_stop.py`` to root the
    phase-quality Stop audit there instead of wherever ``resolve_project_
    root``'s plain cwd/env/subdir chain lands.

    Exists because a Stop-subprocess's cwd is the MAIN repo even while an
    iterate runs in a linked worktree — the same fact
    ``context_cost_session.resolve_active_project_root`` was built to work
    around, and the reason trg-b36fd844's re-audit trigger (``already_audited``
    via ``_staleness.is_stale_finding``) could not observe F5c's ledger
    entry appearing: that entry lands in the WORKTREE, so an audit rooted at
    main never saw the transition (external review, this fix). Re-validates
    independently rather than importing ``context_cost_session`` — this
    package's own convention (see ``iterate_stop_finalize._active_worktree_
    root``) is that each caller re-checks pointer validity locally rather
    than sharing one cross-module import.

    Ownership and identity are both verified (external review, round 3): the
    pointer's own ``session_id`` must name THIS session (closing a gap where
    two ids sanitising to the same pointer filename could redirect this
    session's audit into the other's worktree), and the resolved path must be
    a genuine linked worktree of ``main_root`` (:func:`is_worktree_of`), not
    merely a directory a spoofed ``worktree_path`` happens to name.
    """
    if is_sentinel_run(session_id):
        return None
    try:
        main_root = fast_main_root(cwd)
        if main_root is None:
            resolved = repo_root.resolve_main_repo_root(cwd)
            if resolved is None:
                return None
            main_root = resolved.resolve()
        pointer = worktree_isolation.read_run_pointer(main_root, session_id)
        if not pointer_owned_by_session(pointer, session_id):
            return None
        worktree_str = pointer.get("worktree_path", "")
        if not worktree_str:
            return None
        worktree = Path(worktree_str).resolve()
        if not worktree.is_dir():
            return None
        # is_worktree_of alone proves identity via the gitdir chain
        # (doubt-review D5) — a prior relative_to(main_root) pre-check added
        # no coverage and silently rejected a worktree git legitimately
        # placed outside main_root's own tree; dropped rather than logged.
        if not is_worktree_of(worktree, main_root):
            return None
        return worktree
    except Exception:  # noqa: BLE001 — best-effort, caller falls back
        return None


def _worktree_is_live(worktree_path: object) -> bool:
    """True when the pointer's worktree is still a directory on disk."""
    if not isinstance(worktree_path, str) or not worktree_path.strip():
        return False
    try:
        return Path(worktree_path).is_dir()
    except (OSError, ValueError):
        return False


def resolve_run_id(project_root: Path, session_id: str) -> str:
    """Composite-fallback run_id resolution (plan § 5.3).

    Priority:
    0. the per-session iterate run pointer (:func:`pointer_run_id`)
    1. ``shipwright_run_config.json::run_id``
    2. ``events.jsonl`` latest ``run_started`` event
    3. ``SHIPWRIGHT_LOOP_ID`` + ``SHIPWRIGHT_LOOP_UNIT_ID``
    4. ``session_id`` itself (standalone)

    Step 0 is what makes the iterate spec checks (S2, S3, W2, S9, S10)
    evaluable at all. For an iterate, steps 1-3 are structurally inert — nothing
    writes a top-level ``run_id``, no producer emits a ``run_started`` event,
    and the loop vars are campaign-only — so the audit used to be handed the
    raw session UUID (or ``"unknown"``). Neither is an ``iterate_history`` key,
    so ``unresolvable_run_id_skip`` correctly refused to let an unrelated run's
    complexity or category decide those checks' verdicts, and the whole family
    SKIPped on every real invocation
    (iterate-2026-08-06-resolve-run-id-seam).

    **What step 0 does and does not buy.** It makes the audit's ``run_id`` the
    canonical one — verified in production: the Stop hook reports
    ``run=iterate-<date>-<slug>`` where it previously reported the session
    UUID, so findings and the triage cards ``audit_compliance_on_stop`` labels
    are attributable to the run, and a SKIP now names it. Whether the five
    guarded checks then *evaluate* is a separate condition this does not
    change: they need the audited tree to hold the run's own ledger entry, and
    F5c writes that into the run's WORKTREE. The hook resolves ``project_root``
    from the session's cwd, which is the MAIN repo even mid-iterate — that used
    to leave an in-flight run's audit rooted at main, unable to observe the
    ledger entry appearing (fail-safe, but a permanent SKIP). Closed by
    :func:`pointer_worktree_root`, which the hook now prefers: it redirects
    ``project_root`` to the run's own worktree via the same per-session pointer
    this function reads, so the re-audit this docstring's step 0 exists for can
    actually fire (trg-b36fd844, external review round 2).

    ``session_id`` is normalised ONCE here and that one value is reused for the
    sentinel test, the pointer lookup, the payload comparison and the tail —
    the sole production caller already passes a stripped value, so this only
    removes the possibility of the four disagreeing. One consequence beyond a
    pure move: a whitespace-only ``session_id`` now yields ``"unknown"`` rather
    than the whitespace itself. Unreachable from either production caller (both
    pass ``.strip() or "unknown"``), and it makes the tail agree with the
    sentinel test rather than contradict it.

    The ``isinstance(data, dict)`` check is load-bearing: valid JSON that is not
    an object (``[1, 2]``, ``null``) made ``data.get`` raise ``AttributeError``,
    which the ``except`` below does not catch. This runs FIRST in the Stop hook,
    outside its per-phase ``try`` and after the once-per-Stop claim is taken — so
    that raise killed the audit for EVERY phase and the sibling invocations then
    no-oped on the burned claim.
    """
    session_id = (session_id or "").strip()

    from_pointer = pointer_run_id(project_root, session_id)
    if from_pointer:
        return from_pointer

    run_config = project_root / "shipwright_run_config.json"
    if run_config.exists():
        try:
            data = json.loads(run_config.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                run_id = data.get("run_id")
                if isinstance(run_id, str) and run_id:
                    return run_id
        # ValueError (not just JSONDecodeError) because read_text raises
        # UnicodeDecodeError on a non-UTF-8 run config — the same post-claim
        # escape the pointer branch above guards against.
        except (ValueError, OSError, RecursionError):
            pass

    # Via the events_log SSoT rather than a raw join. The two are equivalent
    # (``resolve_events_path`` is a literal ``project_root / EVENT_FILE``), so
    # this is behaviour-identical — but it retires the pre-split
    # ``_MAIN_REPO_ONLY`` exemption instead of carrying it to a new file.
    events_path = resolve_events_path(project_root)
    if events_path.exists():
        try:
            latest_run_id: str | None = None
            # Record-boundary recovery via the shared SSoT: a merge=union merge can
            # leave two records on one physical line, and the pre-fix per-line
            # json.loads dropped BOTH — silently falling through to the session-id
            # fallback and mis-attributing every audit row keyed on the resolved run
            # (iterate-2026-07-20-events-record-boundary-remainder). read_jsonl_records
            # returns only JSON objects, in wire order, so latest-wins is preserved.
            for obj in read_jsonl_records(events_path).records:
                if obj.get("type") == "run_started":
                    rid = obj.get("run_id") or obj.get("id")
                    if isinstance(rid, str) and rid:
                        latest_run_id = rid
            if latest_run_id:
                return latest_run_id
        except OSError:
            pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID", "").strip()
    loop_unit = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID", "").strip()
    if loop_id and loop_unit:
        return f"{loop_id}-{loop_unit}"
    if loop_id:
        return loop_id

    return session_id or "unknown"


__all__ = ["pointer_run_id", "pointer_worktree_root", "resolve_run_id"]
