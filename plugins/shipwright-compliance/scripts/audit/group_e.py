"""Group E — Compliance-doc content staleness (plan v7 Step 7).

Wraps :mod:`audit_staleness` so it shows up in the detective report.
For each tracked compliance doc (RTM, test-evidence, change-history,
SBOM, dashboard) the check:

1. Regenerates the doc in memory from the current ``ComplianceData``.
2. Strips the volatile ``Generated:`` header.
3. Byte-compares against the on-disk file.

A mismatch → ``fail`` finding with the first-diff line + line-count
delta in the detail. ``--fix`` mode (threaded through run_all → run via
``config["fix"]=True``) writes the regenerated doc back to disk and
records the relative path on ``AuditReport.fixes_applied`` so the
operator sees what was rewritten.

Group E is purely detective-only. It catches *content* drift that
mtime-based Phase-Quality checks (I1-I4) can't see — a doc whose mtime
is fresh but whose body lost an FR row because someone edited spec.md
without re-running ``update_compliance.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
)
from scripts.audit import audit_staleness


_NAME_BY_DOC = {
    "rtm": "RTM stale (regen vs on-disk)",
    "test_evidence": "Test-evidence stale",
    "change_history": "Change-history stale",
    "sbom": "SBOM stale",
    "dashboard": "Dashboard stale",
}

_CHECK_ID_BY_DOC = {
    "rtm": "E1",
    "test_evidence": "E2",
    "change_history": "E3",
    "sbom": "E4",
    "dashboard": "E5",
}


def _suggest(doc_key: str) -> str:
    return (
        "/shipwright-compliance --fix "
        f"# regenerates {doc_key} (Group E)"
    )


def _fail_detail(result: audit_staleness.DocStalenessResult) -> str:
    """Render a one-line detail string from a stale result."""
    if result.error:
        return result.error
    if not result.exists:
        return f"on-disk file missing: {result.rel_path}"
    pieces: list[str] = []
    if result.first_diff_line is not None:
        pieces.append(f"first diff at line {result.first_diff_line}")
    if result.line_delta:
        sign = "+" if result.line_delta > 0 else ""
        pieces.append(f"line delta {sign}{result.line_delta}")
    if not pieces:
        pieces.append("byte-compare differs after header strip")
    return "; ".join(pieces)


def _apply_fix(
    project_root: Path,
    doc: audit_staleness.DocInfo,
    fresh_content: str,
) -> str | None:
    """Write ``fresh_content`` to ``project_root / doc.rel_path``.

    Returns the relative path on success, or ``None`` on write failure
    (which surfaces as the original stale finding — the operator still
    needs to know about the staleness, just without the auto-fix).
    """
    target = project_root / doc.rel_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fresh_content, encoding="utf-8")
    except OSError:
        return None
    return doc.rel_path


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    data: Any,
) -> list[Finding]:
    """Run Group E and return Findings.

    Reads ``config["fix"]`` (bool, default False) to decide whether to
    rewrite stale docs. Reads ``config["fixes_applied"]`` (list, mutated
    in place) so the detector's report can surface what was rewritten.
    """
    cfg = config or {}
    fix_enabled = bool(cfg.get("fix", False))
    fixes_sink: list[str] | None = cfg.get("fixes_applied")
    if fix_enabled and fixes_sink is None:
        # The detector should always supply this when --fix is on; defend
        # against direct callers that forget so the auto-fix still runs.
        fixes_sink = []

    if data is None:
        # Group E needs ComplianceData to render; without it we cannot
        # decide stale-vs-fresh. Skip explicitly so the operator sees
        # WHY the check did nothing.
        return [Finding(
            group="E", check_id="E0", name="Group E ran",
            severity="LOW", source=SOURCE_DETECTIVE_ONLY, status="skip",
            detail="no ComplianceData available — collector returned None",
        )]

    try:
        renderers = audit_staleness.default_renderers()
    except ImportError as exc:
        # Plugin install gap — surface as a single high-severity skip
        # instead of crashing the whole audit run.
        return [Finding(
            group="E", check_id="E0", name="Group E ran",
            severity="HIGH", source=SOURCE_DETECTIVE_ONLY, status="fail",
            detail=f"renderer import failed: {type(exc).__name__}: {exc}",
        )]

    out: list[Finding] = []
    for doc in audit_staleness.DOC_REGISTRY:
        check_id = _CHECK_ID_BY_DOC[doc.key]
        name = _NAME_BY_DOC[doc.key]
        render = renderers.get(doc.key)
        if render is None:
            out.append(Finding(
                group="E", check_id=check_id, name=name,
                severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
                status="skip",
                detail="no renderer registered for this doc",
            ))
            continue

        try:
            fresh = render(data)
        except Exception as exc:  # noqa: BLE001 — convert to finding
            out.append(Finding(
                group="E", check_id=check_id, name=name,
                severity="HIGH", source=SOURCE_DETECTIVE_ONLY,
                status="fail",
                detail=f"render failed: {type(exc).__name__}: {exc}",
                suggested_iterate_cmd=_suggest(doc.key),
            ))
            continue

        result = audit_staleness.compare_doc(project_root, doc, fresh)
        if not result.stale:
            out.append(Finding(
                group="E", check_id=check_id, name=name,
                severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
                status="pass",
                detail=f"on-disk matches fresh regeneration ({doc.rel_path})",
            ))
            continue

        # Stale path. Apply --fix if enabled, else surface as a fail.
        detail = _fail_detail(result)
        if fix_enabled:
            written = _apply_fix(project_root, doc, fresh)
            if written is not None:
                if fixes_sink is not None:
                    fixes_sink.append(written)
                out.append(Finding(
                    group="E", check_id=check_id, name=name,
                    severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
                    status="pass",
                    detail=(
                        f"was stale ({detail}); regenerated {doc.rel_path}"
                    ),
                ))
                continue

        out.append(Finding(
            group="E", check_id=check_id, name=name,
            severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
            status="fail",
            detail=detail,
            evidence=[doc.rel_path],
            suggested_iterate_cmd=_suggest(doc.key),
        ))
    return out
