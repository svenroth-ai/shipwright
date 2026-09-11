"""Generic "this phase writes no production code" boundary check.

Two ledger criteria share the exact same shape and nothing else distinguishes
them:

* FR-01.03 #7 — "Planning writes no production code, runs no tests."
* FR-01.04 #11 — "What design produces are review mockups, not production
  code."

Both are a boundary criterion over the SAME kind of evidence (which paths a
phase session touched), differing only in which prefixes each phase is
allowed to write. One implementation, two thin per-phase allowlists, so the
rule cannot drift between the two callers.

The evidence is the working tree's own uncommitted change set
(``git status --porcelain``) — a plan/design session's artifacts are still
uncommitted at the point either phase's own completion gate runs (the
iterate/build commit happens later in the pipeline), so this is the only
honest place to read "what did this session write" from.

**Known scope, not a bug (external plan review, iterate-2026-09-11-e1-checks-plan-design):**
this reads the WHOLE worktree's uncommitted state, with no session-start
baseline snapshot — it cannot distinguish "this phase session wrote it" from
"it was already dirty before this session began". That is an accepted
limitation, not an oversight: every real call site is a plan/design session
running in its own freshly-branched worktree (`references/campaign-worktree.md`)
that started clean and has not committed yet, so in practice the two are the
same set. A worktree that is dirty for an unrelated reason when this runs
will have that dirt reported too — see
``test_an_unrelated_pre_existing_dirty_path_is_also_reported`` in the test
suite, which pins this as the accepted current behaviour rather than leaving
it an undocumented gap. A baseline-snapshot mechanism (git stash, or a
captured path manifest at session start, mirroring
``record_requirement_impact.py --snapshot-baseline``) would close it, but is
out of scope for this bounded enforcement pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = [
    "find_boundary_violations",
    "git_dirty_paths",
]


def git_dirty_paths(project_root: Path | str) -> list[str]:
    """Every path ``git status --porcelain`` reports as changed (tracked
    modifications, staged changes, and untracked files alike), relative to
    ``project_root``, POSIX-separated for platform-invariant prefix matching.

    Returns ``[]`` (rather than raising) when ``project_root`` is not a git
    worktree at all — a boundary check with no git evidence has nothing to
    report, which is a fact the caller should be told rather than a crash.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=False,
        )
    except (OSError, FileNotFoundError):
        return []
    if proc.returncode != 0:
        return []

    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        # Porcelain v1: "XY <path>" or "XY <path> -> <newpath>" for a rename.
        # The path starts at column 3. BOTH sides of a rename are reported
        # (external code review, iterate-2026-09-11-e1-checks-plan-design):
        # keeping only the new path let a production file renamed INTO an
        # allowed prefix (e.g. `src/app.py` -> `.shipwright/notes.md`) hide
        # the fact that a production path just disappeared — the exact
        # boundary violation this check exists to catch.
        raw = line[3:]
        for side in raw.split(" -> ", 1):
            paths.append(side.strip().strip('"').replace("\\", "/"))
    return paths


def find_boundary_violations(
    changed_paths: list[str], allowed_prefixes: list[str]
) -> list[str]:
    """Return the ``changed_paths`` that start with none of ``allowed_prefixes``.

    Prefix matching is on POSIX-separated strings; both sides are normalised
    the same way so a caller passing OS-native separators still matches.
    An empty ``changed_paths`` list — nothing changed yet, or evidence
    unavailable — yields no violations: the check has nothing to fail on.
    """
    normalized_allowed = [p.replace("\\", "/") for p in allowed_prefixes]
    violations = []
    for path in changed_paths:
        normalized = path.replace("\\", "/")
        if not any(normalized.startswith(prefix) for prefix in normalized_allowed):
            violations.append(path)
    return violations
