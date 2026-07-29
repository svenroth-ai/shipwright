"""Which removals THIS run declared — and whose declarations they are.

Split from :mod:`silent_revert` for the same reason
:mod:`silent_revert_reading` and :mod:`silent_revert_filters` were: the detector
file is at the repo's 300-line source cap. The seam is real as well as
budgetary — everything here reads a *declaration by the operator*, nothing here
inspects the repository.

**Why attribution matters more here than anywhere else.**
``shipwright_test_results.json`` is a DERIVED_SNAPSHOT, and the F11 integration
this very gate runs behind (``ensure_current`` → ``integrate_main`` →
``restore_derived_to_head``) rewinds it to ``HEAD``. For the ledger and
surface-verification gates that means a stale block *fails to catch* something.
Here it is the other way round: a previous run's ``declared_removals`` sitting
in this run's worktree would **excuse** paths this run never declared — the one
place where reading the wrong run's evidence actively unblocks a real revert.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from ._iterate_latest import STATE_MALFORMED, read_iterate_latest  # noqa: E402

__all__ = ["attributed_declared_removals", "covered_by_declaration"]


def _dicts(value: object) -> list[dict]:
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _unattributed_declared_removals(project_root) -> list[dict]:
    """``iterate_latest.declared_removals`` — the stated intentional removals.

    A missing or malformed file yields ``[]``: an unreadable declaration must
    not silently excuse a removal.

    **Private on purpose.** It cannot tell whose declarations it is reading, so
    a caller that reached it would have the false-exemption path back
    (external code review, openai #2). The only legitimate use is counting what
    :func:`attributed_declared_removals` is about to DISREGARD, so the message
    can say how much was ignored.
    """
    path = Path(project_root) / "shipwright_test_results.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    # `or {}` guards None but NOT a truthy non-mapping: `{"iterate_latest": ["x"]}`
    # is valid JSON, reaches here, and `.get` on a list raises. The typed reader
    # already calls that shape `malformed`; this one must agree rather than crash
    # the gate that was about to report it (external code review, openai #1).
    latest = data.get("iterate_latest")
    if not isinstance(latest, dict):
        return []
    return _dicts(latest.get("declared_removals"))


def attributed_declared_removals(project_root, run_id: str) -> tuple[list[dict], str | None]:
    """``(entries, problem)`` — declarations, but only this run's.

    The per-run F5c entry wins, exactly as for the other two blocks: it is not a
    derived snapshot, so the restore cannot reach it.

    A non-current shared block yields no entries. Whether it also yields a
    ``problem`` depends on whether anything was actually DISREGARDED — the
    distinction matters, and it is not the same rule as for the ledger and F0.5
    blocks:

    * **Declarations found but not this run's** → problem. Something was
      disregarded and only the operator can say whether that is fine.
    * **The file is malformed** → problem, unconditionally. This is the one
      state where "no declarations" cannot be told from "declarations we could
      not read", so silence would be a guess (external code review, openai).
    * **No declarations anywhere** (missing / unattributed / foreign-but-empty)
      → no problem. Nothing is being disregarded, and nothing is excused: the
      caller gets ``[]``, so every dropped line still blocks.

    That last case is a deliberate departure from "fail closed on EVERY
    non-current state", and the reason is that declarations are an *exception*
    mechanism rather than evidence. The ledger and F0.5 gates demand evidence to
    PASS, so absence must block them. Here absence is the normal state of a
    healthy run, and blocking it would mean every iterate that never removed
    anything had to write ``declared_removals: []`` to prove a negative —
    ceremony on 100% of runs, defending against nothing, and precisely the kind
    of always-red gate this repo has repeatedly had to un-teach.
    """
    entry = find_entry_by_run_id(Path(project_root), run_id) if run_id else None
    per_run = (entry or {}).get("declared_removals")
    if isinstance(per_run, list):
        return _dicts(per_run), None
    if per_run is not None:
        # Symmetric with the `malformed` rule below, and MORE likely to fire:
        # the F5c entry is the home operators hand-write into `--entry-json`, so
        # it is the likelier place to get the shape wrong. Falling through to the
        # shared file here would answer "none declared" to a question the entry
        # tried and failed to answer (Stage-2 code review).
        return [], (
            "the F5c entry's declared_removals is not a list "
            f"({type(per_run).__name__}), so whether this run declared any "
            "removal is unknowable from it"
        )

    latest = read_iterate_latest(Path(project_root), run_id)
    if latest.is_current:
        return _dicts((latest.block or {}).get("declared_removals")), None

    if latest.state == STATE_MALFORMED:
        return [], (
            f"declarations could not be read at all: {latest.detail}. "
            "Whether this run declared any removal is unknowable from that "
            "file, so it is reported rather than assumed to be none"
        )

    ignored = _unattributed_declared_removals(project_root)
    if not ignored:
        return [], None
    return [], (
        f"{len(ignored)} declared removal(s) were ignored: {latest.detail}. "
        "A declaration only excuses the run that made it"
    )


def covered_by_declaration(path: str, declarations) -> bool:
    """True when the operator declared this path's removal WITH a reason.

    Lives beside the reader rather than in the detector: both halves of "was
    this removal declared" — whose declarations count, and whether a given path
    is among them — are one concern, and the detector is at its 300-line cap.
    A blank reason does not cover: "declared with no reason" is how a removal
    gets waved through, which is the escape hatch this whole check exists to
    keep narrow.
    """
    for entry in declarations or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("path", "")) == path and str(entry.get("reason", "")).strip():
            return True
    return False
