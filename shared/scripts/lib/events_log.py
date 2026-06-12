"""Resolution of the ``shipwright_events.jsonl`` event log.

Single source of truth for *locating* the unified event log. The log is a
**per-tree, version-controlled artifact**: it is tracked (where a project opts
in via ``!/shipwright_events.jsonl``) and the iterate that produces a new
``work_completed`` event **commits it** as part of the F6 commit, so it ships
through the iterate PR and merges to ``main`` like every other artifact.

``resolve_events_path`` therefore returns ``project_root / EVENT_FILE``
**literally** — including from inside a ``/shipwright-iterate`` worktree, where
``project_root`` is the worktree root. The worktree's copy is NOT a throwaway:
F6 stages it and the PR carries it to ``main``.

History (iterate-2026-05-29-events-jsonl-worktree-commit)
---------------------------------------------------------
This resolver used to redirect to the **main** repo via ``git rev-parse
--git-common-dir`` so a worktree-local copy would not be lost to
``git worktree remove``. That was wrong for the worktree-commit flow: the
``work_completed`` event landed as an **uncommitted line in the main tree**,
never entered the iterate PR, and required a manual ``chore(events)`` backfill.
The redirect is gone; the event now rides the PR.

``resolve_main_repo_root`` relocated
------------------------------------
The git-common-dir primitive ``resolve_main_repo_root`` no longer lives here. It
was a repo-root helper squatting in the event-log module — retained here in
2026-05-29 only because the events-path redirect removal happened in this file.
As of ``iterate-2026-06-12-repo-root-resolver-relocate`` the implementation lives
in its thematic home ``lib/repo_root.py`` (beside ``main_repo_root_or``); this
module re-exports it via a thin **lazy** shim so existing
``from lib.events_log import resolve_main_repo_root`` imports keep working. The
lazy (call-time) import avoids the
``events_log → repo_root → worktree_isolation → events_log`` cycle a module-level
re-export would introduce. New code should import it from ``lib.repo_root``.

Relationship to ``shipwright-compliance``'s
``collectors.change_history._resolve_events_path``
----------------------------------------------------------------------
That compliance-plugin function is the standalone-distributable twin of this
one (the compliance plugin cannot import ``shared/scripts/lib`` without a
cross-plugin path bootstrap). ``integration-tests/test_events_log_parity.py``
pins the two to the same answer; both resolve to the per-tree
``project_root / EVENT_FILE``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EVENT_FILE = "shipwright_events.jsonl"


def resolve_main_repo_root(project_root: Path | str) -> Path | None:
    """Back-compat re-export — the implementation lives in ``lib.repo_root``.

    Relocated in ``iterate-2026-06-12-repo-root-resolver-relocate`` (it was a
    repo-root primitive squatting in the event-log module). This thin delegating
    shim keeps existing ``from lib.events_log import resolve_main_repo_root``
    imports working. The two remaining in-repo consumers stay on this re-export on
    purpose — both are already-oversized grandfathered files where adding a
    ``lib.repo_root`` import line would ratchet bloat for a cosmetic change: the
    F11 verifier ``tools/verifiers/iterate_checks.py``, and the compliance Group-F
    detective ``group_f.py`` (which also reaches it through
    ``audit_adapters.load_shared_lib("events_log")``). New code should import it
    from ``lib.repo_root``.

    The import is **lazy** (call-time) on purpose: a module-level
    ``from lib.repo_root import resolve_main_repo_root`` would close the cycle
    ``events_log → repo_root → worktree_isolation → events_log``
    (``worktree_isolation`` imports ``events_log.EVENT_FILE``), raising
    ``ImportError`` under any import order where ``repo_root`` /
    ``worktree_isolation`` loads first.
    """
    from lib.repo_root import resolve_main_repo_root as _impl  # noqa: PLC0415

    return _impl(project_root)


def resolve_events_path(project_root: Path | str) -> Path:
    """Return the path to ``shipwright_events.jsonl`` — ``project_root / EVENT_FILE``.

    The event log is a **per-tree, version-controlled artifact**. From inside a
    ``/shipwright-iterate`` worktree ``project_root`` is the worktree root and
    the iterate commits the log via F6, so the path is the worktree-local copy
    — NOT redirected to the main repo. In a plain checkout this is the repo's
    own log. No git call is made (the resolution is a literal join), so this is
    decoupled from ``resolve_main_repo_root``.

    See the module docstring for the history (this used to redirect to the main
    repo, which orphaned the work_completed event outside the iterate PR).
    """
    return Path(project_root) / EVENT_FILE


def latest_event_dt(project_root: Path | str) -> datetime | None:
    """Return the UTC datetime of the most recent event, or ``None``.

    Iterates ``shipwright_events.jsonl`` line-by-line (worktree-aware via
    :func:`resolve_events_path`), parses only each line's ``ts`` field,
    and returns the chronologically-latest one as a ``datetime`` in UTC.

    Designed as a deterministic substitute for ``datetime.now()`` in
    render headers — two calls against the same events.jsonl produce the
    same answer, so ``Generated:`` / ``Updated:`` banners no longer drift
    on every Stop hook. The audit-trail's "wann ist was passiert" lives
    in the events themselves; the render banner just summarises "data as
    of which event".

    F7-ordering semantic
    --------------------
    The iterate's own F7 ``work_completed`` event is written AFTER the
    F6 commit (so F7 can include the new commit hash). ``finalize_iterate``
    renders the dashboard + compliance markdowns BEFORE F6 but writes the
    handoff in a step that runs AFTER ``record_event``. Concretely the
    rendered banners therefore reflect:

      * ``build_dashboard.md``, ``.shipwright/compliance/*.md``: timestamp
        of the PREVIOUS iterate's F7 event (this iterate's F7 doesn't
        exist yet at render time).
      * ``session_handoff.md``: timestamp of the CURRENT iterate's F7
        event (its ``_generate_handoff`` runs after ``_record_event``).

    The inconsistency is accepted as the price of "no commit amends" —
    F7 cannot run before F6 (it needs the commit SHA), and the rendered
    markdown files must be in the F6 commit. Operator-facing impact: the
    dashboard's "data as of" banner trails by one iterate. Audit-trail
    impact: zero — the actual events are all in the log, this is just a
    rendering banner.

    Returns
    -------
    ``datetime`` in UTC, or ``None`` when:
      * the event log is missing,
      * the log is empty,
      * every line is corrupt and unparseable,
      * no line has a parseable ``ts`` field.

    Robustness
    ----------
    * Corrupt JSON lines are skipped silently (the log is append-only;
      a partial write halfway through one event is the dominant cause
      of corruption, and amplifying that into a fatal exception would
      brick every renderer until the operator hand-fixed the file).
    * ISO8601 timestamps with either ``Z`` or ``+00:00`` suffix are
      both accepted. Non-UTC offsets (e.g. ``+02:00``) are correctly
      ordered by *instant* via ``datetime`` comparison, not by
      lexicographic byte comparison of the string — a 06:00 UTC event
      written as ``08:00+02:00`` correctly loses to a 07:30Z event.
      Naive ``ts`` (no offset suffix) is interpreted as UTC, matching
      the event-log convention used by ``record_event.py``.
    """
    path = resolve_events_path(project_root)
    if not path.exists():
        return None

    latest: datetime | None = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = event.get("ts")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    # `Z` suffix is ISO8601-valid but not accepted by
                    # `fromisoformat` until Python 3.11. Normalise.
                    normalised = ts_raw.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(normalised)
                except ValueError:
                    continue
                # Coerce to UTC: naive datetimes are interpreted as UTC
                # (the event-log convention); aware datetimes are
                # converted via astimezone.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                if latest is None or dt > latest:
                    latest = dt
    except OSError:
        return None

    return latest


def finalized_run_ids(project_root: Path | str) -> set[str] | None:
    """Run_ids in this tree's event log (``adr_id`` + ``run_id`` fields; an
    iterate's run_id is its ``work_completed`` ``adr_id``, ADR-059), or ``None``
    when the log is absent **or unreadable**. The ownership ledger that scopes
    the whole-set arch-drift checkers (the Group-F ``F5`` detective + the drift
    test) to this tree's lineage, excluding cross-branch campaign sibling drops
    in the shared main-rooted ``decision-drops`` dir (documented only on the
    sibling's unmerged branch). ``None`` (ownership undeterminable) → callers
    fail open to whole-set checking (conservative for a drift gate: never weaker,
    never crash-on-read). Existing-but-empty → empty set; corrupt/blank skipped.
    """
    path = resolve_events_path(project_root)
    if not path.exists():
        return None
    run_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # corrupt or blank line
                if not isinstance(event, dict):
                    continue
                for key in ("adr_id", "run_id"):
                    val = event.get(key)
                    if isinstance(val, str) and val:
                        run_ids.add(val)
    except OSError:
        return None  # unreadable → undeterminable, same as absent → fail open
    return run_ids
