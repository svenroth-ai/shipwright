"""Session-start baseline for the design phase's write-boundary gate (FR-01.04 #11).

The project phase leaves its outputs uncommitted (specs, config, scaffolding).
Judged against the whole dirty working tree, the boundary gate flagged all of
that as "outside the design phase's allowed paths", so every brief run stopped
to ask "commit earlier output first?". The gate's contract is "THIS session's
own changes", so ``setup-design-session.py`` records what is already dirty
(path -> content fingerprint) and the gate only reports a path that is new, or
whose content differs from the recorded fingerprint.

Missing or unreadable baseline = no baseline: the gate stays strict. So does a
baseline recorded by another run (``SHIPWRIGHT_SESSION_ID``), and so does a
``--project-root`` that is not the repository root: git reports root-relative
paths, so a subdirectory would fingerprint every path as missing and compare
equal to itself (fail open).
Setup run again at the SAME commit and run (a resume) keeps the original
baseline, so the session cannot launder its own earlier writes into it. When
HEAD moves within the same run (earlier output was committed), the old entries
are carried forward unchanged under the old salt and nothing new is added, so
neither a baseline-dirty file edited before that commit nor a file created
after the first baseline is laundered. The baseline sits
inside the allowed ``.shipwright/`` prefix, so it is self-attested: an agent
that forges it can hide its own writes (accepted residual risk, same trust
level as the rest of the in-session gates). A baseline-dirty file edited and
then restored byte-for-byte reads as unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import subprocess
from pathlib import Path

BASELINE_REL = ".shipwright/design-boundary-baseline.json"
_DELETED = "<deleted>"


def dirty_paths(project_root: Path) -> list[str]:
    """Every changed path (tracked, staged, untracked), both sides of a rename,
    from NUL-delimited ``git status`` so names with spaces or non-ASCII
    characters arrive verbatim (not C-quoted). ``[]`` outside a git worktree."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "status", "--porcelain", "-z", "--untracked-files=all"],
            capture_output=True, check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    fields = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":  # the next field is the rename/copy source
            if i < len(fields) and fields[i]:
                paths.append(fields[i])
            i += 1
    return paths


def fingerprint(project_root: Path, rel_path: str, salt: str = "") -> str | None:
    """Salted sha256 of the working-tree bytes; ``<deleted>`` for a missing
    file; ``None`` when the path exists but cannot be read (a directory such
    as a submodule, a permission error) - never equal to anything, so it
    always counts as changed. The salt keeps the stored hashes useless as a
    content oracle for untracked files.

    Scope: working-tree content only. A change to the index or the file mode
    with identical bytes is not seen (accepted; design always changes bytes).
    """
    try:
        with (project_root / rel_path).open("rb") as fh:
            digest = hashlib.sha256(salt.encode("utf-8"))
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return _DELETED
    except OSError:
        return None


def _head(project_root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(project_root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _run_id() -> str | None:
    """The run this session belongs to; ``None`` when the host sets none."""
    return os.environ.get("SHIPWRIGHT_SESSION_ID") or None


def at_repo_root(project_root: Path) -> bool:
    """True only when ``project_root`` IS the git toplevel. Anything else
    (subdirectory, not a repo, git missing) is not trusted with a baseline."""
    try:
        proc = subprocess.run(["git", "-C", str(project_root), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return False
    top = proc.stdout.strip()
    if proc.returncode != 0 or not top:
        return False
    try:
        return Path(top).resolve() == project_root.resolve()
    except OSError:
        return False


def _read(project_root: Path) -> dict | None:
    try:
        data = json.loads((project_root / BASELINE_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("dirty"), dict) and isinstance(data.get("salt"), str):
        return data
    return None


def write_baseline(project_root: Path) -> bool:
    """Record the dirty set at session start. Returns True when written.

    An existing baseline of the SAME run at the SAME commit is kept: a resume or a
    second setup call must not let the session launder its own earlier
    writes into the baseline. A new commit in the same run (earlier output
    was committed) carries the old entries forward unchanged; another run or a
    missing/corrupt file starts a fresh baseline.
    """
    if not at_repo_root(project_root):
        return False
    head, run = _head(project_root), _run_id()
    existing = _read(project_root)
    same_run = existing is not None and existing.get("run") == run
    if same_run and existing.get("head") == head:
        return False
    if same_run:  # HEAD moved: keep every old entry, add nothing (new dirt is this session's)
        salt, snap = existing["salt"], dict(existing["dirty"])
    else:
        salt = secrets.token_hex(16)
        snap = {p: fingerprint(project_root, p, salt) for p in dirty_paths(project_root)}
    target = project_root / BASELINE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"head": head, "run": run, "salt": salt, "dirty": snap}, indent=2, sort_keys=True),
        encoding="utf-8")
    return True


def session_changes(project_root: Path) -> list[str]:
    """The paths this session changed: the dirty set plus every baseline path,
    minus those whose content still equals the baseline fingerprint.

    A baseline-dirty file the session restored to HEAD is no longer dirty but
    its content moved, so it is reported too. A corrupt, missing, other-run or
    non-root baseline is strict (the dirty set unchanged).
    """
    dirty = dirty_paths(project_root)
    data = _read(project_root)
    if data is None or data.get("run") != _run_id() or not at_repo_root(project_root):
        return dirty
    baseline, salt = data["dirty"], data["salt"]
    changed = []
    for p in dict.fromkeys([*dirty, *baseline]):
        now = fingerprint(project_root, p, salt)
        if now is None or baseline.get(p) != now:
            changed.append(p)
    return changed


def main() -> int:
    """``python boundary_baseline.py --project-root <dir>``: record the baseline
    (the design SKILL runs this before any other action)."""
    import argparse

    parser = argparse.ArgumentParser(description="Record the design boundary baseline")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.project_root).resolve()
        state = ("written" if write_baseline(root) else "kept") if at_repo_root(root) else "not_written"
    except OSError:
        state = "not_written"
    print(json.dumps({"boundary_baseline": state}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
