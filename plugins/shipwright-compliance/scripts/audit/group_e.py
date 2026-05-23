"""Group E — Compliance MD snapshot-provenance audit (plan v7 Step 7).

Replaces the pre-iterate-2026-05-23 fresh-render byte-compare. The audit
now verifies that on-disk ``.shipwright/compliance/*.md`` files match the
version committed in the last iterate-finalize commit (the snapshot,
located via ``Run-ID:`` trailer + ``.shipwright/compliance/`` diff).

Findings produced:

  * **E0 — Snapshot available** — pass: snapshot located at ``<sha>``.
  * **E0 — Snapshot unavailable** — info/skip: no qualifying commit (greenfield).
  * **E1-E5 — pass** — per-doc on-disk matches snapshot.
  * **E1-E5 — fail** — per-doc on-disk drifted from snapshot (hand-edit,
    partial regen outside iterate finalize). Fix hint:
    ``/shipwright-compliance --fix`` (which rewrites with the fresh
    state — operator then commits as a separate ``chore(compliance):``
    or rolls into the next iterate).

``--fix`` mode (config["fix"]=True): rewrite stale docs with a fresh
production render so the next snapshot commit will catch up. Same
mechanism as before — the only change is what counts as "stale".

config["fixes_applied"] (list, mutated in place) accumulates relative
paths that were rewritten, mirroring the legacy contract.
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
    "rtm": "RTM stale (regen vs snapshot)",
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
    if result.snapshot_sha:
        pieces.append(f"snapshot {result.snapshot_sha[:12]}")
    return "; ".join(pieces)


def _render_fresh_for_fix(doc_key: str, data: Any) -> str | None:
    """Lazy-import the production renderer for ``doc_key``.

    Only used in ``--fix`` mode (and only when ``data`` is available).
    The snapshot audit itself never needs to render — it just byte-
    compares against ``git show``.
    """
    try:
        from scripts.lib.change_history import generate as render_change_history
        from scripts.lib.compliance_report import generate as render_dashboard
        from scripts.lib.rtm_generator import generate as render_rtm
        from scripts.lib.sbom_generator import generate as render_sbom
        from scripts.lib.test_evidence import generate as render_test_evidence
    except ImportError:
        return None
    renderers = {
        "rtm": render_rtm,
        "test_evidence": render_test_evidence,
        "change_history": render_change_history,
        "sbom": render_sbom,
        "dashboard": render_dashboard,
    }
    render = renderers.get(doc_key)
    if render is None:
        return None
    try:
        return render(data)
    except Exception:  # noqa: BLE001 — best-effort fix path
        return None


def _apply_fix(
    project_root: Path,
    doc: audit_staleness.DocInfo,
    fresh_content: str,
) -> str | None:
    """Write ``fresh_content`` to ``project_root / doc.rel_path``."""
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

    ``data`` is now optional for the AUDIT step (snapshot byte-compare
    needs only git, not ComplianceData) but still consumed by ``--fix``
    mode to produce fresh content. ``config["fix"]`` (bool, default False)
    enables write-back; ``config["fixes_applied"]`` (list, mutated in
    place) collects relative paths that were rewritten.
    """
    cfg = config or {}
    fix_enabled = bool(cfg.get("fix", False))
    fixes_sink: list[str] | None = cfg.get("fixes_applied")
    if fix_enabled and fixes_sink is None:
        fixes_sink = []

    report = audit_staleness.check_staleness(project_root)

    out: list[Finding] = []

    if report.snapshot_unavailable:
        # Greenfield / pre-adoption: no baseline to drift against.
        out.append(Finding(
            group="E", check_id="E0", name="Snapshot baseline",
            severity="LOW", source=SOURCE_DETECTIVE_ONLY,
            status="skip",
            detail=(
                "no iterate-finalize snapshot found in git history "
                "(no commit with 'Run-ID:' trailer touching "
                f"{audit_staleness.COMPLIANCE_DIR}/) — staleness check skipped"
            ),
        ))
        return out

    # Snapshot found — emit one positive E0 finding for transparency.
    snapshot_sha_short = (report.snapshot_sha or "")[:12]
    out.append(Finding(
        group="E", check_id="E0", name="Snapshot baseline",
        severity="LOW", source=SOURCE_DETECTIVE_ONLY,
        status="pass",
        detail=f"baseline snapshot {snapshot_sha_short}",
        evidence=[report.snapshot_sha] if report.snapshot_sha else [],
    ))

    for result in report.docs:
        check_id = _CHECK_ID_BY_DOC.get(result.doc, "E?")
        name = _NAME_BY_DOC.get(result.doc, result.doc)

        if not result.stale:
            out.append(Finding(
                group="E", check_id=check_id, name=name,
                severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
                status="pass",
                detail=(
                    f"on-disk matches snapshot {snapshot_sha_short} "
                    f"({result.rel_path})"
                ),
            ))
            continue

        # Stale path. Apply --fix if enabled, else surface as a fail.
        detail = _fail_detail(result)
        if fix_enabled and data is not None:
            fresh = _render_fresh_for_fix(result.doc, data)
            if fresh is not None:
                doc = next(
                    (d for d in audit_staleness.DOC_REGISTRY if d.key == result.doc),
                    None,
                )
                if doc is not None:
                    written = _apply_fix(project_root, doc, fresh)
                    if written is not None:
                        if fixes_sink is not None:
                            fixes_sink.append(written)
                        out.append(Finding(
                            group="E", check_id=check_id, name=name,
                            severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
                            status="pass",
                            detail=(
                                f"was stale ({detail}); regenerated "
                                f"{result.rel_path}"
                            ),
                        ))
                        continue

        out.append(Finding(
            group="E", check_id=check_id, name=name,
            severity="MEDIUM", source=SOURCE_DETECTIVE_ONLY,
            status="fail",
            detail=detail,
            evidence=[result.rel_path, report.snapshot_sha or ""],
            suggested_iterate_cmd=_suggest(result.doc),
        ))

    return out
