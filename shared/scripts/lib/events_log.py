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
--git-common-dir``; that orphaned the ``work_completed`` event outside the iterate
PR (an uncommitted main-tree line needing a manual ``chore(events)`` backfill).
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

from datetime import datetime, timezone
from pathlib import Path

# Record-boundary SSoT, imported to survive THREE load contexts (full rationale:
# the iterate spec's Mini-plan AC15, pinned by test_events_log_load_contexts):
#   1. package member ``lib.events_log`` -- relative import works.
#   2. by file location under a sentinel name (``audit_adapters.load_shared_lib``)
#      -- no parent package.
#   3. flat, ``shared/scripts/lib`` on sys.path -- no package either.
# Contexts 2+3 share the by-path fallback. By-NAME fallbacks (``from
# lib.jsonl_records`` / ``from jsonl_records``) both broke production: the first
# rebinds ``sys.modules['lib']`` to shared's package, the second needs a sys.path
# entry no loader inserts. By-path touches no namespace and resolves COPY-LOCALLY.
# ONE SOURCE, SEVERAL RUNTIME OBJECTS: cross-boundary ``isinstance(x, RecordRead)`` is False.
try:
    from .jsonl_records import read_jsonl_records
except ImportError:  # contexts 2 + 3 — see above.
    import hashlib as _hashlib
    import importlib.util as _importlib_util
    import sys as _sys

    _jr_path = Path(__file__).resolve().parent / "jsonl_records.py"
    # Key the cache on the resolved DIRECTORY, not on a bare constant: two copies
    # of this file in one process (worktree + plugin cache — the very drift the
    # copy-local resolution above guards) would otherwise share the first copy's
    # parser under one sentinel name.
    _JR_SENTINEL = "_shipwright_events_log_jsonl_records_" + _hashlib.sha256(
        str(_jr_path.parent).encode("utf-8")
    ).hexdigest()[:12]
    _jr_mod = _sys.modules.get(_JR_SENTINEL)
    if _jr_mod is None:
        # `.is_file()` is the REAL existence check: `spec_from_file_location`
        # does not stat, so a missing file still yields a valid spec with a
        # SourceFileLoader and `exec_module` would raise FileNotFoundError — an
        # OSError escaping this `except ImportError` handler, invisible to
        # callers that guard the import with `except ImportError`.
        if not _jr_path.is_file():
            raise ImportError(f"cannot locate the shared record-boundary leaf: {_jr_path}")
        _jr_spec = _importlib_util.spec_from_file_location(_JR_SENTINEL, _jr_path)
        if _jr_spec is None or _jr_spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load a spec for {_jr_path}")
        _jr_mod = _importlib_util.module_from_spec(_jr_spec)
        # Register BEFORE exec_module: `jsonl_records` defines @dataclass types,
        # and stdlib `dataclasses` resolves `cls.__module__` through sys.modules
        # at CLASS-CREATION time. Without this the exec dies with
        # "'NoneType' object has no attribute '__dict__'". The identical
        # requirement is documented in audit_adapters.load_shared_lib.
        _sys.modules[_JR_SENTINEL] = _jr_mod
        try:
            _jr_spec.loader.exec_module(_jr_mod)
        except Exception:
            _sys.modules.pop(_JR_SENTINEL, None)
            raise
    read_jsonl_records = _jr_mod.read_jsonl_records

EVENT_FILE = "shipwright_events.jsonl"
DROPS_DIR = ".shipwright/events/drops"
ARCHIVE_DIR = ".shipwright/events/archive"
QUARANTINE_DIR = ".shipwright/events/quarantine"
#: Every folder of the drops layout. Classifiers (paths that are bookkeeping, churn,
#: generated, uncounted ...) must list ALL of them -- the S3 guard checks it.
EVENT_FOLDERS = (DROPS_DIR, ARCHIVE_DIR, QUARANTINE_DIR)


#: The pre-move root-level names. Not read, not written; their mere presence is reported (readers never take it for
#: "no events") and refused (writers). Mirrors ``events_sentinel.MOVED_FOLDERS`` (flat-loaded, so it cannot import this).
OLD_ROOT_FOLDERS = ("shipwright_events.d", "shipwright_events.archive", "shipwright_events.quarantine")


#: Names an operating system leaves in a folder: a folder holding only these is not an event folder.
OS_JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def real_event_dir(project_root: Path | str, rel: str) -> bool:
    """``rel`` is a directory reached through real directories only: NO component below the root is a symlink.

    The folders are nested now (``.shipwright/events/drops``), so a guard on the leaf alone would let a hostile
    clone ship ``.shipwright`` or ``.shipwright/events`` as a link to a directory outside the tree.
    """
    cur = Path(project_root)
    for part in rel.split("/"):
        cur = cur / part
        if cur.is_symlink():
            return False
    return cur.is_dir()


