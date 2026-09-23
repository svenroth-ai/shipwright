"""Cross-platform executable resolution.

On Windows, `npm`/`npx`/`yarn`/etc. are installed as `.cmd` shims.
`subprocess.Popen` with `shell=False` cannot find them via the bare name
and raises WinError 2 ("system cannot find the file specified"). This
helper resolves them via `shutil.which` before subprocess invocation.

`shell=True` is intentionally NOT used: profile-author-supplied command
strings would become a command-injection surface for any tampering of
profile JSON.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_trusted_executable(name: str) -> str | None:
    """``shutil.which(name)``, rejecting a hit that only resolved because
    Windows implicitly searches the current working directory before PATH
    (the BatBadBut class) — a directory this process is launched into could
    otherwise plant its own ``<name>.exe``/``<name>.cmd``/``<name>.bat`` at
    its root and have it run instead of the real executable, since the
    process's cwd is typically the project being acted on. Never raises.

    Single source of truth for this guard — previously duplicated
    byte-for-byte between ``external_review_default_legs._resolve_codex_binary``
    and ``codex_activation_helper._resolve_codex_binary`` (R2 code review,
    2026-09-22), which risked the two copies silently drifting apart. Both
    callers now delegate here and keep their own private wrapper name/shape
    unchanged, so existing test monkeypatches targeting those wrapper names
    keep working."""
    found = shutil.which(name)
    if found is None:
        return None
    try:
        if Path(found).resolve().parent == Path.cwd().resolve():
            return None
    except (OSError, RuntimeError):
        return None
    return found


def resolve_executable(name: str) -> str:
    """Return an absolute path to the executable, or `name` unchanged.

    On Windows: try `which(name)` first (resolves `.cmd`/`.exe`/`.bat`
    via PATHEXT), then fall back to `which(name + '.cmd')`. Returns the
    original `name` if nothing is found — the caller will see the
    underlying Popen error if the exe truly isn't installed.

    On non-Windows: returns `name` unchanged.
    """
    if os.name != "nt":
        return name
    hit = shutil.which(name)
    if hit:
        return hit
    if not name.lower().endswith(".cmd"):
        hit = shutil.which(f"{name}.cmd")
        if hit:
            return hit
    return name
