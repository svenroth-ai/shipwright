"""AR-10 — ingest the CI security outcome into the compliance dashboard.

``security.yml`` (Semgrep + Trivy + Gitleaks + prompt-injection) and
``codeql.yml`` run **fail-closed in CI**, but their results were never
rendered in the dashboard, so security *looked* absent — and the Control
Grade's Security dimension stayed ``n/a``. This module ingests the CI outcome
into a **public-safe, committed** summary
(``.shipwright/compliance/ci-security.json``) and renders it, lighting the
grader's ``security_measurable`` + ``security_open_high_critical`` seam.

Design (mirrors the ``github_triage`` producer/reader split):

* The **producer** (``tools/refresh_ci_security.py``) fetches the latest
  ``security.yml`` run's ``findings.json`` over the network and calls
  :func:`summarize_ci_security` → :func:`write_ci_security`.
* This module is **PURE + offline**: it summarizes finding arrays, reads/writes
  the committed JSON, parses the ``.trivyignore.yaml`` accepted-risk register,
  and renders the dashboard section. No network here, so ``generate()`` stays
  deterministic (reads the frozen summary; expiry keyed to a passed ``now``).

**Public-safe** = counts + dates + gate verdict + accepted-CVE ids/expiry only.
Never finding detail (file paths, packages, code, secrets, exploit hints) —
:func:`summarize_ci_security` keeps only the severity buckets, and the accepted
ids already live in the committed ``.trivyignore.yaml``.

**Never a false CRITICAL** (spec handoff): a missing/degraded summary →
:func:`grade_security_signal` returns ``(False, None)`` so the dimension stays
``n/a`` rather than reading a stale/absent scan as "clean".
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

# NOTE: ``yaml`` (PyYAML) is imported LAZILY inside ``parse_accepted_risks`` —
# NOT at module top. This module is reached by a cross-plugin import chain
# (shared.contracts.iterate → compliance.update_compliance → _control_block →
# ci_security), and PyYAML is only a shipwright-compliance dependency. An eager
# import would break that chain (and CI) in plugins that don't install PyYAML,
# even though the grade/render paths used cross-plugin never touch YAML (ADR-045).

#: Tracked, public-safe summary — committed so security is visible on the
#: public repo / webui (which has no local ``securityreports/``). Single
#: canonical literal (not Path()/"compliance"/...) so the artifact-path-canon
#: AST lint sees the ``.shipwright/`` prefix.
SUMMARY_REL = Path(".shipwright/compliance/ci-security.json")
_TRIVYIGNORE_NAMES = (".trivyignore.yaml", ".trivyignore.yml")
_BUCKETS = ("critical", "high", "medium", "low")
#: Bumped if the summary shape changes (lets future readers degrade safely).
SCHEMA_VERSION = 1


def _severity_counts(findings: list[dict] | None) -> dict[str, int]:
    """Count findings into the four public severity buckets (``info`` and
    unknown severities are dropped — they never affect the gate or grade)."""
    counts = {s: 0 for s in _BUCKETS}
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity", "")).lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def summarize_ci_security(
    findings: list[dict] | None,
    prompt_risks: list[dict] | None,
    *,
    scan_date: str,
    source: str,
    degraded: bool = False,
) -> dict[str, Any]:
    """Build the public-safe summary from the CI finding arrays.

    ``findings`` = ``findings.json`` (Semgrep/Trivy/Gitleaks SAST+SCA+secrets);
    ``prompt_risks`` = ``prompt_risks.json`` (prompt-injection leg). Only
    severity counts survive — no per-finding detail (AC1, public-safe).

    ``open_high_critical`` (critical + high) is the grader seam; ``critical_gate``
    mirrors the merge-blocking CI gate (fail iff any critical).
    """
    sev = _severity_counts(findings)
    open_hc = sev["critical"] + sev["high"]
    return {
        "schema": SCHEMA_VERSION,
        "scan_date": scan_date or "",
        "source": source or "",
        "by_severity": sev,
        "total": sum(sev.values()),
        "open_high_critical": open_hc,
        "critical_gate": "fail" if sev["critical"] > 0 else "pass",
        "prompt_injection": sum(_severity_counts(prompt_risks).values()),
        "degraded": bool(degraded),
    }


def grade_security_signal(summary: dict | None) -> tuple[bool, int | None]:
    """Map a summary onto the grader's ``(security_measurable,
    security_open_high_critical)`` seam.

    Returns ``(False, None)`` — dimension stays ``n/a`` — when there is no
    summary, the scan was degraded, or the open count is not a non-negative
    int. This is the "never a false CRITICAL" guard: an absent/untrustworthy
    scan must read as *unknown*, not as *clean* (0) nor as a fabricated risk.
    """
    if not summary or summary.get("degraded"):
        return (False, None)
    ohc = summary.get("open_high_critical")
    if not isinstance(ohc, int) or isinstance(ohc, bool) or ohc < 0:
        return (False, None)
    return (True, ohc)


def load_ci_security(project_root: Path | str | None) -> dict | None:
    """Read the committed summary, or ``None`` when absent/unreadable.

    A falsy/invalid ``project_root`` (e.g. an unset ``ComplianceData.project_root``)
    yields ``None`` → Security stays n/a rather than crashing the grader."""
    if not project_root:
        return None
    path = Path(project_root) / SUMMARY_REL
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_ci_security(project_root: Path | str, summary: dict) -> Path:
    """Atomically write the summary to ``ci-security.json`` and return its path.

    Deterministic encoding (``sort_keys``) so re-running the producer with
    identical CI inputs leaves a byte-identical file (no churn)."""
    path = Path(project_root) / SUMMARY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


# The accepted-risk view moved to its own module when this file approached the
# 300-line cap, and was widened there: it now correlates the scanner-agnostic
# register (`shipwright_accepted_risks.yaml`) with the operational suppressions,
# reads the classic flat `.trivyignore` the scanner also honours, and surfaces
# the `statement` / `rationale_ref` an auditor needs. Re-exported so existing
# callers (and the grade re-export bridge) are unchanged.
from .accepted_risk_view import (  # noqa: F401
    _coerce_date,
    accepted_risk_rows,
    parse_accepted_risks,
)


def _gate_badge(summary: dict) -> str:
    return "✅ PASS" if summary.get("critical_gate") == "pass" else "❌ FAIL"


def render_ci_security(project_root: Path | str, *, now: date) -> list[str]:
    """The dashboard CI-Security section (AR-10) — scan date, the
    severity table, the critical-gate badge, the prompt-injection count, and
    the accepted-risk register. Drills down from the Control Grade's Security
    dimension. Degrades to a "not ingested" note when no summary exists."""
    lines = ["## 🛡️ CI Security (fail-closed gate)", ""]
    summary = load_ci_security(project_root)
    if summary is None:
        # Explicit `+` (not adjacent-literal concat inside the list) so the
        # CodeQL py/implicit-string-concatenation-in-list query doesn't read it
        # as a missing-comma bug.
        not_ingested = (
            "_CI security results not yet ingested. Run "
            + "`refresh_ci_security.py` (auto-run by `update_compliance.py`) "
            + "to pull the latest `security.yml` scan._"
        )
        lines.extend([not_ingested, ""])
        return lines

    scan_date = (summary.get("scan_date") or "")[:10] or "unknown"
    source = summary.get("source") or "security.yml"
    lines.append(
        f"Latest scan: **{scan_date}** · source `{source}` · "
        f"critical-gate **{_gate_badge(summary)}**")
    if summary.get("degraded"):
        lines.append("")
        lines.append("> ⚠️ Scan reported **degraded** — counts may be incomplete.")
    sev = summary.get("by_severity") or {}
    lines.extend([
        "",
        "| Severity | Count |",
        "|----------|-------|",
        *[f"| {b.capitalize()} | {int(sev.get(b, 0))} |" for b in _BUCKETS],
        "",
        f"Prompt-injection findings: **{int(summary.get('prompt_injection', 0))}**",
        "",
    ])

    accepted, degraded_note = accepted_risk_rows(project_root, now=now)
    if degraded_note:
        # Never let an unreadable register render as "nothing accepted".
        lines.extend([f"> ⚠️ Accepted-risk register: {degraded_note}", ""])
    if accepted:
        lines.extend([
            "**Accepted risks** (`shipwright_accepted_risks.yaml` register):",
            "",
            "| ID | Target | Expires | Status | Recorded under |",
            "|----|--------|---------|--------|----------------|",
        ])
        for row in accepted:
            # Status is COMPOSED, not a single winner: a suppression can be both
            # unrecorded and past due, and reporting only the first would hide
            # the other. Facts accumulate; severity orders them.
            flags = []
            if row["source"] == "unregistered":
                # Suppressed but not recorded: that is drift, not an accepted
                # risk. Rendering it as "active" would launder it into one.
                flags.append("❌ UNRECORDED — no register entry")
            if row["expired"]:
                flags.append("⚠️ EXPIRED — re-review")
            if not flags:
                flags.append(
                    "recorded (suppression not verified here)"
                    if row["source"] == "registered" else "active")
            status = " · ".join(flags)
            lines.append(
                f"| {row['id']} | {row['target'] or '—'} | "
                f"{row['expires'] or '—'} | {status} | "
                f"{row['rationale_ref'] or '—'} |")
        lines.append("")

    footer = (
        "_Ingested from CI `findings.json` (public-safe: severity counts + gate "
        + "verdict only — no finding detail). The local "
        + "`.shipwright/securityreports/` is intentionally **not** used "
        + "(stale/FP-laden). Open high/critical feed the Control Grade's Security "
        + "dimension._"
    )
    lines.extend([footer, ""])
    return lines