def old_root_folders(project_root: Path | str) -> list[str]:
    """Old root-level event folders that still hold something (a real directory; OS junk alone does not count)."""
    root = Path(project_root)
    found = []
    for old in OLD_ROOT_FOLDERS:
        if real_event_dir(root, old):
            try:
                if any(p.name not in OS_JUNK_NAMES for p in (root / old).iterdir()):
                    found.append(old)
            except OSError:
                found.append(old)  # cannot tell what is in it: treat as present, never as "no events"
    return found


def is_event_folder_path(rel: str) -> bool:
    """True for a repo-relative path inside (or naming) one of :data:`EVENT_FOLDERS`."""
    norm = rel.strip().replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return any(norm == f or norm.startswith(f + "/") for f in EVENT_FOLDERS)


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

    The import is **lazy** (call-time) on purpose — and stays lazy even though the
    old ``events_log → repo_root → worktree_isolation → events_log`` import cycle
    was removed in ``iterate-2026-06-28-codeql-import-cycles`` (``repo_root`` now
    depends on the leaf ``lib.git_base``, not ``worktree_isolation``). The
    still-live reason is import-context isolation: the compliance Group-F detective
    loads this module via ``audit_adapters.load_shared_lib("events_log")``, which
    ``exec``s it from file under a sentinel name to keep the ``lib`` namespace OUT
    of ``sys.modules`` (ADR-044 — otherwise shared's ``lib`` shadows the compliance
    plugin's own ``lib``). A module-level ``from lib.repo_root import …`` would run
    during that ``exec`` and bind/pollute ``sys.modules['lib']``, defeating that
    isolation; deferring to call-time keeps the loader namespace-clean. So: do NOT
    hoist this to module scope even though the cycle is gone.
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


def event_files(project_root: Path | str) -> list[Path]:
    """Legacy file (listed even if absent), then archive and drop files by name; folders are read whatever the layout."""
    root = Path(project_root)
    # drops are LISTED before the archive (a fold adds its archive file first, deletes the drops after); a file
    # lost between listing and reading is redone by read_events_assembled; _all_records has no such retry (S6 note)
    listed = {f: sorted(p for p in (root / f).glob("*.jsonl") if p.is_file() and not p.is_symlink())
              if real_event_dir(root, f) else [] for f in (DROPS_DIR, ARCHIVE_DIR)}
    return [resolve_events_path(root), *listed[ARCHIVE_DIR], *listed[DROPS_DIR]]


def _all_records(project_root: Path | str) -> list[dict]:
    """Records of every event file (order is irrelevant to the two callers below)."""
    return [r for p in event_files(project_root) for r in read_jsonl_records(p).records]


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
    latest: datetime | None = None
    try:
        records = _all_records(project_root)
    except OSError:
        return None
    # PARTIAL recovery is the right policy for THIS caller: the value drives a
    # rendered "data as of" banner, so a stale-but-present timestamp beats a
    # blank one, and skipping corrupt input silently is already the documented
    # contract above. `finalized_run_ids` deliberately differs — see there.
    for event in records:
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
            try:
                dt = dt.astimezone(timezone.utc)
            except OverflowError:  # year-1 instant + offset: unparseable, like any bad ts
                continue
        if latest is None or dt > latest:
            latest = dt

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
    never crash-on-read). Existing-but-empty → empty set; blank lines skipped.

    Concatenated records are RECOVERED (iterate-2026-07-19-…-readers): a
    union-merge-joined line used to yield the EMPTY SET here — not ``None`` —
    which reads as the confident claim "this tree finalized no runs" and scopes
    the drift gate to nothing. A fail-open gate failing open by accident.

    An unrecoverable FRAGMENT is still skipped, and the run_ids that did decode
    are still returned. That asymmetry is deliberate and pre-dates this change:
    ``None`` is reserved for absent-or-unreadable, and "one bad row must not
    take down the audit" is the documented contract (pinned by
    ``test_arch_drift_event_scope.test_finalized_run_ids_skips_corrupt_lines``).
    Widening ``None`` to cover fragments was considered during external review
    and REJECTED here as a policy change riding along in a defect repair — it
    belongs in its own iterate, reasoned about on its own terms.
    """
    if not any(p.exists() for p in event_files(project_root)):
        return None
    try:
        records = _all_records(project_root)
    except OSError:
        return None  # any file unreadable → undeterminable, same as absent → fail open
    run_ids: set[str] = set()
    # `read_jsonl_records` yields only JSON objects, so the historical
    # `isinstance(event, dict)` guard is now structurally guaranteed.
    for event in records:
        for key in ("adr_id", "run_id"):
            val = event.get(key)
            if isinstance(val, str) and val:
                run_ids.add(val)
    return run_ids
