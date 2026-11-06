"""F11 claim check: a change may only ADD files under the event folders (issue 978, S6, kill criterion 6).

Judges the branch against the trunk it left (``git_helpers._branch_base_commit``) with
``lib.events_integrity.check_integrity``: no modify/delete of a file that exists at the merge-base (fold and
quarantine commits excepted), no path traversal or hidden/overlong key, no symlink, no drop stamped with a
foreign ``run``. SKIPPED while neither the base nor the commit has an event folder (every legacy repo), when
the project is not a git work tree, or when no trunk view exists. Violations are an ERROR: they are in the
branch's own diff, so the author can fix them (a fold goes through ``tools/fold_events.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_fold_io import FOLDERS, GitError, git  # noqa: E402
from lib.events_integrity import check_integrity  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _branch_base_commit  # noqa: E402

CHECK_NAME = "event folders only grow (integrity)"


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def check_events_integrity(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root, head = Path(project_root), commit_hash or "HEAD"
    try:
        base = _branch_base_commit(root, head)
        if base is None:
            return _skip("no trunk view to judge against")
        touched = git(root, "diff", "--name-only", base, head, "--", *FOLDERS).stdout.strip()
        if not touched:
            return _skip("the change touches no event folder")
        violations = check_integrity(root, base, head)
    except (GitError, OSError) as exc:
        return _skip(f"git could not answer: {str(exc)[:120]}")
    if not violations:
        return CheckResult(CHECK_NAME, True, f"{len(touched.splitlines())} event-folder path(s), all additions or a recognised fold")
    shown = "; ".join(f"{v.code}: {v.path} ({v.detail})" for v in violations[:5])
    return CheckResult(CHECK_NAME, False, f"{len(violations)} violation(s): {shown}"
                       + (" ..." if len(violations) > 5 else ""))
