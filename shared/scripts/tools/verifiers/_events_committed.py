"""F11 committed-check for the DROPS layout (issue 978, campaign unit S4).

``iterate_checks._event_committed_in_head`` only knows the one legacy file. For the drops layout the
run's ``work_completed`` event lives in a file of ``shipwright_events.d/``; "committed" then means
a file of that folder IN HEAD'S TREE carries it. A drop that exists only in the working copy
(F6 forgot to stage it, and ``ensure_current``'s ABSORB step did not take it either) FAILS the
check -- never ``None``, never a pass. A repo that ignores the folder is judged like a repo that
ignores the legacy log: the assertion does not apply (``None``).

Legacy behaviour is unchanged: a tree whose working copy has the event only in the legacy file is
decided by the legacy tri-state the caller passes in.
"""

from __future__ import annotations

from pathlib import Path

from lib.events_log import ARCHIVE_DIR, DROPS_DIR
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
        if d.is_dir() and not d.is_symlink():
            out += sorted(p for p in d.glob("*.jsonl") if p.is_file() and not p.is_symlink())
    return out


def drops_committed_state(project_root: Path, commit_hash: str, run_id: str,
                          legacy_state: bool | None) -> bool | None:
    """Fold the drops layout into the legacy tri-state (see module docstring)."""
    working = [p for p in _folder_files(project_root)
               if _carries(read_jsonl_records(p).records, commit_hash, run_id)]
    if not working:
        return legacy_state  # the event is not in a drop: the legacy decision stands
    if legacy_state is True:
        return True
    rc, _, _ = _run_git(project_root, "check-ignore", "-q", f"{DROPS_DIR}/x.jsonl")
    if rc == 0:
        return None  # folder ignored: not tracked, the committed-assertion does not apply
    for path in working:
        rel = path.relative_to(project_root).as_posix()
        rc, blob, _ = _run_git(project_root, "show", f"HEAD:{rel}")
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
