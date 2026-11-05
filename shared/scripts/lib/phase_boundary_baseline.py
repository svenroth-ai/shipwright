"""Session-start baseline for a phase's write-boundary gate (design FR-01.04 #11, plan FR-01.03 #7).

Earlier phases leave their outputs uncommitted (specs, config, scaffolding, screens).
Judged against the whole dirty working tree, a phase's boundary gate flagged all of
that as "outside the phase's allowed paths", so a run stopped to ask "commit earlier
output first?" (design: e2e run of 2026-10-28; plan: e2e run 22, 63 files from the
Project and Design phases). The gate's contract is "THIS session's own changes", so
the phase's setup records what is already dirty (path -> content fingerprint) in
its own baseline file and the gate only reports a path that is new, or whose content
differs from the recorded fingerprint. Each phase passes its own ``baseline_rel``
(``.shipwright/<phase>-boundary-baseline.json``), so two phases never share a file.

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

Stdlib only, no imports of other lib modules: it is loaded top-level (plan gate),
through ``shared_lib_loader`` (design wrapper) and as ``lib.phase_boundary_baseline``
(tests), and must behave the same in all three.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path

DELETED = "<deleted>"
#: One file per phase, so a design baseline never stands in for a plan one (or back).
DESIGN_BASELINE_REL = ".shipwright/design-boundary-baseline.json"
PLAN_BASELINE_REL = ".shipwright/plan-boundary-baseline.json"


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
    with identical bytes is not seen (accepted; the phases always change bytes).
    """
    try:
        with (project_root / rel_path).open("rb") as fh:
            digest = hashlib.sha256(salt.encode("utf-8"))
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return DELETED
    except OSError:
        return None


def head(project_root: Path) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(project_root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def run_id() -> str | None:
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


def baseline_path(baseline_rel: str, scope: str | None = None) -> str:
    """One file per scope (plan: per split), so re-entering split 01 never meets split 02's snapshot."""
    if not scope:
        return baseline_rel
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in scope)
    stem = baseline_rel[:-len(".json")] if baseline_rel.endswith(".json") else baseline_rel
    return f"{stem}-{safe}.json"


def read_baseline(project_root: Path, baseline_rel: str, scope: str | None = None) -> dict | None:
    try:
        data = json.loads((project_root / baseline_path(baseline_rel, scope)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("dirty"), dict) and isinstance(data.get("salt"), str):
        return data
    return None


def write_baseline(project_root: Path, baseline_rel: str, scope: str | None = None) -> bool:
    """Record the dirty set at session start. Returns True when written.

    ``scope`` names the unit a session works on inside one run (plan: the split). The
    plan phase runs once per split in the same run (plan/01, build/01, plan/02 share one
    ``SHIPWRIGHT_SESSION_ID``), so a baseline of another scope is never carried forward:
    plan/02 takes a fresh snapshot that includes what build/01 left behind.

    An existing baseline of the SAME run at the SAME commit is kept: a resume or a
    second setup call must not let the session launder its own earlier
    writes into the baseline. A new commit in the same run (earlier output
    was committed) carries the old entries forward unchanged; another run or a
    missing/corrupt file starts a fresh baseline.
    """
    if not at_repo_root(project_root):
        return False
    now_head, run = head(project_root), run_id()
    existing = read_baseline(project_root, baseline_rel, scope)
    same_run = existing is not None and existing.get("run") == run and existing.get("scope") == scope
    if same_run and existing.get("head") == now_head:
        return False
    if same_run:  # HEAD moved: keep every old entry, add nothing (new dirt is this session's)
        salt, snap = existing["salt"], dict(existing["dirty"])
    else:
        salt = secrets.token_hex(16)
        snap = {p: fingerprint(project_root, p, salt) for p in dirty_paths(project_root)}
    target = project_root / baseline_path(baseline_rel, scope)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"head": now_head, "run": run, "scope": scope, "salt": salt, "dirty": snap}, indent=2,
                   sort_keys=True),
        encoding="utf-8")
    return True


def session_changes(project_root: Path, baseline_rel: str, scope: str | None = None) -> list[str]:
    """The paths this session changed: the dirty set plus every baseline path,
    minus those whose content still equals the baseline fingerprint.

    A baseline-dirty file the session restored to HEAD is no longer dirty but
    its content moved, so it is reported too. A corrupt, missing, other-run or
    non-root or other-scope baseline is strict (the dirty set unchanged).
    """
    dirty = dirty_paths(project_root)
    data = read_baseline(project_root, baseline_rel, scope)
    if data is None or data.get("run") != run_id() or data.get("scope") != scope or not at_repo_root(project_root):
        return dirty
    baseline, salt = data["dirty"], data["salt"]
    changed = []
    for p in dict.fromkeys([*dirty, *baseline]):
        now = fingerprint(project_root, p, salt)
        if now is None or baseline.get(p) != now:
            changed.append(p)
    return changed


def record(project_root: Path, baseline_rel: str, scope: str | None = None) -> str:
    """``written`` | ``kept`` | ``not_written`` -- the setup scripts' one call."""
    try:
        root = Path(project_root).resolve()
        if not at_repo_root(root):
            return "not_written"
        return "written" if write_baseline(root, baseline_rel, scope) else "kept"
    except OSError:
        return "not_written"
