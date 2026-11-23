"""The release's run state: facts decided once, read by every later call (second pass A6, finding F14).

One file, ``release_run.json`` in the checkout's git directory (``git rev-parse --git-path``: per checkout and per
worktree, never in the working tree, so it can neither dirty the tree nor be committed; a directory that is no git
repository falls back to ``.shipwright/runtime/``): the version, the release date and the run id. ``prepare`` writes it; ``aggregate`` and the later subcommands read it, so the date is never
passed by the model ("same date on re-run" was a prose rule) and ``SHIPWRIGHT_RUN_ID`` does not have to survive
separate shell calls (it does not, F14). A state is reused only for the SAME version while its tag does not exist
yet, which is exactly an interrupted release; anything else starts a fresh one.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

STATE_REL = ".shipwright/runtime/release_run.json"  # fallback, outside a git repository
GIT_PATH = "shipwright/release_run.json"
SCHEMA = 1
Clock = Callable[[], datetime]
MAX_AGE_HOURS = 48  # an older unfinished state is an abandoned release, not an interrupted one
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,120}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def state_path(project_root: Path) -> Path:
    root = Path(project_root)
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", GIT_PATH], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return root / STATE_REL
    if done.returncode != 0 or not done.stdout.strip():
        return root / STATE_REL
    found = Path(done.stdout.strip())
    return found if found.is_absolute() else root / found


def load(project_root: Path) -> dict[str, Any] | None:
    """The stored state, or ``None`` when there is none or it is unreadable (a damaged file is never trusted)."""
    try:
        data = json.loads(state_path(project_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(data, dict) and data.get("schema") == SCHEMA and all(
        isinstance(data.get(k), str) and data[k] for k in ("version", "release_date", "run_id"))
    ok = ok and _DATE.fullmatch(data["release_date"]) and _SAFE_ID.fullmatch(data["run_id"])  # read back from disk: check the shape
    return data if ok else None


def save(project_root: Path, state: dict[str, Any]) -> None:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _fresh(stored: dict[str, Any], now: datetime) -> bool:
    try:
        made = datetime.fromisoformat(stored["created_at"])
    except (KeyError, ValueError, TypeError):
        return False
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    return (now - made).total_seconds() < MAX_AGE_HOURS * 3600


def resolve(project_root: Path, version: str, *, tag_exists: bool, release_date: str | None = None,
            clock: Clock = utc_now, use_env_run_id: bool = False, require_fresh: bool = True,
            released: bool = False) -> dict[str, Any]:
    """The state for ``version``: the stored one when it is the same unfinished release, else a new one (not saved).
    An explicit ``release_date`` wins over the stored date (rerunning-a-release.md: "pass it when the original date matters")."""
    stored, now = load(project_root), clock()
    if stored and stored["version"] == version and not tag_exists and (_fresh(stored, now) or not require_fresh):
        state = dict(stored, reused=True)
        if not released and require_fresh and not str(stored.get("created_at", "")).startswith(f"{now:%Y-%m-%d}"):
            state["release_date"], state["created_at"] = f"{now:%Y-%m-%d}", now.isoformat(timespec="seconds")  # only `prepare` re-dates (an abandoned look at yesterday must not date today's release); a release that crosses midnight keeps its date
        env_id = os.environ.get("SHIPWRIGHT_RUN_ID") if use_env_run_id else None
        if env_id and _SAFE_ID.fullmatch(env_id):  # a new dispatch names its own run
            state["run_id"] = env_id
    else:
        env_id = os.environ.get("SHIPWRIGHT_RUN_ID") if use_env_run_id else None  # only a dispatched run's id: a stale variable is not one
        run_id = env_id if env_id and _SAFE_ID.fullmatch(env_id) else f"changelog-v{version}-{now:%Y%m%d-%H%M%S}"
        state = {"schema": SCHEMA, "version": version, "release_date": f"{now:%Y-%m-%d}", "run_id": run_id,
                 "created_at": now.isoformat(timespec="seconds"), "reused": False}
    if release_date:
        state["release_date"] = release_date
    return state
