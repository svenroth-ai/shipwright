#!/usr/bin/env python3
"""Scan coverage manifest — what this run actually looked at.

A tool that CRASHES is already surfaced: it records a ``scan_errors`` marker,
``degraded: true`` lands in ``findings.json`` and the run fails closed. A tool
that was NEVER THERE was invisible — the backend simply skipped its class, so a
machine with one scanner installed produced a report that read clean for every
class of weakness.

This module closes that hole. It derives one row per weakness class from data
the caller already holds, so no backend has to remember to populate anything:

    build_coverage(available=backend.capabilities,
                   requested=scan_types,
                   scan_errors=backend.scan_errors)

Each row is ``{"class", "tool", "status", "detail"}`` with ``status`` drawn from
the closed vocabulary :data:`COVERAGE_STATUSES`:

    covered        the class was scanned and its result can be trusted
    degraded       the tool ran but its result CANNOT be trusted — no
                   parseable output (see scan_errors), or a configured
                   ruleset known to be ineffective
    not_requested  the caller scoped this class out (``--scan-types``)
    not_available  the check could not run here — locally, the tool is not on PATH

An EMPTY manifest means "coverage was not reported", never "everything was
covered": :func:`is_complete` returns ``False`` for it, and the report renders
it as unknown rather than clean.

The manifest is also what makes a run-to-run comparison honest — see
``scan_compare``: a finding that vanished between two scans counts as resolved
only for the classes both scans actually covered.
"""

from __future__ import annotations

from typing import Any, Iterable

# A manifest read back from a caller-supplied artifact is UNTRUSTED — see
# coverage_sanitize for why, and for the boundary where it is normalized.
from coverage_sanitize import safe_text, sanitize_coverage  # noqa: F401

# Weakness class -> the local CLI tool that provides it. Classes a backend
# offers that are not in this map (Aikido's ``iac``) still get a row, with
# ``tool: None`` — an unmapped class must never be silently dropped.
SCAN_CLASS_TOOLS: dict[str, str] = {
    "sast": "semgrep",
    "sca": "trivy",
    "secrets": "gitleaks",
}

# Stable render order for the three local classes.
CLASS_ORDER: tuple[str, ...] = ("sast", "sca", "secrets")

# The prompt-injection scan is built into the plugin rather than provided by a
# third-party binary, so it can never be "not installed" — but it IS a distinct
# class of weakness that the report omits entirely when the caller did not pass
# ``--prompt-risks``. Omission reads as clean, so it gets a row too.
PROMPT_INJECTION_CLASS = "prompt_injection"

COVERAGE_STATUSES: tuple[str, ...] = (
    "covered",
    "degraded",
    "not_requested",
    "not_available",
)

# Human-readable class labels for the report.
CLASS_LABELS: dict[str, str] = {
    "sast": "Code flaws (SAST)",
    "sca": "Vulnerable dependencies (SCA)",
    "secrets": "Leaked secrets",
    "iac": "Infrastructure-as-code",
    PROMPT_INJECTION_CLASS: "Prompt injection",
}

# Normalized finding ``type`` values -> coverage class. ``secret_detection`` is
# what the gitleaks normalizer emits; ``secrets`` is the scan-type spelling.
_TYPE_TO_CLASS: dict[str, str] = {
    "sast": "sast",
    "sca": "sca",
    "secret_detection": "secrets",
    "secrets": "secrets",
    "iac": "iac",
    PROMPT_INJECTION_CLASS: PROMPT_INJECTION_CLASS,
}

# Fallback for findings that carry a scanner but no recognizable ``type``.
_SOURCE_TO_CLASS: dict[str, str] = {
    "semgrep": "sast",
    "trivy": "sca",
    "gitleaks": "secrets",
}

_TOOL_TO_CLASS: dict[str, str] = {v: k for k, v in SCAN_CLASS_TOOLS.items()}


def class_label(cls: Any) -> str:
    """Human-readable label for a coverage class.

    A known class maps to its curated label; an UNKNOWN one falls back to the raw
    id, which may have arrived in a caller-supplied manifest — so the fallback is
    flattened by ``coverage_sanitize.safe_text``. This is the single chokepoint
    feeding the report banner, the coverage table, the one-line summary and the
    triage card, so hardening it covers all four.
    """
    known = CLASS_LABELS.get(cls) if isinstance(cls, str) else None
    return known if known is not None else safe_text(cls)


