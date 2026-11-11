"""F11 claim check: a change may only ADD files under the event folders (issue 978, S6, kill criterion 6).

Judges the branch against the trunk it left (``git_helpers._branch_base_commit``) with
``lib.events_integrity.check_integrity``: no modify/delete of a file that exists at the merge-base (fold and
quarantine commits excepted), no path traversal or hidden/overlong key, no symlink, no drop stamped with a
foreign ``run``. Passes trivially while the change touches no event folder (every legacy repo); SKIPPED when the project is not a git work tree, or when no trunk view exists. Violations are an ERROR: they are in the
branch's own diff, so the author can fix them (a fold goes through ``tools/fold_events.py``).

Ownership: a drop under a key other than this run's (``sanitize_key(run_id)``) or the key the writer falls back to
without a run id (``events_layout.implicit_key``: unit worktree / ``_branch-<slug>`` / ``_main``) is a ``foreign_key``.
Two honest shapes are NOT foreign: a drop whose file name carries THIS worktree's id (``<key>--<wt8>--<nonce>``: ``ensure_current``'s
absorb, a re-attempt under a new run id, a phase skill's own run id, a rebase's ``_detached-`` key -- the stamp-vs-key forgery rule still
applies to it), and every drop while a non-finished ``stacked`` / ``single-branch`` campaign is on record (the range then holds the earlier
units' drops; the loop state lives in the campaign worktree, not necessarily at the main root). The check says so when it skipped ownership.
A git failure in a work tree is a FAILURE, not a skip: a check that cannot answer must not pass the claim.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_fold_io import GitError  # noqa: E402
from lib.events_integrity import check_integrity  # noqa: E402
from lib.events_layout import implicit_key, worktree_id  # noqa: E402
from lib.events_log import resolve_main_repo_root  # noqa: E402
from lib.events_read import DROP_NAME, sanitize_key  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _branch_base_commit  # noqa: E402

CHECK_NAME = "event folders only grow (integrity)"


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def _inherits_earlier_units(root: Path) -> bool:
    """True while a stacked / single-branch campaign is on record: the branch then carries earlier units' drops (other keys).

    The loop state is looked for here, at the main root and in every campaign worktree under it (``.worktrees/campaign-*``), where the
    campaign really keeps it. A finished loop does not count; a state without the key means ``single-branch`` (the loop code's default).
    """
    main = resolve_main_repo_root(root) or root
    candidates = [root / ".shipwright" / "loop_state.json", main / ".shipwright" / "loop_state.json",
                  *sorted((main / ".worktrees").glob("campaign-*/.shipwright/loop_state.json"))]
    for path in candidates:
        try:
            state = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(state, dict) and state.get("status") not in ("complete", "done") \
                and state.get("branch_strategy", "single-branch") in ("stacked", "single-branch"):
            return True
    return False


def _own_worktree_drop(path: str, wt8: str) -> bool:
    """``shipwright_events.d/<key>--<wt8>--<nonce>.jsonl`` written from THIS worktree (the key may itself contain ``--``)."""
    match = DROP_NAME.match(path.rsplit("/", 1)[-1])
    return bool(match) and match.group("wt8") == wt8


def check_events_integrity(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root, head = Path(project_root), commit_hash or "HEAD"
    try:
        base = _branch_base_commit(root, head)
        if base is None:
            return _skip("no trunk view to judge against")
        enforce = not _inherits_earlier_units(root)
        own = tuple(dict.fromkeys(k for k in (sanitize_key(run_id) if run_id else "", implicit_key(root)) if k)) if enforce else ()
        violations = check_integrity(root, base, head, own_keys=own)  # no pathspec prefilter: a case variant must reach the library
        if enforce and any(v.code == "foreign_key" for v in violations):
            wt8 = worktree_id(root)
            violations = [v for v in violations if v.code != "foreign_key" or not _own_worktree_drop(v.path, wt8)]
    except (GitError, OSError, subprocess.SubprocessError) as exc:
        return CheckResult(CHECK_NAME, False, f"git could not answer ({str(exc)[:120]}); the event folders were NOT checked")
    if not violations:
        return CheckResult(CHECK_NAME, True, "event folders only grew (or the change touches none)"
                           + ("" if enforce else "; drop ownership NOT enforced (stacked / single-branch campaign on record)"))
    shown = "; ".join(f"{v.code}: {v.path} ({v.detail})" for v in violations[:5])
    return CheckResult(CHECK_NAME, False, f"{len(violations)} violation(s): {shown}"
                       + (" ..." if len(violations) > 5 else ""))
