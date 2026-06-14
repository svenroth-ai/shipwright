"""First-wins, TTL-armed ``claim_once`` primitive for once-per-event work.

Claude Code fires every registered hook of an event type with no
"active plugin" filter, so a hook registered in N plugins runs N times
for a single event (e.g. one SessionStart → ~12 invocations). When those
invocations each emit the *same* expensive output (a context-injection
block), the result is N-fold duplication.

``claim_once`` lets exactly ONE of the concurrent invocations win the
right to do the once-per-event action; the others skip. It is keyed on a
caller-chosen claim file (typically scoped to the event, e.g. the
session id). A claim older than ``ttl_seconds`` is treated as belonging
to a *previous* event (a later resume/compact SessionStart that reuses
the session id), so the new event re-claims and the action re-fires.

**Fail-open invariant.** Any unexpected error returns ``True`` (the
caller does the work). The worst acceptable case is "work happens N
times" — today's behaviour — never "work silently dropped". For a
quality-signal injector that means a guard bug can re-introduce spam but
can never hide a real finding.

**Known limitation (acceptable for the interim use-case).** Two
concurrent invocations of a *later* (TTL-expired) event can both re-arm
and both win, double-emitting once. Within a single event the claim is
always fresh, so exactly one wins. Late events are temporally separated,
so this race is effectively unreachable in practice and, per the
fail-open invariant, over-emission is the safe failure direction.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

# Restrict event / session tokens to a safe filename charset so an unexpected
# hook-supplied value (separators, ``..``) can never escape the .cache dir.
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]")


def event_claim_path(
    project_root: str | os.PathLike[str],
    event: str,
    session_id: str,
) -> Path:
    """Canonical claim-file path for a once-per-(event, session) guard.

    Returns ``<project_root>/.shipwright/.cache/<event>-<session_id>.claim``.
    ``event`` and ``session_id`` are sanitised to ``[A-Za-z0-9._-]`` (other
    characters → ``_``) so a malformed value cannot traverse out of the
    gitignored ``.cache`` directory. Empty tokens fall back to a literal.

    **Contract — session-unique events only.** Valid for SessionStart / Stop
    (logically once per session). Do NOT use for multi-fire events such as
    PostToolUse without adding a per-event instance discriminator (e.g. a
    tool-use id): the ``(event, session)`` key alone would suppress every
    legitimate later firing until the claim's TTL expires.
    """
    safe_event = _SAFE_TOKEN_RE.sub("_", event or "") or "event"
    safe_sid = _SAFE_TOKEN_RE.sub("_", session_id or "") or "unknown"
    return (
        Path(project_root) / ".shipwright" / ".cache"
        / f"{safe_event}-{safe_sid}.claim"
    )


def claim_once_for_event(
    project_root: str | os.PathLike[str],
    event: str,
    session_id: str,
    *,
    ttl_seconds: float = 30.0,
) -> bool:
    """Return True if THIS invocation should do the once-per-(event, session) work.

    The standard Shipwright fan-out dedup: a shared hook registered in N plugins
    fires N× per event; exactly one invocation should do the real work. Wraps
    :func:`claim_once` on :func:`event_claim_path` with the hook contract:

    - **No real session id** (empty / ``"unknown"``) → return True WITHOUT
      claiming. ``"unknown"`` would be a SHARED key colliding across distinct
      sessionless events, suppressing later ones for the TTL window. Doing the
      work N× is the safe failure direction.
    - **Fail-open:** any guard error → True (never silently drop the work).

    Valid only for session-unique events (SessionStart / Stop), never multi-fire
    PostToolUse — see :func:`event_claim_path`.
    """
    sid = (session_id or "").strip()
    if not sid or sid == "unknown":
        return True
    try:
        return claim_once(
            event_claim_path(project_root, event, sid), ttl_seconds=ttl_seconds,
        )
    except Exception:  # noqa: BLE001 — fail-open: never drop the work
        return True


def claim_once(
    claim_path: str | os.PathLike[str],
    *,
    ttl_seconds: float = 30.0,
    now: float | None = None,
) -> bool:
    """Return True if THIS invocation should perform the once-per-event work.

    Exactly one concurrent invocation sharing ``claim_path`` gets True per
    event; the rest get False until the claim ages past ``ttl_seconds``.
    ``now`` overrides the wall clock for deterministic tests.
    """
    path = Path(claim_path)
    ts = time.time() if now is None else now
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return True  # fail-open: cannot coordinate → let the caller emit

    # Fast path: atomic first-wins create.
    created = _create(path)
    if created is None:
        return True  # unexpected create error → fail-open
    if created:
        return True  # winner of this event

    # A claim already exists. Fresh → another invocation of THIS event
    # owns it → skip. Stale → previous event → re-arm for the new one.
    age = _age(path, ts)
    if age is not None and age < ttl_seconds:
        return False

    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return True  # fail-open
    created = _create(path)
    if created is None or created:
        return True  # re-armed (winner) or fail-open
    return False  # lost the re-arm race to a concurrent invocation


def _create(path: Path) -> bool | None:
    """Atomic exclusive create. True=created(winner), False=exists, None=error."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    except OSError:
        return None
    os.close(fd)
    return True


def _age(path: Path, ts: float) -> float | None:
    """Seconds since the claim file was last written, or None if unreadable.

    Uses filesystem mtime; assumes ``ttl_seconds`` is far larger than the
    mtime granularity (e.g. FAT/exFAT 2 s, some network mounts 1 s) so the
    coarse-tick rounding is irrelevant. The 30 s default holds comfortably.
    """
    try:
        return ts - os.path.getmtime(path)
    except OSError:
        return None
