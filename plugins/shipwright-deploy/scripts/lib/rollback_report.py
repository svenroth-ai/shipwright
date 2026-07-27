#!/usr/bin/env python3
"""How a rollback states what happened.

Split out of ``rollback.py`` so the orchestration reads as a sequence of
decisions rather than as string-building. This module owns the vocabulary:
the exit codes, the payload shape, and the two failure altitudes.

The distinction the payloads exist to preserve:

- **refused** — nothing on the hosting target was changed (it may have been
  *read*, never written), so the command may say so. It makes no claim about
  what is running, because it learned nothing new about that.
- **halted**  — a rollback was started and did not finish. It may have changed
  something, so it names what, what it last tried, what that reported, and that
  the running version is unverified — then stops. The worst case is not that a
  rollback fails; it is that nobody notices.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_HALT = 3

NOT_CHANGED = (
    "Nothing on the hosting target was changed, and whatever was running "
    "before this command is still running."
)


class HostingError(Exception):
    """A failure reported by the hosting interface (not a bug in this code)."""


def canonical_ref(ref: str | None) -> str | None:
    """`refs/heads/main`, `refs/tags/v1` and `main`/`v1` name the same thing."""
    if not ref:
        return None
    for prefix in ("refs/heads/", "refs/tags/", "refs/remotes/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def base(strategy: str, env_name: str, **extra) -> dict:
    """Every field a caller may read, always present, so absence never means 'fine'."""
    result = {
        "success": False,
        "strategy": strategy,
        "env_name": env_name,
        "target_ref": None,
        "clone_name": None,
        "mutated": False,
        "halt": False,
        "state": "",
        "last_attempted": None,
        "what_it_found": None,
        "previous_ref": None,
        "ref_verified": "n/a",
        "verification_error": None,
        "restored": False,
        "data_drift": None,
        "message": "",
        "operator_message": "",
        "error": None,
    }
    result.update(extra)
    return result


def refused(strategy: str, env_name: str, reason: str, **extra) -> dict:
    """Stopped before changing anything on the host — exit 1."""
    return base(
        strategy, env_name,
        state="refused-no-change",
        error=reason,
        message=f"Refused: {reason}",
        operator_message=f"Refused: {reason}\n{NOT_CHANGED}",
        **extra,
    )


def halted(strategy: str, env_name: str, last_attempted: str, found: str,
           what_changed: str, **extra) -> dict:
    """Started and did not finish — exit 3, state named, operator told to stop."""
    operator = (
        "STOP — this rollback started and did not finish.\n"
        f"What changed on the target: {what_changed}\n"
        f"Last operation attempted: {last_attempted}\n"
        f"What it reported: {found}\n"
        "This rollback did not verify which version is running. Neither the new "
        "release nor the previous one is confirmed live.\n"
        "Do not continue unattended — check the environment before the next action."
    )
    return base(
        strategy, env_name,
        mutated=True,
        halt=True,
        state="started-not-finished",
        last_attempted=last_attempted,
        what_it_found=found,
        error=found,
        message=f"Rollback of {env_name} failed at {last_attempted}: {found}",
        operator_message=operator,
        **extra,
    )


def exit_code(result: dict) -> int:
    if result.get("success"):
        return EXIT_OK
    return EXIT_HALT if result.get("halt") else EXIT_REFUSED


__all__ = [
    "EXIT_HALT", "EXIT_OK", "EXIT_REFUSED", "NOT_CHANGED", "HostingError",
    "base", "canonical_ref", "exit_code", "halted", "refused",
]
