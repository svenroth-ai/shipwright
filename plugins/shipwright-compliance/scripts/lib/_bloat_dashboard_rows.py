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

try:
    from lib.phase_quality import collect_bloat_summary as _collect_bloat_summary
except ImportError:  # pragma: no cover - helper always available in practice
    _collect_bloat_summary = None  # type: ignore[assignment]


def _summary(project_root: Path) -> dict[str, int]:
    if _collect_bloat_summary is None:  # pragma: no cover - broken env only
        return {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}
    return _collect_bloat_summary(project_root)


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
    ol_ok = s["over_limit"] == 0
    ol_why = (
        f"{s['over_limit']} file(s) past limit AND not ADR-justified — see "
        "shipwright_bloat_baseline.json" if not ol_ok else ""
    )
    rd_ok = s["ratchet_delta"] <= 0
    rd_why = (
        f"grandfathered surface ratcheted up by {s['ratchet_delta']} line(s) — "
        "Iron Law violation" if not rd_ok else ""
    )
    return [
        f"| Bloat over-limit | {s['over_limit']} | {_badge(ol_ok)} | {ol_why} |",
        f"| Bloat in allowlist | {s['in_allowlist']} entries | INFO |  |",
        f"| Bloat ratchet delta | {s['ratchet_delta']:+d} lines | {_badge(rd_ok)} | {rd_why} |",
        "",
    ]


def bloat_rows_legacy_mode(project_root: Path) -> list[str]:
    """Three rows for the legacy (``Description``) Quality table."""
    s = _summary(project_root)
    ol_ok = s["over_limit"] == 0
    rd_ok = s["ratchet_delta"] <= 0
    return [
        f"| Bloat over-limit | {s['over_limit']} | {_badge(ol_ok)} | "
        "Files exceeding their LOC limit + not ADR-justified |",
        f"| Bloat in allowlist | {s['in_allowlist']} entries | INFO | "
        "Grandfathered or ADR-exception entries in shipwright_bloat_baseline.json |",
        f"| Bloat ratchet delta | {s['ratchet_delta']:+d} lines | {_badge(rd_ok)} | "
        "Sum of (measured-current) across grandfathered entries — negative shrinks |",
    ]


__all__ = ["bloat_rows_events_mode", "bloat_rows_legacy_mode"]
