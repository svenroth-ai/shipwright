#!/usr/bin/env python3
"""Read the parts of a deploy profile the runtime actually acts on.

The profiles under ``shared/profiles/deploy/`` have declared
``smoke_test.poll_interval_seconds`` / ``max_wait_seconds`` and
``rollback.data_rollback_strategy`` since they were written, and nothing read
them: the liveness check asked once with a fixed ten-second limit, and rollback
never mentioned stored data. This module is the single reader for both, so the
two consumers (``shared/scripts/smoke_test.py`` and the deploy plugin's
``rollback.py``) cannot drift apart on what a profile means.

Imported **bare** (``from deploy_profile import ...``) rather than via ``lib.``:
one consumer is a shared module and the other is plugin-local, and a ``lib.``
import binds ``sys.modules['lib']`` for whichever runs first (ADR-044/045).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Today's shipped behaviour when nothing declares otherwise: one attempt, ten
# seconds. `max_wait = None` means "do not poll" and is what keeps every
# existing caller (notably /shipwright-test) unchanged.
DEFAULT_TIMEOUT = 10
DEFAULT_POLL_INTERVAL = 5
DEFAULT_MAX_WAIT = None


class ProfileError(ValueError):
    """The profile could not be read or does not have the expected shape."""


@dataclass(frozen=True)
class SmokePolicy:
    """How long to keep asking a freshly released application whether it is up."""

    timeout: int = DEFAULT_TIMEOUT
    poll_interval: int = DEFAULT_POLL_INTERVAL
    max_wait: int | None = DEFAULT_MAX_WAIT
    health_path: str | None = None
    source: dict[str, str] = field(default_factory=dict)

    @property
    def polls(self) -> bool:
        return self.max_wait is not None


def load_profile(path: Path | str) -> dict:
    """Load and shallow-validate a deploy profile."""
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"deploy profile not found: {file}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"deploy profile {file} is not readable JSON: {exc}") from exc
    if not isinstance(data, dict) or not data.get("target_id"):
        raise ProfileError(f"deploy profile {file} has no target_id")
    return data


def _positive_int(value, label: str) -> int | None:
    if value is None:
        # None means "not supplied" all the way through: `pick` reads it as
        # "no explicit override" and falls through to the profile, then the
        # default. It is never a validated zero.
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileError(f"{label} must be a non-negative integer, got {value!r}")
    return value


def smoke_policy(
    profile: dict | None = None,
    *,
    timeout: int | None = None,
    poll_interval: int | None = None,
    max_wait: int | None = None,
    health_path: str | None = None,
) -> SmokePolicy:
    """Resolve the effective liveness policy.

    Precedence is **per field**: an explicit argument overrides only its own
    field, so ``--timeout 5`` against a profile keeps that profile's polling
    deadline. ``source`` records where each winning value came from, because a
    single ``deadline_source`` would over-claim on mixed input.
    """
    declared = (profile or {}).get("smoke_test") or {}
    if profile is not None and not isinstance(declared, dict):
        raise ProfileError("smoke_test must be an object")
    target = (profile or {}).get("target_id")
    origin = f"profile:{target}" if profile else "default"

    def pick(explicit, key: str, fallback):
        if explicit is not None:
            return explicit, "cli"
        if key in declared:
            return _positive_int(declared[key], f"smoke_test.{key}"), origin
        return fallback, "default"

    resolved_timeout, timeout_src = pick(
        _positive_int(timeout, "--timeout"), "timeout_seconds", DEFAULT_TIMEOUT)
    resolved_interval, interval_src = pick(
        _positive_int(poll_interval, "--poll-interval"), "poll_interval_seconds",
        DEFAULT_POLL_INTERVAL)
    resolved_max_wait, max_wait_src = pick(
        _positive_int(max_wait, "--max-wait"), "max_wait_seconds", DEFAULT_MAX_WAIT)

    resolved_path, path_src = health_path, "cli"
    if resolved_path is None:
        resolved_path = declared.get("health_path")
        path_src = origin if resolved_path is not None else "default"

    if resolved_max_wait is not None and not resolved_interval:
        raise ProfileError("poll_interval must be greater than zero when a deadline is set")

    return SmokePolicy(
        timeout=resolved_timeout if resolved_timeout is not None else DEFAULT_TIMEOUT,
        poll_interval=resolved_interval or DEFAULT_POLL_INTERVAL,
        max_wait=resolved_max_wait,
        health_path=resolved_path,
        source={
            "timeout": timeout_src,
            "poll_interval": interval_src,
            "max_wait": max_wait_src,
            "health_path": path_src,
        },
    )


def data_rollback_strategy(profile: dict | None) -> str | None:
    """What the target says happens to stored data when code goes back."""
    rollback = (profile or {}).get("rollback") or {}
    value = rollback.get("data_rollback_strategy") if isinstance(rollback, dict) else None
    return value if isinstance(value, str) and value else None


__all__ = [
    "DEFAULT_MAX_WAIT",
    "DEFAULT_POLL_INTERVAL",
    "DEFAULT_TIMEOUT",
    "ProfileError",
    "SmokePolicy",
    "data_rollback_strategy",
    "load_profile",
    "smoke_policy",
]
