#!/usr/bin/env python3
"""Compare two scans — but only over the ground they both covered.

A finding present on Monday and gone on Tuesday means FIXED only if Tuesday
actually checked the same class of weakness. If gitleaks was uninstalled
between the two runs, every secret finding "disappears" and a naive diff
reports them all as resolved. That is the failure this module refuses to make,
and it is why the coverage manifest (``scan_coverage``) is worth building.

It is also the reason there is **no stored per-finding outcome**. An outcome
written into a scan record ("fixed on Tuesday") is a claim frozen at a moment
when the coverage question may not have been asked. Deriving the answer from
two sidecars on demand means the coverage gate is applied every single time, so
the comparison cannot go stale or be trusted beyond what it can prove.
:func:`compare_scans` never mutates its inputs.

Fail-closed: a sidecar with no coverage manifest (written before this feature)
makes NOTHING comparable — we cannot prove the later run covered the same
ground, so nothing is declared resolved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from coverage_sanitize import sanitize_coverage  # noqa: E402
from scan_coverage import (  # noqa: E402
    CLASS_ORDER,
    class_label,
    covered_classes,
    finding_class,
)

# Same key shape as the triage dedup key
# (``security_triage_emit.emit_findings_to_triage``) so "the same finding" means
# the same thing on both surfaces.
def fingerprint(finding: Any) -> str:
    """Stable identity for a finding: ``source:rule:file:line``.

    **Location-based, deliberately.** The line number is part of the identity,
    inherited from the triage dedup contract, so the same rule firing at a new
    line reads as one resolved plus one new rather than one persisting. That
    keeps a finding that MOVED from silently inheriting the triage state of the
    one that was there before; the cost is that ordinary edits above a finding
    churn the counts. Changing it would fork "the same finding" between this
    comparison and the inbox, which is worse.
    """
    if not isinstance(finding, dict):
        return "unknown:unknown:unknown:?"
    source = str(finding.get("source") or "unknown")
    rule = str(finding.get("rule") or finding.get("type") or "unknown")
    afile = str(finding.get("affected_file") or finding.get("file") or "unknown")
    line = finding.get("affected_line") or finding.get("line") or "?"
    return f"{source}:{rule}:{afile}:{line}"


def _findings(sidecar: Any) -> list[dict[str, Any]]:
    if not isinstance(sidecar, dict):
        return []
    raw = sidecar.get("findings")
    return [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []


def _coverage(sidecar: Any) -> list[dict[str, Any]]:
    """The sidecar's manifest, SANITIZED — the same boundary the report generator
    and the cache re-read apply. Both sidecars here are caller-selected files, and
    their class labels reach ``render_comparison``'s markdown."""
    if not isinstance(sidecar, dict):
        return []
    return sanitize_coverage(sidecar.get("coverage"))


def _classes_in(coverage: list[dict[str, Any]]) -> list[str]:
    """Every class either manifest mentions, in a stable order.

    Seeded with ``CLASS_ORDER`` so a pre-manifest sidecar still produces named
    ``not_comparable`` rows. Reporting "nothing is comparable" without saying
    WHICH classes would leave the caller to infer the list, and AC-4 asks for the
    reason per class.
    """
    seen = {str(r.get("class")) for r in coverage if r.get("class")}
    seen |= set(CLASS_ORDER)
    ordered = [c for c in CLASS_ORDER if c in seen]
    return ordered + sorted(seen - set(CLASS_ORDER))


def _summarize(finding: dict[str, Any]) -> dict[str, Any]:
    """The subset of a finding a comparison consumer needs to render a row."""
    return {
        "fingerprint": fingerprint(finding),
        "class": finding_class(finding),
        "severity": str(finding.get("severity") or "unknown"),
        "rule": str(finding.get("rule") or "unknown"),
        "affected_file": str(
            finding.get("affected_file") or finding.get("file") or "unknown"
        ),
    }


