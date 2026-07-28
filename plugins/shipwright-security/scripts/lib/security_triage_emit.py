#!/usr/bin/env python3
"""Mirror security findings into the project's Triage Inbox.

Two surfaces, deliberately different in shape.

:func:`emit_findings_to_triage` writes one item per finding — the enumeration.
It carries a stable per-finding dedup key so the same finding on the same line
is one item across runs. Moved here verbatim out of ``generate_security_report``
(which sits over its bloat baseline) so that file could shrink.

:func:`emit_scan_card` writes ONE collapsed action unit per repository carrying
the per-severity split, what the scan did not check, and the scope question. The
enumeration says *what* was found; the card says *how much of each* and asks how
far to go. A card carrying only a total leaves the executing agent to decide
silently that the low-severity findings do not matter.

Best-effort: an emission failure is logged to stderr and swallowed so it can
never block the report the operator actually asked for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from security_card import build_scan_action_unit  # noqa: E402

_SECURITY_KIND_FROM_SEVERITY = {
    "critical": "bug",
    "high": "bug",
    "medium": "improvement",
    "low": "improvement",
    "info": "improvement",
}

_KNOWN_SEVERITIES = ("critical", "high", "medium", "low", "info")

# Findings re-fire daily until promoted or dismissed.
_DEDUP_WINDOW_SECONDS = 24 * 3600


def _import_triage_appender():
    """Lazily import the shared idempotent triage appender.

    Lazy so importing this module never forces ``shared/scripts`` onto
    ``sys.path`` — plugin tests run with a constrained path. Returns ``None``
    (after a stderr diagnostic) when the shared module is unreachable.
    """
    try:
        shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from triage import append_triage_item_idempotent  # noqa: PLC0415

        return append_triage_item_idempotent
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[security] triage import failed: {type(exc).__name__}: {exc}\n"
        )
        return None


def emit_findings_to_triage(
    project_root: Path,
    findings: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> int:
    """Append security findings to ``.shipwright/triage.jsonl`` (best-effort).

    One triage item per finding. ``source="security"``, severity inherited
    verbatim from the scanner (unrecognized → fallback to ``"medium"``).
    ``dedup_key=f"{tool}:{check_id}:{file}:{line}"`` makes the same finding
    on the same line stable across runs; ``match_commit=True`` with a 24h
    window lets the finding re-fire daily until promoted/dismissed.

    Returns the number of NEW items appended (duplicates are skipped). Any
    per-finding error is logged to stderr and swallowed — emission never
    blocks the consolidation path.
    """
    if not findings:
        return 0

    append_triage_item_idempotent = _import_triage_appender()
    if append_triage_item_idempotent is None:
        return 0

    appended = 0
    for f in findings:
        try:
            if not isinstance(f, dict):
                continue
            tool = str(f.get("source") or "unknown")
            check_id = str(f.get("rule") or f.get("type") or "unknown")
            affected_file = str(f.get("affected_file") or f.get("file") or "unknown")
            line_val = f.get("affected_line") or f.get("line") or "?"
            description = str(f.get("description") or "")

            if not check_id or check_id == "unknown" or affected_file == "unknown":
                # Producer cannot build a stable dedup key from this finding
                # — best-effort skip + stderr (rather than emit a useless
                # "unknown:unknown:..." key that pollutes the inbox).
                sys.stderr.write(
                    f"[security] skipping finding missing rule/file: {f!r}\n"
                )
                continue

            raw_sev = str(f.get("severity") or "").lower()
            # Conservative fallback — never raise into the consolidation path
            # (which would break the entire report). "medium" is the
            # operator-useful default.
            severity = raw_sev if raw_sev in _KNOWN_SEVERITIES else "medium"
            kind = _SECURITY_KIND_FROM_SEVERITY[severity]

            summary = description.replace("\n", " ").strip()[:80]
            title = f"[{tool}] {check_id}: {summary}" if summary else \
                    f"[{tool}] {check_id}"
            title = title[:160]

            detail_parts = [f"{affected_file}:{line_val}"]
            if description:
                detail_parts.append(description)
            suggested_fix = f.get("suggested_fix") or f.get("remediation")
            if suggested_fix:
                detail_parts.append(f"fix: {suggested_fix}")
            detail = " | ".join(detail_parts)

            evidence_path = f.get("_evidence_path") or f.get("evidence_path")

            new_id = append_triage_item_idempotent(
                project_root,
                source="security",
                severity=severity,
                kind=kind,
                title=title,
                detail=detail,
                dedup_key=f"{tool}:{check_id}:{affected_file}:{line_val}",
                evidence_path=str(evidence_path) if evidence_path else None,
                run_id=run_id,
                commit=commit,
                match_commit=True,
                window_seconds=_DEDUP_WINDOW_SECONDS,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001 — best-effort per-finding
            sys.stderr.write(
                f"[security] triage emit failed for finding "
                f"{f.get('rule', '<no-rule>') if isinstance(f, dict) else '<non-dict>'}: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def emit_scan_card(
    project_root: Path,
    findings: list[dict[str, Any]],
    *,
    coverage: list[dict[str, Any]] | None = None,
    repo: str = "unknown",
    report_path: str | None = None,
    run_id: str | None = None,
    commit: str | None = None,
) -> str | None:
    """Append the collapsed ``security-scan:{repo}`` action unit.

    Returns the new triage id, or ``None`` when there was nothing to act on, the
    appender was unreachable, or the card already exists in the window.
    """
    card = build_scan_action_unit(
        findings=findings, coverage=coverage, repo=repo, report_path=report_path,
    )
    if card is None:
        return None

    append_triage_item_idempotent = _import_triage_appender()
    if append_triage_item_idempotent is None:
        return None

    try:
        return append_triage_item_idempotent(
            project_root,
            source="security",
            severity=card["severity"],
            kind=card["kind"],
            title=card["title"],
            detail=card["detail"],
            dedup_key=card["dedup_key"],
            launch_payload=card["launch_payload"],
            run_id=run_id,
            commit=commit,
            match_commit=True,
            window_seconds=_DEDUP_WINDOW_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, never blocks the report
        sys.stderr.write(
            f"[security] scan card emit failed: {type(exc).__name__}: {exc}\n"
        )
        return None
