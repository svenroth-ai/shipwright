"""F11 committed-check for the DROPS layout (issue 978, campaign unit S4).

``iterate_checks._event_committed_in_head`` only knows the one legacy file. For the drops layout the
run's ``work_completed`` event lives in a file of ``.shipwright/events/drops/``; "committed" then means
a file of that folder IN HEAD'S TREE carries it. A drop that exists only in the working copy
(F6 forgot to stage it, and ``ensure_current``'s ABSORB step did not take it either) FAILS the
check -- never ``None``, never a pass. A drop in an IGNORED folder fails the same way: F6's staging skips
ignored files, so the event would never ship. (The folder sits under ``.shipwright/``, which a managed
``.gitignore`` ignores by default except for ``!/.shipwright/events/``, so an ignored folder is a missing
re-include, not a deliberate choice.)

Legacy behaviour is unchanged: a tree whose working copy has the event only in the legacy file is
decided by the legacy tri-state the caller passes in.
"""

from __future__ import annotations

from pathlib import Path

from lib.events_log import ARCHIVE_DIR, DROPS_DIR, real_event_dir
from lib.jsonl_records import read_jsonl_records

from .git_helpers import _run_git


def _carries(records: list[dict], commit_hash: str, run_id: str) -> bool:
    for evt in records:
        if evt.get("type") != "work_completed":
            continue
        if run_id and evt.get("adr_id") == run_id:
            return True
        if commit_hash and str(evt.get("commit", "") or "") == commit_hash:
            return True
    return False


def _folder_files(project_root: Path) -> list[Path]:
    out: list[Path] = []
    for folder in (DROPS_DIR, ARCHIVE_DIR):
        d = project_root / folder
        if real_event_dir(project_root, folder):
            out += sorted(p for p in d.glob("*.jsonl") if p.is_file() and not p.is_symlink())
    return out


def drops_folder_ignored(project_root: Path) -> bool:
    """True when git ignores the drops folder (a drop written there can never be staged)."""
    rc, _, _ = _run_git(project_root, "check-ignore", "-q", f"{DROPS_DIR}/x.jsonl")
    return rc == 0


def event_stuck_in_ignored_drop(project_root: Path, commit_hash: str, run_id: str) -> bool:
    """True when this run's event sits in a drop file AND git ignores the drops folder (the hint's precondition)."""
    return drops_folder_ignored(project_root) and any(
        _carries(read_jsonl_records(p).records, commit_hash, run_id) for p in _folder_files(project_root))


def drops_committed_state(project_root: Path, commit_hash: str, run_id: str,
                          legacy_state: bool | None) -> bool | None:
    """Fold the drops layout into the legacy tri-state (see module docstring)."""
    working = [p for p in _folder_files(project_root)
               if _carries(read_jsonl_records(p).records, commit_hash, run_id)]
    if not working:
        return legacy_state  # the event is not in a drop: the legacy decision stands
    if legacy_state is True:
        return True
    # An ignored folder needs no special case here: a drop already committed in HEAD passes in the loop below, and an
    # uncommitted one (which an ignored folder can never stage) falls through to the final ``return False``.
    for path in working:
        rel = path.relative_to(project_root).as_posix()
        # ``./`` makes the path relative to project_root (a repo SUBDIRECTORY); cat-file, not show (Windows long paths)
        rc, blob, _ = _run_git(project_root, "cat-file", "blob", f"HEAD:./{rel}")
        if rc == 0 and _carries(_parse(blob), commit_hash, run_id):
            return True
    return False  # an unstaged / uncommitted drop FAILS the check


def _parse(blob: str) -> list[dict]:
    from lib.jsonl_records import split_records
    out: list[dict] = []
    for line in blob.splitlines():
        if line.strip():
            out += split_records(line.strip())[0]
    return out
