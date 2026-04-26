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
