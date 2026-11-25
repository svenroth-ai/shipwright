"""``release.py cancel``: Cancel at the Step 5 preview, in code (P8a fix round, finding D84).

Since F2 the preview writes nothing, so a Cancel straight after it has nothing to undo. An Edit does change a drop file
under ``CHANGELOG-unreleased.d/``; a Cancel after it must put that file back as it was at the last ``prepare``, and the
prose cannot do that reliably (it would have to remember the old text). Every ``prepare`` keeps the bytes of every drop
file in the run state (``drops_before``, taken anew on a re-run); ``cancel`` writes back each one that changed or went missing, byte for byte. A drop
file that did not exist at ``prepare`` is never deleted (it may be someone's work): it is listed in ``left``. The real
``aggregate`` consumes the drops, so once it has run (the version's section is in ``CHANGELOG.md``, or the tag exists) a
cancel is refused: putting consumed drops back would release them twice. The run record itself stays, as it does after
any release that stops: the release guard keeps an outward release push blocked until it is 48 hours old or
``SHIPWRIGHT_RELEASE_GUARD=off`` is set.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path, PurePosixPath
from typing import Any

from . import release_runstate, release_upgrade_notes
from .release_runner import Recorder

DROPS = "CHANGELOG-unreleased.d"
GUARD_NOTICE = ("The release's run record stays: the release guard blocks a push of the trunk or a tag for this release until "
                "the record is 48 hours old or SHIPWRIGHT_RELEASE_GUARD=off is set.")


def snapshot(project_root: Path) -> dict[str, str]:
    """Every drop file now, ``{relative posix path: base64 of its bytes}`` (exact bytes: line endings included)."""
    base, out = Path(project_root) / DROPS, {}
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        if path.is_file() and not path.is_symlink():
            try:
                out[path.relative_to(project_root).as_posix()] = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError:
                continue
    return out


def _safe(rel: Any) -> bool:
    """A path the state names may only point into the drops directory: posix form only (a backslash or a drive colon is a
    second path syntax on Windows, so neither is accepted), relative, no ``..``."""
    if not isinstance(rel, str) or "\\" in rel or ":" in rel:
        return False
    parts = PurePosixPath(rel).parts
    return len(parts) > 1 and parts[0] == DROPS and ".." not in parts and not PurePosixPath(rel).is_absolute()


def _writable(root: Path, rel: str) -> bool:
    """Checked before every write: no symlink at the target or on the way to it from the drops directory (that directory
    included), and the resolved target still lies inside the resolved drops directory."""
    drops, path = root / DROPS, root / rel
    if any(p.is_symlink() for p in (path, *path.parents) if p == drops or drops in p.parents):
        return False
    try:
        return path.resolve().is_relative_to(drops.resolve())
    except (OSError, RuntimeError):
        return False


def cancel(rec: Recorder, plugin_root: Path, *, version: str) -> tuple[int, dict[str, Any]]:
    root = rec.cwd
    out: dict[str, Any] = {"version": version, "restored": [], "left": []}
    state = release_runstate.stored(root, version)
    if state is None:
        return 1, {**out, "status": "failed", "reason": "no_release_in_progress", "commands": rec.as_json()}
    tag = rec.run("tag-check", ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"])
    if tag.exit == 0 or release_upgrade_notes.released(root, version):  # the real aggregate ran: its drops are consumed
        return 1, {**out, "status": "failed", "reason": "release_written", "commands": rec.as_json()}
    before = state.get("drops_before")
    if not isinstance(before, dict) or not all(_safe(rel) and isinstance(data, str) for rel, data in before.items()):
        return 1, {**out, "status": "failed", "reason": "no_drop_snapshot", "commands": rec.as_json()}
    now = snapshot(root)
    for rel, data in sorted(before.items()):
        if now.get(rel) == data:
            continue
        if not _writable(root, rel):
            return 1, {**out, "status": "failed", "reason": "unsafe_drop_path", "detail": rel, "commands": rec.as_json()}
        try:
            content = base64.b64decode(data, validate=True)
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except (OSError, binascii.Error) as exc:
            return 1, {**out, "status": "failed", "reason": "restore_failed", "detail": f"{rel}: {type(exc).__name__}",
                       "commands": rec.as_json()}
        out["restored"].append(rel)
    out["left"] = sorted(set(now) - set(before))
    release_runstate.save(root, {k: v for k, v in state.items() if k != "drops_before"})  # the next release snapshots anew
    return 0, {**out, "status": "ok", "notices": [GUARD_NOTICE], "commands": rec.as_json()}