def _degraded_by_class(
    scan_errors: Iterable[dict[str, Any]] | None,
    tool_to_class: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map ``class -> "reason: detail"`` for every recorded degraded leg.

    ``tool_to_class`` is inverted from the EFFECTIVE class->tool map, so a caller
    that overrides ``class_tools`` gets its degraded legs attributed with the
    same map the rest of the manifest uses — otherwise a custom map would render
    a leg's class as ``not_available`` while its error sat unmapped.
    """
    mapping = _TOOL_TO_CLASS if tool_to_class is None else tool_to_class
    out: dict[str, str] = {}
    for err in scan_errors or []:
        if not isinstance(err, dict):
            continue
        cls = mapping.get(str(err.get("scanner", "")).strip().lower())
        if cls is None:
            continue
        reason = str(err.get("reason", "unknown"))
        detail = str(err.get("detail", "")).strip()
        out[cls] = f"{reason}: {detail}"[:300] if detail else reason
    return out


def build_coverage(
    *,
    available: Iterable[str],
    requested: Iterable[str] | None = None,
    scan_errors: Iterable[dict[str, Any]] | None = None,
    class_tools: dict[str, str] | None = None,
    class_degradations: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Derive the coverage manifest for one scan.

    Args:
        available: the backend's capabilities (``{"sast", "sca", ...}``).
        requested: the caller's ``--scan-types`` filter, or ``None`` for "all".
        scan_errors: degraded-leg markers recorded by the backend.
        class_tools: class -> tool map override (defaults to the OSS map).
        class_degradations: ``class -> reason`` for a class whose tool RAN but
            whose result cannot be trusted — e.g. a project gitleaks config that
            leaves the secret scan with no effective rules. Such a class is
            forced to ``degraded``, never left ``covered`` with a footnote: a
            result that cannot be trusted is not a clean class.

    Status precedence is ``degraded`` > ``not_requested`` > ``not_available`` >
    ``covered``. ``degraded`` wins outright because a recorded marker is hard
    evidence the leg ran and failed — when a binary vanishes mid-run the
    capability re-probe comes back empty, and reporting that as "not installed"
    would lose the failure.
    """
    tools = SCAN_CLASS_TOOLS if class_tools is None else class_tools
    available_set = {str(c) for c in available}
    requested_set = None if requested is None else {str(c) for c in requested}
    degraded = _degraded_by_class(
        scan_errors, {v: k for k, v in tools.items()})
    # A configured-but-ineffective ruleset degrades the class just as a fataled
    # leg does — but ONLY a class that would otherwise be `covered`. A class the
    # caller scoped out, or whose tool is not installed, was not scanned under
    # that ruleset at all: reporting it `degraded` would state something false
    # about what happened, and `degraded` outranks both statuses so the accurate
    # one would be lost. An explicit scan_errors marker still wins, since it is
    # evidence about this specific invocation.
    for cls, reason in (class_degradations or {}).items():
        would_be_covered = cls in available_set and (
            requested_set is None or cls in requested_set)
        if would_be_covered:
            degraded.setdefault(cls, reason)

    # The three local classes first, then any extra capability a backend offers.
    classes = list(CLASS_ORDER) + sorted(available_set - set(CLASS_ORDER))

    rows: list[dict[str, Any]] = []
    for cls in classes:
        tool = tools.get(cls)
        if cls in degraded:
            status, detail = "degraded", degraded[cls]
        elif requested_set is not None and cls not in requested_set:
            status, detail = "not_requested", "excluded by the requested scan types"
        elif cls not in available_set:
            status = "not_available"
            detail = (
                f"{tool} is not installed on this machine"
                if tool
                else "not offered by the active scanner backend"
            )
        else:
            status, detail = "covered", None
        rows.append(
            {"class": cls, "tool": tool, "status": status, "detail": detail}
        )
    return rows


def with_prompt_injection_row(
    coverage: list[dict[str, Any]], *, ran: bool
) -> list[dict[str, Any]]:
    """Append the prompt-injection row unless the manifest already has one.

    ``ran`` is True when prompt-injection findings were actually merged into
    this report (``--prompt-risks``); otherwise the class was not looked at and
    says so rather than being absent.

    **A row is added only when it carries information.** On an empty manifest
    (a scan record written before the manifest existed) a ``not_requested`` row
    would convert *coverage not reported* — the honest state — into *coverage
    reported, one class outstanding*, silently asserting something about the
    classes nobody measured. A ``covered`` row is different: the prompt scan
    genuinely ran, so recording it adds knowledge rather than manufacturing it.
    """
    # Drop non-dict entries first: a `{"coverage": ["bad-row"]}` sidecar reaching
    # `.get` used to crash report generation outright, which defeated the very
    # tolerance for malformed / pre-feature artifacts this feature promises.
    rows = [r for r in coverage if isinstance(r, dict)] if isinstance(coverage, list) else []
    if not rows and not ran:
        return rows
    if any(r.get("class") == PROMPT_INJECTION_CLASS for r in rows):
        return rows
    rows.append({
        "class": PROMPT_INJECTION_CLASS,
        "tool": None,
        "status": "covered" if ran else "not_requested",
        "detail": None if ran else "the prompt-injection scan was not run for this report",
    })
    return rows


def covered_classes(coverage: Iterable[dict[str, Any]] | None) -> set[str]:
    """Classes this run actually scanned to completion."""
    return {
        str(r["class"])
        for r in (coverage or [])
        if isinstance(r, dict) and r.get("status") == "covered" and r.get("class")
    }


def unchecked_classes(coverage: Iterable[dict[str, Any]] | None) -> list[str]:
    """Classes that were never looked at, in manifest order.

    Excludes ``degraded`` — a leg that ran and failed is a different (already
    surfaced, run-failing) condition from one that was never attempted.
    """
    return [
        str(r["class"])
        for r in (coverage or [])
        if isinstance(r, dict)
        and r.get("status") in ("not_available", "not_requested")
        and r.get("class")
    ]


def is_complete(coverage: Iterable[dict[str, Any]] | None) -> bool:
    """True only when every row is ``covered``.

    An empty/absent manifest is NOT complete: "we do not know what was covered"
    must never render as a clean sweep.
    """
    rows = [r for r in (coverage or []) if isinstance(r, dict)]
    if not rows:
        return False
    return all(r.get("status") == "covered" for r in rows)


def finding_class(finding: Any) -> str | None:
    """Coverage class for a normalized finding, or ``None`` if unrecognizable.

    Reads ``type`` first (the normalized schema field) and falls back to
    ``source`` so a finding from a known scanner is still attributable.
    """
    if not isinstance(finding, dict):
        return None
    cls = _TYPE_TO_CLASS.get(str(finding.get("type", "")).strip().lower())
    if cls is not None:
        return cls
    return _SOURCE_TO_CLASS.get(str(finding.get("source", "")).strip().lower())
