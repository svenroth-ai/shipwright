"""Enforcement-flag readers (``SHIPWRIGHT_*`` env vars).

Default-OFF semantics for every ``ENFORCE_*`` flag so PR 1 ships
audit-only — no user-visible effect without explicit opt-in. The
documented rollback lever ``SHIPWRIGHT_PHASE_QUALITY=0`` is the only
exception: the audit defaults ON.

Iterate Campaign B (B3): split out of the 1108-LOC monolith.
"""

from __future__ import annotations

import os


def flag_enabled(name: str, default: bool = False) -> bool:
    """Read a Shipwright enforcement flag from the environment.

    Default is ``False`` for every ``ENFORCE_*`` flag so PR 1 ships with
    audit-only behaviour — no user-visible effect without explicit opt-in.
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def phase_quality_enabled() -> bool:
    """Whether the Stop-hook audit should run at all.

    Default ``on``. Setting ``SHIPWRIGHT_PHASE_QUALITY=0`` (or ``false``)
    is the documented rollback lever (plan § 9.2).
    """
    raw = os.environ.get("SHIPWRIGHT_PHASE_QUALITY", "").strip().lower()
    if not raw:
        return True
    return raw not in ("0", "false", "no", "off")


def skipped_check_ids() -> set[str]:
    """Parse ``SHIPWRIGHT_SKIP_QUALITY_CHECK`` into a set of check ids."""
    raw = os.environ.get("SHIPWRIGHT_SKIP_QUALITY_CHECK", "").strip()
    if not raw:
        return set()
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


def override_reason() -> str:
    """Return the operator-supplied SKIP-override reason, or empty string."""
    return os.environ.get("SHIPWRIGHT_AUDIT_OVERRIDE_REASON", "").strip()


__all__ = [
    "flag_enabled",
    "override_reason",
    "phase_quality_enabled",
    "skipped_check_ids",
]
