"""Pure field-derivation helpers shared by the triage store's writers.

Relocated out of `shared/scripts/triage.py` (iterate-2026-08-08-triage-amend-event)
to make room under that file's bloat-baseline ceiling (it is pinned at its exact
measured size, 882 lines, in `shipwright_bloat_baseline.json` — any growth blocks
the pre-commit hook). Kept in its own, amend-agnostic module rather than folded
into `lib/triage_amend.py`: `suggest_domain_from_source` derives from `source`,
which is not an amendable field, so bundling it with amend-specific logic would
misstate the dependency (external plan review).

`triage.py` re-exports every name here via its existing PEP 562 `__getattr__`
lazy-load pattern (already used for `_FileLock`/`AUTO_RESOLVABLE_STATUSES`), so
`triage.SEVERITIES`, `triage.suggest_priority_from_severity`, etc. keep resolving
for every existing caller.

No import of `triage` — same ADR-045 reasoning as `lib/triage_delivery.py`.
"""

from __future__ import annotations

#: Triage priority — drives `suggestedPriority` + default CTA. See `triage.SEVERITIES`.
SEVERITIES = ("critical", "high", "medium", "low", "info")

#: Coarse category — drives suggested backlog domain on Promote. See `triage.KINDS`.
KINDS = ("bug", "feature", "improvement", "compliance", "maintenance")

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

PRIORITY_FROM_SEVERITY = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
    "info": "P3",
}

DEFAULT_DOMAIN = "engineering"
DOMAIN_FROM_SOURCE = {"compliance": "compliance"}


def check_optional_str(name: str, value: object) -> None:
    """Reject non-string, non-None values for camelCase optional fields.

    Iterate B0 (2026-05-21) — caught by external review (H1): producers
    that pass `fr_id=42` (or any non-string) silently wrote an integer to
    disk, breaking the JSON schema at validation time. This guard turns
    that into a producer-side ValueError so misuse fails fast.
    """
    if value is None or isinstance(value, str):
        return
    raise ValueError(
        f"{name!r} must be str or None, got {type(value).__name__}"
    )


def suggest_priority_from_severity(severity: str) -> str:
    """Pure: severity → P0..P3.

    Raises ValueError on unknown severity (forces producers to pick from
    the canonical SEVERITIES enum).
    """
    try:
        return PRIORITY_FROM_SEVERITY[severity]
    except KeyError as exc:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        ) from exc


def suggest_domain_from_source(source: str) -> str:
    """Pure: source → domain. Falls back to DEFAULT_DOMAIN for any
    source not in DOMAIN_FROM_SOURCE.
    """
    return DOMAIN_FROM_SOURCE.get(source, DEFAULT_DOMAIN)
