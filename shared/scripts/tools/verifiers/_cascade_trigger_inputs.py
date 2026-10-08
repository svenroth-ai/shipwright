"""What decides whether a small iterate's code review was due: risk flags and diff size.

Split from :mod:`cascade_trigger` along its natural seam. This module reads git
and the run's self-reports. The gate next door decides what the review record
must then say.

**Risk flags** are the union of three sources. Any one of them is enough:

* the session plan Stage 1 wrote (``.shipwright/agent_docs/iterates/<run_id>.plan.json``,
  ``classify_complexity --run-id``), which a standalone iterate leaves;
* Step 3.4's ``risk_recheck.json``, which a campaign sub-iterate leaves;
* the two detectors that shared/ already carries, recomputed from the branch diff
  (``cross_component`` and ``touches_ci_supplychain``). A flag the agent did not
  record still counts. The other flags are taken as self-reported.

**Diff size** follows ``lib/review_diff_threshold.py`` exactly: added+removed lines
of ``git diff --numstat --no-renames <merge-base>..<commit>``, without the
finalization records, ``> 100``.

An input that cannot be read is reported as an error string, never as "no flag"
or "0 lines". The gate reads such a run as triggered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_diff_threshold import is_counted_path, numstat_changed_lines  # noqa: E402
from lib.review_record_schema import is_safe_run_id  # noqa: E402

from .ci_supplychain import _is_ci_supplychain  # noqa: E402
from .git_helpers import _branch_base_commit, _run_git  # noqa: E402
from .integration_coverage import _is_cross_component  # noqa: E402
from .risk_recheck_recording import _read_recheck_record  # noqa: E402

__all__ = ["DiffMeasure", "measure_diff", "read_plan", "recorded_risk_flags"]

_GIT_TIMEOUT = 30.0

#: Local trunk names a remote-less (greenfield) repo may carry.
_LOCAL_TRUNKS = ("main", "master")

#: Remote trunk refs whose containment of a commit licenses the tip-only view.
_REMOTE_TRUNKS = ("refs/remotes/origin/main", "refs/remotes/origin/master")


def read_plan(project_root: Path, run_id: str) -> tuple[dict | None, str | None]:
    """The Stage-1 session plan as ``(data, error)``. Absence is ``(None, None)``.

    Hardened like :func:`risk_recheck_recording._read_recheck_record`: the plan's
    directory must resolve inside ``.shipwright/agent_docs/iterates``, a symlink or a
    non-regular file is malformed, never absence, and a plan must name this run in
    ``run_id``: one without a run id, or naming another run, cannot vouch for this one.
    """
    if not is_safe_run_id(run_id):
        return None, f"run id {str(run_id)[:60]!r} is not a single safe path component"
    iterates = Path(project_root) / ".shipwright" / "agent_docs" / "iterates"
    path = iterates / f"{run_id}.plan.json"
    try:
        # compare against the project root's real path, not iterates.resolve(): that would
        # follow a symlinked iterates/ and then agree with itself
        inside = path.parent.resolve() == Path(project_root).resolve() / ".shipwright/agent_docs/iterates"
    except OSError:
        inside = False
    if not inside:
        return None, f"{path.name} resolves outside {iterates}; refusing to read through a symlinked directory"
    if path.is_symlink():
        return None, f"{path.name} is a symlink, not a regular file"
    if not path.exists():
        return None, None
    if not path.is_file():
        return None, f"{path.name} exists but is not a regular file"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{path.name} is unreadable ({exc}); a corrupt plan cannot vouch for 'no risk flag'"
    if not isinstance(data, dict):
        return None, f"{path.name} is not a JSON object"
    if data.get("run_id") != run_id:
        if "run_id" not in data:
            return None, f"{path.name} carries no `run_id`, so it cannot vouch for this run"
        return None, f"{path.name} belongs to another run ({str(data['run_id'])[:60]!r})"
    return data, None


def _plan_flags(project_root: Path, run_id: str) -> tuple[list[str], str | None]:
    """``risk_flags`` from the Stage-1 session plan. Absence is ``([], None)``."""
    data, err = read_plan(project_root, run_id)
    if err or data is None:
        return [], err
    path_name = f"{run_id}.plan.json"
    flags = data.get("risk_flags")
    if not isinstance(flags, list):
        return [], f"{path_name} carries no `risk_flags` list"
    return [f for f in flags if isinstance(f, str) and f.strip()], None


def recorded_risk_flags(project_root: Path, run_id: str) -> tuple[list[str], str | None]:
    """The run's self-reported flags (session plan + Step 3.4 record), or why not."""
    if not is_safe_run_id(run_id):
        return [], f"run id {str(run_id)[:60]!r} is not a single safe path component"
    flags, err = _plan_flags(project_root, run_id)
    if err:
        return [], err
    block, err = _read_recheck_record(Path(project_root), run_id)
    if err:
        return [], err
    if block is not None:
        flags += [f for f in block.get("risk_flags") or [] if isinstance(f, str) and f.strip()]
    return sorted(set(flags)), None


