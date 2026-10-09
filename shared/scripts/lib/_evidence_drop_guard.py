"""``evidence_drop.stage`` refuses reports that are older than the code they claim to test.

The F11 surface check compares the tree fingerprinted at staging with the
verified commit, so it cannot see code that changed between running the tests
and staging them: re-staging the reports of an earlier run after a fix would
fingerprint the fixed tree and read fresh. This guard binds the reports to the
run that wrote them: when any path the branch changed (committed since its
merge-base with the trunk, uncommitted, or untracked) was modified after the
OLDEST report being staged was written, staging is refused.

Not counted: finalization records (``review_diff_threshold.is_counted_path``),
prose (``.md`` / ``.rst`` / ``.txt``), anything under a ``.shipwright/``
directory (a test run's leaks), and deleted paths (no mtime). A resumed F0
run is not affected: its reused reports are copied into the run that reuses
them, so their mtimes are that run's.

Fail-open on purpose when git cannot name the branch's paths (no repo, no
trunk): F11 stays the gate. Standard library only.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from review_diff_threshold import is_counted_path
except ImportError:  # loaded as a package (lib.evidence_drop).
    from .review_diff_threshold import is_counted_path  # type: ignore

__all__ = ["ReportsOlderThanCodeError", "check_reports_newer_than_code"]

_TRUNKS = ("origin/main", "origin/master", "main", "master")
_PROSE = (".md", ".rst", ".txt")
_TIMEOUT = 60.0


class ReportsOlderThanCodeError(ValueError):
    """The reports being staged predate a change to the code they would vouch for."""


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=_TIMEOUT, check=False)
    except Exception:  # noqa: BLE001 - like worktree_tree: git that cannot answer is fail-open here, F11 gates
        return None
    return proc.stdout if proc.returncode == 0 else None


_SCRATCH_DIR = ".scratch"  # check_ac_ratchet_f0's scratch parent; gitignored by every Shipwright repo


def _is_ignored_scratch_tree(root: Path) -> bool:
    """True when ``root`` is a copy under the OUTER repo's gitignored ``.scratch/`` directory.

    A scratch copy (``check_ac_ratchet_f0`` builds one under ``<project>/.scratch``) holds
    no branch of its own: git run there resolves the OUTER repo, whose changed paths are
    then joined onto the freshly copied files - which always look newer than the reports.
    Narrow on purpose: a checkout with its own ``.git`` (an iterate worktree, a nested
    clone) is its own toplevel and stays guarded, wherever it sits.
    """
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return False
    top_path, root_path = Path(top.strip()).resolve(), Path(root).resolve()
    if top_path == root_path or (top_path / _SCRATCH_DIR) not in root_path.parents:
        return False
    try:
        proc = subprocess.run(["git", "-C", str(top_path), "check-ignore", "-q", "--", str(root_path)],
                              capture_output=True, timeout=_TIMEOUT, check=False)
    except Exception:  # noqa: BLE001 - git that cannot answer keeps the guard on
        return False
    return proc.returncode == 0


def _branch_paths(root: Path) -> list[str] | None:
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return None
    if _is_ignored_scratch_tree(root):
        return None
    base = next((mb.strip() for ref in _TRUNKS if (mb := _git(root, "merge-base", "HEAD", ref))), None)
    if not base:
        return None
    tracked = _git(root, "diff", "--name-only", "--no-renames", base)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if tracked is None or untracked is None:
        return None
    return sorted({p.strip() for p in (tracked + "\n" + untracked).splitlines() if p.strip()})


def _counted(path: str) -> bool:
    lower = path.lower()
    return (is_counted_path(path) and not lower.endswith(_PROSE)
            and ".shipwright" not in lower.split("/"))


def check_reports_newer_than_code(project_root: Path, sources: list[Path]) -> None:
    """Raise :class:`ReportsOlderThanCodeError` when a branch path changed after the oldest report."""
    mtimes = [(src.stat().st_mtime, src) for src in sources if src.is_file()]
    paths = _branch_paths(Path(project_root)) if mtimes else None
    if not paths:
        return
    oldest, report = min(mtimes)
    newer = []
    for rel in filter(_counted, paths):
        try:
            if (Path(project_root) / rel).stat().st_mtime > oldest:
                newer.append(rel)
        except OSError:
            continue  # deleted in the working tree: no mtime to compare
    if newer:
        when = datetime.fromtimestamp(oldest, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raise ReportsOlderThanCodeError(
            f"refusing to stage: {newer[0]!r}" + (f" and {len(newer) - 1} more path(s)" if len(newer) > 1 else "")
            + f" changed after the oldest report ({report.name}, written {when}), so these reports "
            "describe older code. Re-run the tests (F0, and F0.5 for the surface), then stage the "
            "reports that run wrote. Nothing was staged.")