def compare_scans(previous: Any, current: Any) -> dict[str, Any]:
    """Diff two scan sidecars, gated on equal coverage.

    Returns a dict with:

    - ``comparable``      classes both scans covered — the only ground on which
                          ``resolved`` / ``new`` / ``persisting`` are computed;
    - ``not_comparable``  ``[{"class", "reason"}]`` for every other class;
    - ``resolved``        in the earlier scan, absent from the later one, on
                          comparable ground — i.e. genuinely fixed;
    - ``new`` / ``persisting`` the other two buckets, same gate;
    - ``counts``          the three bucket sizes;
    - ``unclassified``    findings whose class could not be derived (never
                          counted as resolved — an unattributable finding
                          cannot be proven covered);
    - ``coverage_known``  ``False`` when either side has no manifest.
    """
    prev_cov, curr_cov = _coverage(previous), _coverage(current)
    coverage_known = bool(prev_cov) and bool(curr_cov)

    prev_covered = covered_classes(prev_cov)
    curr_covered = covered_classes(curr_cov)
    comparable = [
        c for c in _classes_in(prev_cov + curr_cov)
        if c in prev_covered and c in curr_covered
    ]

    not_comparable: list[dict[str, str]] = []
    for cls in _classes_in(prev_cov + curr_cov):
        if cls in comparable:
            continue
        in_prev, in_curr = cls in prev_covered, cls in curr_covered
        if not in_prev and not in_curr:
            reason = (
                "neither scan reports a coverage manifest, so nothing about this "
                "class can be compared"
                if not coverage_known
                else "covered by neither scan"
            )
        elif not in_curr:
            reason = "not covered by the later scan — its findings cannot be called fixed"
        else:
            reason = "not covered by the earlier scan — its findings cannot be called new"
        not_comparable.append({"class": cls, "reason": reason})

    comparable_set = set(comparable)
    unclassified = 0
    prev_by_fp: dict[str, dict[str, Any]] = {}
    curr_by_fp: dict[str, dict[str, Any]] = {}
    for bucket, findings in ((prev_by_fp, _findings(previous)),
                             (curr_by_fp, _findings(current))):
        for f in findings:
            cls = finding_class(f)
            if cls is None:
                unclassified += 1
                continue
            if cls not in comparable_set:
                continue
            # Key by (class, fingerprint): two findings sharing source/rule/
            # location but normalized to DIFFERENT classes are different
            # findings, and matching them across classes would report a
            # cross-class pair as persisting on ground only one class covered.
            bucket[f"{cls}::{fingerprint(f)}"] = f

    resolved = [_summarize(f) for fp, f in prev_by_fp.items() if fp not in curr_by_fp]
    new = [_summarize(f) for fp, f in curr_by_fp.items() if fp not in prev_by_fp]
    persisting = [_summarize(f) for fp, f in curr_by_fp.items() if fp in prev_by_fp]

    return {
        "coverage_known": coverage_known,
        "comparable": comparable,
        "not_comparable": not_comparable,
        "resolved": resolved,
        "new": new,
        "persisting": persisting,
        "counts": {
            "resolved": len(resolved),
            "new": len(new),
            "persisting": len(persisting),
        },
        "unclassified": unclassified,
    }


def render_comparison(result: dict[str, Any]) -> list[str]:
    """Markdown lines for a comparison result (``[]`` is never returned)."""
    counts = result.get("counts", {})
    lines = [
        "## Comparison with the previous scan",
        "",
        f"- **Fixed:** {counts.get('resolved', 0)}",
        f"- **New:** {counts.get('new', 0)}",
        f"- **Still open:** {counts.get('persisting', 0)}",
        "",
    ]
    comparable = result.get("comparable") or []
    lines.append(
        f"Compared over: {', '.join(comparable)}." if comparable
        else "Compared over: **nothing** — the two scans share no covered class."
    )
    unclassified = int(result.get("unclassified") or 0)
    if unclassified:
        # Stated next to the counts, not buried: these findings are in neither
        # bucket, so the three numbers above are not the whole picture.
        lines.extend([
            "",
            f"> ⚠️ {unclassified} finding(s) could not be attributed to a class "
            "and are counted in none of the totals above — an unattributable "
            "finding cannot be proven covered, so it is never called fixed.",
        ])
    not_comparable = result.get("not_comparable") or []
    if not_comparable:
        lines.extend([
            "",
            "Not compared (the two runs did not cover the same ground):",
            "",
        ])
        for entry in not_comparable:
            lines.append(
                f"- **{class_label(entry.get('class'))}** — {entry.get('reason')}")
    if not result.get("coverage_known", False):
        lines.extend([
            "",
            "> ⚠️ One of the two scans records no coverage manifest, so no "
            "finding can be proven fixed. Re-scan to get a comparable pair.",
        ])
    lines.append("")
    return lines
