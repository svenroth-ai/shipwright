#!/usr/bin/env python3
"""SessionStart producer: is the host's must-pass check set still the real one?

Drives `tools/check_required_checks.py`, which compares the checks this repo's
workflows produce against the ones the host will actually block a merge on. That
comparison existed and was invoked by nothing — no hook, no skill step, no
workflow — so it ran only when a human remembered (P3.03 / `trg-304c764b`).

**Why the producer chain and not a push-time gate.** Three properties decide it,
and the sibling decision in the same change sent `scripts/verify_local.py` the
other way for the mirror-image reasons: this subject is *portable* (it derives
from whatever workflows exist, and lives in `shared/`), it needs the *operator's
own* `gh` auth rather than a CI token, and its answer is *diff-independent* — it
moves when a workflow is added, renamed or deleted, or when someone edits the
host's rules outside the repository. `verify_local.py` is monorepo-only,
needs nothing, and changes with every diff, so it belongs to a phase gate.

**…and why it is throttled.** `import_github_findings.py` is the network
producer this hook sits beside, and its throttle is what makes a network call
acceptable in a chain that runs before the session opens.

**This wrapper exists because the producer cannot be registered directly.** Two
facts about the chain, both read out of `run_if_cache_ready.py` rather than
assumed: it forwards each child's **stderr verbatim** and parses the child's
**stdout** as SessionStart JSON (so the producer's drift paragraph would spill
into the session and fail `test_hook_output_schema_compliance.py`, which executes
every registered hook); and it runs children with `check=False` but propagates
the FIRST non-zero code, while the producer's documented `exit 2` — no `gh`, no
auth, unreachable repo — is the normal case on a machine without the GitHub CLI.

So the contract is: **always exit 0, never write to stdout**, and keep the
operator's one channel — stderr — for things they can act on. That is not the
same as never speaking: an exit code the producer does not document, and a check
that has not *succeeded* in many windows, both reach them (see
`required_checks_state.stale_since`, which closes the fail-open where an expired
token would have ended this check permanently and silently).

**The producer is driven as a subprocess, never imported.** It does an eager
module-scope `sys.path.insert` plus `from lib…` / `from triage…`; binding `lib`
inside this process is the ADR-045 collision that resolves to a different
directory depending on what loaded first — green locally, red in CI. Deferring
the import would only defer *which* `lib` binds.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

#: ``shared/scripts`` — this file's grandparent. Everything is resolved from the
#: wrapper's own location because a hook process inherits an arbitrary working
#: directory, and because the same file is reached from an installed plugin cache
#: where a relative path would land somewhere else entirely.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_HOOKS_DIR = Path(__file__).resolve().parent
PRODUCER = _SCRIPTS_DIR / "tools" / "check_required_checks.py"

if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from required_checks_state import (  # noqa: E402
    DEFAULT_THROTTLE_HOURS,
    ENV_THROTTLE,
    STALE_WINDOWS,
    is_due,
    record,
    release,
    stale_since,
    state_path,
    throttle_hours,
)

__all__ = [
    "DEFAULT_THROTTLE_HOURS", "ENV_THROTTLE", "STALE_WINDOWS", "PRODUCER",
    "TIMEOUT_SECONDS", "is_due", "main", "producer_argv", "record", "release",
    "resolve_project_root", "run", "stale_since", "state_path", "throttle_hours",
]

#: Bounded so a stalled `gh` cannot hold session start open, and deliberately BELOW
#: the 30 s cap `test_hook_output_schema_compliance` puts on the whole chain — a
#: hook whose own allowance exceeded that could only ever fail that gate. Measured,
#: the producer answers in ~1.5 s, so this is >10x headroom.
TIMEOUT_SECONDS = 20

#: What the producer documents: 0 = compared (in sync, or drift recorded);
#: 2 = the configuration could not be read. Anything else is a defect in it.
_EXPECTED_EXITS = (0, 2)


def _warn(message: str) -> None:
    """The operator's only channel.

    stdout belongs to the SessionStart schema, so it cannot carry this. stderr is
    re-emitted verbatim by `run_if_cache_ready.py`, which is exactly the reach
    wanted — and it means a broken wrapper is visible without inventing a log
    file nothing else in this chain writes.

    **Guarded, because this is the floor every fail-soft path stands on.**
    `sys.stderr.write` can raise — `BrokenPipeError` if the chain's parent died
    mid-run, `ValueError` on a closed stream. Raising from inside `run()`'s
    handler would escape to `main()`'s handler, which calls this again, which
    raises again — this time out of `main()`, producing exactly the traceback and
    non-zero exit the whole design exists to prevent.
    """
    try:
        sys.stderr.write(f"[required-checks] {message}\n")
    except Exception:  # noqa: BLE001 - a diagnostic must never become the fault
        pass


def resolve_project_root() -> Path:
    """The project this session is about.

    Mirrors `check_drift.py`: the canonical resolver when it imports, the working
    directory when it does not. `ImportError` is caught explicitly because in a
    degraded or partially-synced tree that is the expected failure, not a bug.
    """
    try:
        scripts_dir = str(_SCRIPTS_DIR)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import resolve_project_root as _resolve
        return _resolve()
    except (ImportError, ValueError):
        return Path(os.getcwd())


def _is_shipwright_project(root: Path) -> bool:
    """The F7 boundary — never act on a tree the framework is not installed in.

    Delegates to the canonical predicate so every hook agrees on where greenfield
    ends and a foreign repository begins. **The fallback is a strict SUBSET of it,
    deliberately:** it fires only when the import collides, the branch nobody
    exercises, so it must not say "yes" where canonical says "no". A bare
    `.shipwright/` is exactly that case — a leftover from a removed install
    satisfies neither `CONFIG_MARKER` nor `.shipwright/agent_docs/` — and admitting
    it would spend three authenticated `gh` calls on a stranger's repository.
    """
    try:
        scripts_dir = str(_SCRIPTS_DIR)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import is_shipwright_project
        return bool(is_shipwright_project(root))
    except (ImportError, ValueError):
        return any(
            (root / marker).is_file()
            for marker in ("shipwright_run_config.json", "shipwright_build_config.json")
        )


def producer_argv(project_root: Path | str) -> list[str]:
    """The exact command, as a list.

    Never a shell string: the only interpolated value is a filesystem path that
    arrives from the resolver, and a fixed argv keeps it that way by construction
    rather than by review.
    """
    return [sys.executable, str(PRODUCER), "--project-root", str(project_root)]


def run(project_root: Path | str, runner=subprocess.run, *,
        now: datetime | None = None) -> int:
    """Drive the producer at most once per throttle window. Returns 0 — always.

    ``runner`` is injected by the tests so the invocation contract can be asserted
    without three live `gh` calls, the same shape `verify_local.py` uses.
    """
    root = Path(project_root)
    if not _is_shipwright_project(root):
        return 0
    if not PRODUCER.is_file():
        # A partially-synced plugin cache. Nothing to say to the operator: they
        # did not ask for this producer, and the cache guard already reports it.
        return 0
    if not is_due(root, now=now):
        return 0

    # RESERVE the window before launching, not after returning: two chains opened
    # at once would otherwise both read an expired stamp, both call out, and only
    # then both write. Reserving narrows that race to one small write; it does not
    # eliminate it, deliberately — a lock would have to be acquired, released and
    # reaped on a path whose whole cost is one extra comparison.
    #
    # A window that cannot be RECORDED cannot be bounded, so an unwritable state
    # file skips the producer rather than running it unthrottled on every session.
    # Silent, for the same reason the timeout below is: an unwritable `.shipwright/`
    # would otherwise emit a line every single session, which is precisely the
    # training-to-ignore this prefix cannot afford.
    if not record(root, succeeded=False, when=now):
        return 0

    try:
        completed = runner(
            producer_argv(root),
            cwd=str(root),
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        code = completed.returncode
        # exit 0 means it actually compared. exit 2 means it could not read the
        # configuration — a real outcome, but NOT a success, and conflating the two
        # is what would let an expired token look like a healthy check forever.
        if code == 0:
            record(root, succeeded=True, when=now)
        if code not in _EXPECTED_EXITS:
            # Deliberately does NOT echo the child's captured output: it is `gh`
            # error text, which is where a token or auth header would surface.
            _warn(f"producer exited {code}, which it does not document "
                  f"(expected {' or '.join(str(c) for c in _EXPECTED_EXITS)}). "
                  f"Re-run it by hand: {' '.join(producer_argv(root))}")
    except subprocess.TimeoutExpired:
        # The reservation STANDS. Silent on purpose: a slow network is not an
        # operator-actionable defect, and a line every window would train them to
        # ignore this prefix — which is the channel the warnings above and below
        # depend on. Staleness is what eventually speaks for this case.
        pass
    except Exception as exc:  # noqa: BLE001 — a producer may never break a session
        # RELEASE the reservation: failing to *start* is usually fixable (a broken
        # interpreter path, a half-written file), and holding the window would hide
        # the fix rather than the fault.
        release(root)
        _warn(f"producer could not be started: {type(exc).__name__}: {exc}")

    _warn_if_stale(root, now=now)
    return 0


def _warn_if_stale(root: Path, *, now: datetime | None = None) -> None:
    """Speak once when the check has not SUCCEEDED for many windows.

    This is the fail-open the rest of the design would otherwise have. `exit 2`
    covers "not authenticated", the wrapper is silent on that path by contract,
    and the attempt still consumes its window — so an expired token ends the check
    permanently with nothing anywhere recording that it stopped working. Worse,
    that failure correlates with the event being watched, since whoever rotates
    credentials is often whoever edits the host's rules.
    """
    try:
        days = stale_since(root, now=now)
    except Exception:  # noqa: BLE001 - diagnosing staleness may not become the fault
        return
    if days is None:
        return
    _warn(f"the must-pass check set has not been verified for {days} day(s) — "
          f"the check is running but not succeeding. Run it by hand to see why: "
          f"{' '.join(producer_argv(root))}")


def main() -> int:
    """Always 0, unconditionally.

    `resolve_project_root()` runs OUTSIDE `run()`'s guard and can raise beyond
    the `(ImportError, ValueError)` it handles: the canonical resolver calls
    `Path.cwd()` and `cwd.iterdir()`, which raise `FileNotFoundError` when the
    working directory has been deleted and `PermissionError` when it cannot be
    listed — and the `os.getcwd()` fallback raises the same way. Uncaught, the
    traceback would go to stderr (forwarded verbatim) and exit 1 (propagated by
    the chain as its first non-zero code), producing exactly the failed session
    this hook exists to prevent.
    """
    try:
        return run(resolve_project_root())
    except Exception as exc:  # noqa: BLE001
        _warn(f"could not resolve a project root: {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
