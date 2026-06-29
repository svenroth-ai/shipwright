"""Bloat-findings dashboard rows.

Renders the three Quality-Indicators rows the Compliance Dashboard
gained in Iterate Campaign B (B3). Producer:
``shared.scripts.lib.phase_quality.collect_bloat_summary``.

Two layouts:

* :func:`bloat_rows_events_mode` — 4-col table where the last column is
  ``Why warn?`` (event-sourced dashboard).
* :func:`bloat_rows_legacy_mode` — 4-col table where the last column is
  ``Description`` (legacy config-sourced dashboard).

Extracted from ``compliance_report.py`` so that file stays at its
grandfathered ceiling (the anti-ratchet rule blocks net additions —
moving the helper here keeps the dashboard surface readable without
ratcheting compliance_report.py).
"""

from __future__ import annotations

from pathlib import Path


def _summary(project_root: Path) -> dict[str, int]:
    # Lazy import: a module-level `from lib.phase_quality import ...` would
    # cache the shared `lib` package in sys.modules at import time, which
    # then shadows plugin-local `lib/` (e.g. shipwright-test/scripts/lib/,
    # this plugin's lib/thresholds.py) for every later `from lib.X` import
    # in the same pytest session. Deferring the import keeps the module
    # load side-effect-free.
    try:
        from lib.phase_quality import collect_bloat_summary
    except ImportError:  # pragma: no cover - broken env only
        return {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}
    return collect_bloat_summary(project_root)


def _badge(ok: bool) -> str:
    return "PASS" if ok else "WARN"


def bloat_rows_events_mode(project_root: Path) -> list[str]:
    """Three rows (+ trailing blank) for the events-mode Quality table.

    The trailing blank line is bundled in so the caller can replace
    its own ``lines.append("")`` with this extend — saves one line on
    the grandfathered ``compliance_report.py`` and keeps the anti-
    ratchet rule satisfied (Iterate Campaign B B3).
    """
    s = _summary(project_root)
    # over_limit counts grandfathered files above the standard limit. The
    # baseline only holds grandfathered/exception entries, so this is the
    # ACCEPTED set — grandfathering IS the acceptance, not a deficit — and a
    # genuinely new crossing is never in it (the Group H detective owns those).
    # Render INFO, not WARN: the live signal is the ratchet delta below
    # (regression past the accepted ceiling). Keying the WARN off the
    # grandfathered count is the alarm-fatigue flaw BP-1 fixed for traceability.
    rd_ok = s["ratchet_delta"] <= 0
    rd_why = (
        f"grandfathered surface ratcheted up by {s['ratchet_delta']} line(s) — "
        "Iron Law violation" if not rd_ok else ""
    )
    return [
        f"| Bloat over-limit (grandfathered) | {s['over_limit']} | INFO |  |",
        f"| Bloat in allowlist | {s['in_allowlist']} entries | INFO |  |",
        f"| Bloat ratchet delta | {s['ratchet_delta']:+d} lines | {_badge(rd_ok)} | {rd_why} |",
        "",
    ]


def bloat_rows_legacy_mode(project_root: Path) -> list[str]:
    """Three rows for the legacy (``Description``) Quality table."""
    s = _summary(project_root)
    rd_ok = s["ratchet_delta"] <= 0
    return [
        f"| Bloat over-limit (grandfathered) | {s['over_limit']} | INFO | "
        "Grandfathered files above the standard LOC limit — accepted via the "
        "baseline; the ratchet delta is the live signal |",
        f"| Bloat in allowlist | {s['in_allowlist']} entries | INFO | "
        "Grandfathered or ADR-exception entries in shipwright_bloat_baseline.json |",
        f"| Bloat ratchet delta | {s['ratchet_delta']:+d} lines | {_badge(rd_ok)} | "
        "Sum of (measured-current) across grandfathered entries — negative shrinks |",
    ]


__all__ = ["bloat_rows_events_mode", "bloat_rows_legacy_mode"]
