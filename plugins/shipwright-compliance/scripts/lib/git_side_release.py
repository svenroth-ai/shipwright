"""Hand-off from the PreToolUse ``check_rtm_coverage`` hook to the git-side check.

When a logged override releases a blocked ``git commit`` command in the Claude Code hook,
the git ``pre-commit`` check that git itself runs for that same commit would block it a
second time and demand a second logged override. :func:`grant` (PreToolUse side, right
after the override was consumed) leaves an untracked token under ``.shipwright/locks``;
:func:`take` (git side) removes it and reports whether it was there and fresh. ``unlink``
is the arbiter: of two concurrent takers exactly one succeeds. A token older than
:data:`TTL` is not honoured (the commit it was granted for is long over) and is swept.
The token names the override entry it rides on and is honoured only while that entry's
consumption marker exists, so a hand-written token without a logged, consumed override is
refused. Pure stdlib; every failure resolves toward "no token" = normal evaluation, so a broken
hand-off can only cost the operator one more logged override, never skip the check.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from override_marker import marker as override_marker_path

LOCK_DIR = Path(".shipwright/locks")
TTL = timedelta(minutes=2)
CLOCK_SKEW_S = 60  # a token stamped slightly in the future (clock step) is still honoured


def token(project_root: str | Path, hook: str) -> Path:
    return Path(project_root) / LOCK_DIR / f"git-side-release-{hook}"


def head(project_root: str | Path) -> str:
    """The commit the next commit builds on (``none`` when unborn or unreadable)."""
    try:
        out = subprocess.run(["git", "-C", str(project_root), "rev-parse", "--verify", "-q",
                              "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "none"
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "none"


def grant(project_root: str | Path, hook: str, at: datetime) -> str | None:
    """Leave the hand-off token, bound to the current HEAD and to the consumed override
    entry timestamp *at*; a WARN sentence on failure."""
    path = token(project_root, hook)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{head(project_root)}\n{at.isoformat()}", encoding="utf-8")  # re-stamps too
    except OSError as exc:
        return (f"the git-side hand-off could not be written ({type(exc).__name__}); the "
                "git pre-commit check will ask for its own logged override")
    return None


def _backed_by_override(project_root: str | Path, hook: str, stamp: str) -> bool:
    """True when the token's override entry was really consumed (its marker exists)."""
    try:
        at = datetime.fromisoformat(stamp)
        return override_marker_path(project_root, hook, at).is_file()
    except (ValueError, OSError):
        return False


def claim(project_root: str | Path, hook: str,
          now: float | None = None) -> tuple[bool, str | None]:
    """``(True, None)`` when a fresh token for the CURRENT HEAD existed and this call removed
    it; else ``(False, why)`` -- ``why`` is ``None`` when there was simply no token.

    The token is removed whatever its verdict (a stale or mismatched one must not linger
    for a later commit), and ``unlink`` makes the taker single. A commit that lands on a
    different HEAD than the one granted for -- the second commit of ``a && b`` -- is not
    released: it needs its own logged override. A refused token is named, so a release
    that expired behind a long step on the same command line is not mistaken for no release.
    """
    path = token(project_root, hook)
    try:
        age = (now if now is not None else time.time()) - path.stat().st_mtime
        raw = path.read_bytes().decode("utf-8", errors="replace").strip()  # junk = mismatch
        path.unlink()
    except OSError:
        return False, None  # absent, unreadable, or a concurrent taker removed it first
    if age < -CLOCK_SKEW_S:
        return False, "the hand-off token is stamped in the future (clock step); it is ignored"
    if age > TTL.total_seconds():
        return False, (f"the Claude Code hook released this command {int(age)} s ago but the "
                       f"hand-off lasts {int(TTL.total_seconds())} s: run the commit as its own "
                       "command, without a long step before it")
    bound, _, stamp = raw.partition("\n")
    if not _backed_by_override(project_root, hook, stamp.strip()):
        return False, ("the hand-off token names no consumed override entry; it is ignored "
                       "(a token is only honoured while the logged override it rides on is used)")
    if bound.strip() != head(project_root):
        return False, ("the Claude Code hook released this command for another HEAD (an earlier "
                       "step moved it, or this is a later commit of the same command): this "
                       "commit needs its own logged override")
    return True, None


def take(project_root: str | Path, hook: str, now: float | None = None) -> bool:
    """:func:`claim` without the reason."""
    return claim(project_root, hook, now)[0]
