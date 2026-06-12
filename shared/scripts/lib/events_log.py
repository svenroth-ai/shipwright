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

``resolve_main_repo_root`` stays
--------------------------------
The git-common-dir primitive ``resolve_main_repo_root`` is **retained,
unchanged** — but it is no longer used to locate the event log. Its remaining
consumers are the **decision-drop** directory resolver
(``tools/write_decision_drop.py``, ``tools/aggregate_decisions.py``) and the
F11 verifier's decision-drop lookup. Decision-drops are *gitignored* staging
that ``/shipwright-changelog`` consumes on ``main``, so they genuinely must
resolve to the main repo (an iterate worktree's copy IS discarded before
aggregation). The event log no longer shares that constraint because it is
committed into the branch.

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
import os
import subprocess
import warnings
from datetime import datetime, timezone
from pathlib import Path

EVENT_FILE = "shipwright_events.jsonl"

# git path-resolution is a single fast call; cap it so a hung git cannot
# wedge an append.
_GIT_TIMEOUT_SECONDS = 15.0

# Environment variables that override git's repo discovery. If any of these
# leak in from the caller's environment, `git rev-parse` would resolve a
# DIFFERENT repo than ``cwd=project_root`` — silently writing the event log
# into the wrong repo. Strip them so resolution is pinned to project_root.
_GIT_DISCOVERY_OVERRIDES = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")


def _git_env() -> dict[str, str]:
    """Process environment with git repo-discovery overrides removed."""
    env = dict(os.environ)
    for var in _GIT_DISCOVERY_OVERRIDES:
        env.pop(var, None)
    return env


def resolve_main_repo_root(project_root: Path | str) -> Path | None:
    """Return the MAIN repo's working-tree root, git-worktree-aware.

    From inside a linked git worktree this resolves to the **main** repo
    root (the worktree's ``--git-common-dir`` parent); in a plain checkout
    it is the repo's own top level. Returns ``None`` when ``project_root``
    is not a git repository, or when git is unavailable / returns an
    unexpected layout — callers then fall back to ``project_root`` itself.

    A ``warnings.warn`` diagnostic is emitted only when git is *broken*
    (binary missing, timeout, empty / unexpected output). A plain "not a
    git repository" answer returns ``None`` *silently*: that is a
    definitive, no-data-loss result — a non-git project's artifacts
    genuinely live next to ``project_root``.

    Shared primitive behind :func:`resolve_events_path` and the
    worktree-aware decision-drop directory resolver in
    ``tools/write_decision_drop.py`` / ``tools/aggregate_decisions.py``.
    """
    project_root = Path(project_root)

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            # WP7/F27: git emits the common-dir path as UTF-8 bytes. Without
            # an explicit encoding the platform default (cp1252 on Windows)
            # mojibakes a non-ASCII project path, so the resolved main root
            # points at a directory that does not exist — and worktree
            # decision-drops are silently written there and lost. Pin UTF-8;
            # the exists() guard below fail-softs if anything still slips.
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # git binary missing / un-spawnable / hung — we cannot tell whether
        # this is a worktree, so a fallback here MAY be silent data loss.
        warnings.warn(
            f"resolve_main_repo_root: git unavailable for {project_root} "
            f"({exc!r}) — the caller falls back to {project_root} itself. "
            "An iterate worktree run may write a throwaway, soon-discarded "
            "artifact.",
            stacklevel=2,
        )
        return None

    if proc.returncode != 0:
        # Definitive "not a git repository" — the fallback is correct, not
        # a failure. Silent by design (non-git projects + test tmp dirs).
        return None

    common_dir = proc.stdout.strip()
    if not common_dir:
        warnings.warn(
            f"resolve_main_repo_root: `git rev-parse --git-common-dir` "
            f"returned empty output in {project_root} — the caller falls "
            f"back to {project_root} itself.",
            stacklevel=2,
        )
        return None

    common_path = Path(common_dir)
    if not common_path.is_absolute():
        # Without --path-format=absolute, `--git-common-dir` yields a path
        # relative to the git command's cwd, which we pinned to project_root.
        common_path = (project_root / common_path).resolve()

    # `--git-common-dir` returns the MAIN repo's .git directory; its parent
    # is the canonical project root. A linked worktree's *git-dir* is
    # `.git/worktrees/<name>`, but its *common* dir is the top-level `.git`
    # — so this is worktree-correct. Defensive: only trust a path that
    # actually ends in ".git".
    if common_path.name == ".git":
        resolved_root = common_path.parent
        # WP7/F27: a mojibaked (or otherwise corrupt) path can name a
        # directory that does not exist on disk. Returning it would send
        # worktree decision-drops into a phantom dir where they are lost.
        # Fail-soft to None so the caller falls back to project_root, which
        # is guaranteed real.
        if not resolved_root.exists():
            warnings.warn(
                f"resolve_main_repo_root: resolved main root "
                f"{str(resolved_root)!r} does not exist (corrupt/mojibaked "
                f"git output?) for {project_root} — the caller falls back to "
                f"{project_root} itself.",
                stacklevel=2,
            )
            return None
        return resolved_root

    warnings.warn(
        f"resolve_main_repo_root: unexpected git-common-dir "
        f"{str(common_path)!r} (not a `.git` directory) for {project_root} "
        f"— the caller falls back to {project_root} itself.",
        stacklevel=2,
    )
    return None


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
