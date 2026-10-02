#!/usr/bin/env python3
"""F0 cross-invocation resume - the state a RED run leaves for the next one.

After a unit goes red the agent fixes it and re-runs F0. Re-running the whole unit
(`shared/tests`: 15-22 min) to learn that two tests are now green is the cost the
resume removes; this module owns the persisted half of it (`suite_resume` owns the
decisions). What is kept per unit: the final JUnit report, the red test ids (pytest
`lastfailed`), the coverage data file, the unit's test-file set and a signature of how
the unit is run - plus a hash of EVERY tracked and untracked, non-ignored file (not only
`.py`: SKILL.md, prompts, JSON and fixtures all drive tests here).

Trust rules, each one a refusal rather than a guess:

- **Keyed by checkout**: the store lives under the main repo's gitignored
  `.shipwright/runs/f0-evidence/resume/<hash of the checkout path>/`, so another
  worktree's state is never even looked at.
- **Atomic**: a new state is written beside the old one and published by replacing the
  small `CURRENT` pointer file. Every stored file's SHA-256 is in the manifest, so a torn
  or hand-edited state is detected on load and means "run in full".
- **Bound to a lineage**: the merge base with `origin/main` must be unchanged (a rebase
  or a merge of main re-bases every result), the state must be younger than a day, and a
  green result may be reused at most `MAX_REUSES` times in a row.
- **A resume token, not a cache**: state is only kept while some unit is red. A fully
  green run deletes it, so a later F0 on a later tree can never be answered from here.

Source edits between the two runs are EXPECTED (that is the point: the fix) and are not
a refusal - operator decision 2026-10-02, CI re-runs the full suite on every PR and is
the safety net. The per-file hashes are what let the resume say WHAT changed and drop
the stale coverage of exactly those files.

ASCII-only operator strings (a cp1252 console raises UnicodeEncodeError, #244).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_coverage_rules import _FALLBACK_BRANCH as BASE_REF  # noqa: E402
from scripts.tools.suite_retention import retention_root  # noqa: E402
from scripts.tools.suite_units import Unit, cov_label  # noqa: E402
from scripts.tools.suite_worktree_diff import controlled_git_env  # noqa: E402

SCHEMA_VERSION = 1
MAX_REUSES = 3
MAX_AGE_SECONDS = 24 * 3600
NO_STATE = "no saved state from a prior red run"
_CURRENT = "CURRENT"
_UNIT_KEYS = ("sig", "outcome", "lastfailed", "test_files", "reuses")


@dataclass(frozen=True)
class TreeSnapshot:
    """Every tracked + untracked, non-ignored file of a checkout, hashed."""

    files: dict[str, str]  # posix relpath -> sha256 of the bytes ("-" = unreadable)
    base_sha: str          # merge base with origin/main
    digest: str            # one hash over all of `files`


@dataclass(frozen=True)
class LoadedState:
    directory: Path
    manifest: dict
    tree: dict[str, str]


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(root: Path, args: tuple[str, ...], runner) -> str | None:
    try:
        proc = runner(  # nosec B603 - fixed argv, shell=False
            ["git", "-C", str(root), *args], cwd=str(root), env=controlled_git_env(),
            capture_output=True, text=True, errors="replace", shell=False, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout or "" if proc.returncode == 0 else None


def tree_snapshot(project_root: Path, runner=subprocess.run,
                  base_ref: str = BASE_REF) -> TreeSnapshot | None:
    """Hash the whole checkout; None when it is not a git checkout or has no merge base."""
    root = Path(project_root).resolve()
    listing = _git(root, ("ls-files", "-co", "--exclude-standard", "-z"), runner)
    base = _git(root, ("merge-base", base_ref, "HEAD"), runner)
    if listing is None or not (base or "").strip():
        return None
    files: dict[str, str] = {}
    for rel in sorted(p for p in listing.split("\0") if p):
        path = root / rel
        try:
            payload = (os.readlink(path).encode("utf-8", errors="surrogatepass")
                       if path.is_symlink() else path.read_bytes())
            files[rel.replace("\\", "/")] = _sha(payload)
        except OSError:  # deleted-but-tracked, a gitlink directory, a locked file
            files[rel.replace("\\", "/")] = "-"
    digest = _sha("".join(f"{k}\0{v}\n" for k, v in sorted(files.items()))
                  .encode("utf-8", errors="surrogatepass"))
    return TreeSnapshot(files, base.strip(), digest)


def changed_files(prior: dict[str, str], now: dict[str, str]) -> list[str]:
    """Paths added, removed or edited between two snapshots."""
    return sorted(k for k in prior.keys() | now.keys() if prior.get(k) != now.get(k))


_ENV_FILES = ("pyproject.toml", "uv.lock", "pytest.ini", "setup.cfg", "tox.ini")


def unit_signature(unit: Unit, snapshot: TreeSnapshot | None = None) -> str:
    """How a unit is RUN (not where this checkout lives): a different one is a new unit.
    With a snapshot, the test-environment inputs (pytest/coverage config, dependency lock
    of the unit and of the repo root) are part of it: a changed one is a new unit too."""
    env = []
    if snapshot is not None:
        cwd = "" if unit.cwd in ("", ".") else unit.cwd + "/"
        env = [snapshot.files.get(prefix + name) for prefix in sorted({"", cwd}) for name in _ENV_FILES]
    return _sha(json.dumps([unit.id, unit.cwd, unit.target, list(unit.markers),
                            list(unit.extra_deps), bool(unit.cov_file), env]).encode("utf-8"))


def unit_test_files(snapshot: TreeSnapshot, unit: Unit) -> list[str]:
    """`path:digest` of the unit's `.py` files under its test target plus every
    `conftest.py` above it; a changed SET (added, removed, renamed) or an EDITED test means
    the saved red ids and reports no longer describe the unit."""
    prefix = unit.target if unit.cwd in ("", ".") else f"{unit.cwd}/{unit.target}"

    def _in(p: str) -> bool:
        if p == prefix or p.startswith(prefix + "/"):
            return True  # fixtures, golden files and snapshots drive tests as much as .py
        head, _, name = p.rpartition("/")
        return name == "conftest.py" and (not head or prefix.startswith(head + "/"))
    return sorted(f"{p}:{digest}" for p, digest in snapshot.files.items()
                  if digest != "-" and _in(p))  # "-" = deleted/unreadable


def store_dir(project_root: Path) -> Path:
    key = _sha(str(Path(project_root).resolve()).encode("utf-8", errors="replace"))[:16]
    return retention_root(project_root) / "resume" / key


def _stash(src: Path | None, dest_dir: Path, rel: str, hashes: dict[str, str]) -> str | None:
    if src is None or not Path(src).is_file():
        return None
    shutil.copyfile(src, dest_dir / rel)
    hashes[rel] = _sha((dest_dir / rel).read_bytes())
    return rel


def save_state(project_root: Path, *, run_id: str, invocation: str, snapshot: TreeSnapshot,
               chain: tuple[str, ...], entries: dict[str, dict]) -> bool:
    """Publish a new state; never raises (a lost resume only costs a full run).

    `entries[unit_id]` carries `_UNIT_KEYS` plus `report` / `cov` source paths (or None).
    """
    store = store_dir(project_root)
    token = f"{int(time.time())}-{uuid4().hex[:8]}"
    new = store / token
    pointer = store / f"{_CURRENT}.{token}"
    try:
        (new / "reports").mkdir(parents=True)
        (new / "cov").mkdir()
        hashes: dict[str, str] = {}
        units: dict[str, dict] = {}
        for unit_id, entry in sorted(entries.items()):
            label = cov_label(unit_id)
            rec = {k: entry[k] for k in _UNIT_KEYS}
            rec["report"] = _stash(entry.get("report"), new, f"reports/{label}.xml", hashes)
            rec["cov"] = _stash(entry.get("cov"), new, f"cov/{label}", hashes)
            units[unit_id] = rec
        tree_bytes = json.dumps(snapshot.files, sort_keys=True).encode("utf-8")
        (new / "tree.json").write_bytes(tree_bytes)
        hashes["tree.json"] = _sha(tree_bytes)
        manifest = {
            "schema_version": SCHEMA_VERSION, "run_id": run_id, "invocation": invocation,
            "created": time.time(), "base_sha": snapshot.base_sha,
            "tree_digest": snapshot.digest, "chain": list(chain), "units": units,
            "sha256": hashes}
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (new / "manifest.json").write_bytes(manifest_bytes)
        # the pointer also pins the manifest's own hash, which no file inside the token can
        pointer.write_text(f"{token}\n{_sha(manifest_bytes)}", encoding="utf-8")
        os.replace(pointer, store / _CURRENT)  # the ONE atomic publication step
    except OSError as exc:
        warnings.warn(f"F0 resume: could not save state: {exc}", stacklevel=2)
        shutil.rmtree(new, ignore_errors=True)
        pointer.unlink(missing_ok=True)
        return False
    _prune(store, keep=token)
    return True


def _prune(store: Path, keep: str) -> None:
    try:
        entries = list(store.iterdir())
    except OSError:
        return
    for path in entries:
        if path.is_dir() and path.name != keep:
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.name.startswith(f"{_CURRENT}."):  # a crashed publish
            path.unlink(missing_ok=True)


def clear_state(project_root: Path) -> None:
    """Spend the resume token (best-effort: a leftover only costs a refused resume)."""
    store = store_dir(project_root)
    try:
        (store / _CURRENT).unlink(missing_ok=True)
    except OSError:
        pass
    _prune(store, keep="")


def load_state(project_root: Path, now: float | None = None) -> tuple[LoadedState | None, str]:
    """The saved state, or (None, why) - every doubt is a refusal."""
    store = store_dir(project_root)
    try:
        token, _, pinned = (store / _CURRENT).read_text(encoding="utf-8").strip().partition("\n")
    except OSError:
        return None, NO_STATE
    directory = store / token
    if (not token or token in (".", "..") or Path(token).name != token
            or directory.resolve().parent != store.resolve() or not directory.is_dir()):
        return None, "saved state is unreadable (bad pointer)"
    try:
        manifest_bytes = (directory / "manifest.json").read_bytes()
        if _sha(manifest_bytes) != pinned:
            return None, "saved state is torn or edited (manifest.json)"
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if manifest["schema_version"] != SCHEMA_VERSION:
            return None, "saved state has another schema version"
        age = (now if now is not None else time.time()) - float(manifest["created"])
        if not 0 <= age <= MAX_AGE_SECONDS:
            return None, "saved state is older than 24 hours"
        for rel, digest in manifest["sha256"].items():
            if _sha((directory / rel).read_bytes()) != digest:
                return None, f"saved state is torn or edited ({rel})"
        tree = json.loads((directory / "tree.json").read_text(encoding="utf-8"))
        if not isinstance(manifest["units"], dict) or not isinstance(tree, dict):
            return None, "saved state is malformed"
        hashed = manifest["sha256"]  # every file a plan will open must have been verified
        if any(rec.get(k) and rec[k] not in hashed
               for rec in manifest["units"].values() for k in ("report", "cov")):
            return None, "saved state is malformed"
    except (OSError, ValueError, KeyError, TypeError):
        return None, "saved state is unreadable or torn"
    return LoadedState(directory, manifest, tree), ""
