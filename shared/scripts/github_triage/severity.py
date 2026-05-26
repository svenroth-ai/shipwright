"""Severity helpers + per-feed severity extractors.

Internal helpers used by ``producer.py`` mappers. Not part of the public
``github_triage`` import surface — only ``triage_severity`` is re-exported
(producer.py re-exports it; ``__init__.py`` then re-exports it from there).

The three feed-specific severity extractors live here because the shape
of each feed's payload is a producer-side concern (rule.severity_level,
security_advisory.severity, top-level severity string), and the mappers
in producer.py compose them with breakdown / max-severity helpers.
"""

from __future__ import annotations

from triage import SEVERITY_RANK

# GitHub severity vocab -> canonical triage severity. `error/warning/note`
# are code-scanning `rule.severity` levels; the rest are the GHAS
# `security_severity_level` / advisory `severity` vocab.
_GH_SEVERITY_TO_TRIAGE = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "error": "high",
    "warning": "medium",
    "note": "low",
}


def triage_severity(gh_value: str | None) -> str:
    """Map a GitHub severity token to a canonical triage severity.

    Unknown / missing values fall back to ``medium`` — a finding is never
    dropped for an unrecognised severity.
    """
    return _GH_SEVERITY_TO_TRIAGE.get((gh_value or "").lower(), "medium")


def kind_for(severity: str) -> str:
    """critical/high findings are bugs; lower severities are improvements."""
    return "bug" if severity in ("critical", "high") else "improvement"


def max_severity(severities: list[str]) -> str:
    """Pick the most severe of a list (lowest SEVERITY_RANK wins).

    Returns ``"medium"`` for an empty list — a defensive default so an
    accidentally-empty caller never gets a crash.
    """
    if not severities:
        return "medium"
    return min(severities, key=lambda s: SEVERITY_RANK.get(s, 99))


def severity_breakdown(alerts: list[dict], extract_severity) -> dict[str, int]:
    """Count alerts per canonical triage severity.

    ``extract_severity`` is per-feed (code-scanning reads
    ``rule.security_severity_level``; dependabot reads
    ``security_advisory.severity``).
    """
    counts: dict[str, int] = {s: 0 for s in ("critical", "high", "medium", "low")}
    for alert in alerts:
        sev = triage_severity(extract_severity(alert))
        if sev in counts:
            counts[sev] += 1
        else:
            counts["medium"] += 1
    return counts


def cs_extract_severity(alert: dict) -> str | None:
    rule = alert.get("rule") or {}
    return rule.get("security_severity_level") or rule.get("severity")


def db_extract_severity(alert: dict) -> str | None:
    return (alert.get("security_advisory") or {}).get("severity")


def artifact_extract_severity(finding: dict) -> str | None:
    """Severity extractor for shipwright-security ``findings.json`` entries.

    The artifact's ``findings[].severity`` is a top-level lowercase string
    (``"critical"`` / ``"high"`` / etc.) — flat, unlike cs_alerts' nested
    ``rule.security_severity_level`` and db_alerts' ``security_advisory.severity``.

    Iterate C openai-9: derive truth from the list, never from the
    redundant ``by_severity`` aggregate.
    """
    return finding.get("severity")


def format_breakdown(counts: dict[str, int]) -> str:
    """Render a severity breakdown as a stable, comma-separated string.

    Always iterates in fixed severity order (critical → low) so the same
    counts produce byte-identical output. Empty severities are omitted to
    keep the line concise; the total is always present in the caller.
    """
    parts = [f"{n} {sev}" for sev, n in counts.items() if n > 0]
    return ", ".join(parts) if parts else "0"


def security_url(owner_repo: str) -> str:
    return f"https://github.com/{owner_repo}/security"


def secret_scanning_url(owner_repo: str) -> str:
    return f"https://github.com/{owner_repo}/security/secret-scanning"


def workflow_page_url(owner_repo: str, workflow_id) -> str:
    return f"https://github.com/{owner_repo}/actions/workflows/{workflow_id}"
