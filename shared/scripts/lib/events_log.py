"""Worktree-aware resolution of the ``shipwright_events.jsonl`` event log.

Single source of truth for *locating* the unified event log. The log is a
**repo-scoped** append-only journal. Under ``/shipwright-iterate`` worktree
isolation (see shipwright-iterate SKILL.md "Worktree Isolation") a run
executes inside an ephemeral linked worktree, but the canonical event log
lives next to the **main** repo. A literal ``project_root / EVENT_FILE``
from inside a worktree therefore reads/writes a throwaway copy that is
discarded on ``git worktree remove`` — F7 ``work_completed`` events never
reach the main log.

``resolve_events_path`` resolves the log via ``git rev-parse
--git-common-dir``: git consistently reports the *main* repo's ``.git``
directory even from inside a linked worktree, and its parent is the
canonical project root that owns the event log.

That git-common-dir resolution is exposed on its own as
``resolve_main_repo_root`` — the generic worktree-aware primitive shared
with the decision-drop directory resolver in
``tools/write_decision_drop.py`` and ``tools/aggregate_decisions.py``. The
decision-drop staging dir is repo-scoped for the same reason the event log
is, and an iterate worktree's copy is discarded by ``git worktree remove``
before ``/shipwright-changelog`` can aggregate it.

Relationship to ``shipwright-compliance``'s
``data_collector._resolve_events_path``
----------------------------------------------------------------------
This helper is the **shared-side SSoT**, modelled on that compliance-plugin
function (which stays separate — the compliance plugin is a distinct
distributable and cannot import ``shared/scripts/lib`` without a
cross-plugin path bootstrap). A parity test pins the two to the same
answer. This helper deliberately hardens two things the compliance copy
does not:

- It does **not** pass ``--path-format=absolute`` (a Git 2.31+ flag, Mar
  2021). Older git silently fails that flag, which would trigger the
  fallback and leave the worktree bug unfixed. Plain ``--git-common-dir``
  is resolved to an absolute path against ``project_root`` in Python —
  same answer, no git-version floor.
- When git is genuinely **broken** (binary absent, timeout) or returns an
  **unexpected layout**, it emits a ``warnings.warn`` diagnostic before
  falling back, so a worktree run whose git unexpectedly failed is visible
  rather than silently writing the throwaway worktree copy.

In a plain single-repo checkout (no linked worktree) the resolved path is
identical to ``project_root / EVENT_FILE`` — behavior is unchanged.
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
        return common_path.parent

    warnings.warn(
        f"resolve_main_repo_root: unexpected git-common-dir "
        f"{str(common_path)!r} (not a `.git` directory) for {project_root} "
        f"— the caller falls back to {project_root} itself.",
        stacklevel=2,
    )
    return None


def resolve_events_path(project_root: Path | str) -> Path:
    """Return the path to ``shipwright_events.jsonl``, git-worktree-aware.

    From inside a linked git worktree this resolves to the **main** repo's
    event log; in a plain checkout — or when git is unavailable — it is
    identical to ``project_root / EVENT_FILE`` (behavior unchanged).

    Thin derivation of :func:`resolve_main_repo_root` — see that function
    for the git-resolution and ``warnings.warn`` diagnostic semantics.
    """
    project_root = Path(project_root)
    main_root = resolve_main_repo_root(project_root)
    return (main_root or project_root) / EVENT_FILE


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