class DiffMeasure:
    """The branch's changed paths and counted lines, or the reason they are unknown."""

    def __init__(self, paths: list[str] | None = None, lines: int | None = None,
                 error: str | None = None, base: str = "") -> None:
        self.paths = paths or []
        self.lines = lines
        self.error = error
        self.base = base

    def diff_flags(self) -> list[str]:
        """Detectors run over the counted paths: a finalization record is not code."""
        paths = [p for p in self.paths if is_counted_path(p)]
        flags = []
        if _is_cross_component(paths):
            flags.append("cross_component")
        if _is_ci_supplychain(paths):
            flags.append("touches_ci_supplychain")
        return flags


def _is_merge(project_root: Path, commit: str) -> bool | None:
    """``True`` for a merge commit, ``False`` for a single-parent one, ``None`` if git failed."""
    rc, out, _ = _run_git(project_root, "rev-list", "--parents", "-n", "1", commit, timeout=_GIT_TIMEOUT)
    if rc != 0 or not out.strip():
        return None
    return len(out.split()) > 2


def _greenfield_base(project_root: Path, commit: str) -> str | None:
    """No remote at all and exactly one local trunk name: trust that one merge-base.

    ``_branch_base_commit`` wants two agreeing names, because a lone REMOTE name may
    be a stale ``origin/master`` after a rename. A repo with no remote has nothing
    that can go stale that way, so its one local ``main`` (or ``master``) is the trunk.
    """
    rc, remotes, _ = _run_git(project_root, "remote", timeout=_GIT_TIMEOUT)
    if rc != 0 or remotes.strip():
        return None
    bases = []
    for name in _LOCAL_TRUNKS:
        rc, mb, _ = _run_git(project_root, "merge-base", name, commit, timeout=_GIT_TIMEOUT)
        if rc == 0 and mb.strip():
            bases.append(mb.strip())
    return bases[0] if len(bases) == 1 else None


def _in_remote_trunk(project_root: Path, commit: str) -> bool:
    """``commit`` is contained in a remote trunk ref (``origin/main`` or ``origin/master``).

    Ancestry is read from ``rev-list --count <ref>..<commit>`` (0 = contained), so a
    git failure stays "not shown contained" instead of passing for a "yes".
    """
    for ref in _REMOTE_TRUNKS:
        rc, out, _ = _run_git(project_root, "rev-list", "--count", f"{ref}..{commit}", timeout=_GIT_TIMEOUT)
        if rc == 0 and out.strip() == "0":
            return True
    return False


def measure_diff(project_root: Path, commit: str) -> DiffMeasure:
    """Count the branch against its merge-base with the trunk.

    No trustworthy trunk base is UNKNOWN, never "the last commit": a branch of
    several commits would otherwise be measured by its tip alone. A commit that
    already sits on the trunk (``base == commit``) has no branch range. Its own
    numstat is measured only when a REMOTE trunk ref contains it, the shape of a
    squash-merged PR. On a local-only trunk (unpushed commits on ``main``, a
    remote-less greenfield trunk) the tip may be the last of several commits, so
    the size is unknown. A merge commit's own numstat shows nothing: unknown too.
    """
    rc, head, _ = _run_git(project_root, "rev-parse", commit, timeout=_GIT_TIMEOUT)
    head = head.strip()
    if rc != 0 or not head:
        return DiffMeasure(error=f"cannot resolve {commit[:12]!r}")
    base = _branch_base_commit(project_root, head) or _greenfield_base(project_root, head)
    if not base:
        return DiffMeasure(error=f"no trustworthy trunk merge-base for {head[:8]} (needs two "
                                 "agreeing trunk names, e.g. main + origin/main, or a remote-less "
                                 "repo with one local main/master)")
    if base != head:
        args = ["diff", "--numstat", "--no-renames", f"{base}..{head}"]
    else:
        if not _in_remote_trunk(project_root, head):
            return DiffMeasure(error=f"{head[:8]} sits on a local trunk that no remote trunk ref "
                                     "contains, so its own diff may be the last of several commits")
        merge = _is_merge(project_root, head)
        if merge is None:
            return DiffMeasure(error=f"git could not list the parents of {head[:8]}, so whether "
                                     "it is a merge commit is unknown")
        if merge:
            return DiffMeasure(error=f"{head[:8]} is a merge commit already on the trunk; its size is unknown")
        args = ["show", "--numstat", "--no-renames", "--format=", head]
    rc, out, err = _run_git(project_root, "-c", "core.quotePath=false", *args, timeout=_GIT_TIMEOUT)
    if rc != 0:
        return DiffMeasure(error=f"`git {args[0]} --numstat` failed ({(err or '').strip()[:120]})")
    try:
        paths, lines = numstat_changed_lines(out)
    except ValueError as exc:
        return DiffMeasure(error=str(exc))
    return DiffMeasure(paths, lines, base=base[:8])
