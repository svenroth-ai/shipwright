#!/usr/bin/env python3
"""Adopt traceability-baseline step (traceability TT7).

Establishes the requirement→test traceability baseline at brownfield onboarding so an
adopted repo starts *with* traceability instead of accruing the session's rot. Run after
Step E (spec written, ``Layers`` inferred by TT3) and before Step F (compliance seeding,
which — with ``test_links`` now wired into its ``adopt`` phase — emits the manifest from
the tags this step writes):

  1. scaffold the ``@FR`` tag convention into ``.claude/rules/`` (TT1 convention);
  2. run the shared backfill engine (TT6) to tag existing tests + emit its report;
  3. take a REPO-WIDE (not diff-scoped) skip/quarantine inventory (TT4 scanners);
  4. resolve ``required_layers`` ambiguity against predeclared decisions — an unattended
     run consumes P1's fixture and NEVER stalls (Spec §11-R5, binding);
  5. file the orphan/unmapped/proposal candidates + every pre-existing skip as tracked
     triage (carrying the TT6 orphan category — an ``unmapped`` test is a review
     candidate, never a stale-feature accusation);
  6. write ``.shipwright/adopt/traceability-baseline.json`` as a durable run summary.

ADR-045 (precise): the ONLY ``lib`` package that binds in THIS interpreter is
``shared/scripts/lib`` — and only lazily, when ``triage.append_triage_item_idempotent``
imports ``lib.file_lock`` at call time. The backfill engine (which imports the *same*
``shared/scripts/lib``) runs in a SUBPROCESS, and the manifest collector (which imports the
compliance ``scripts.lib``) runs in Step F's own interpreter — so no two DIFFERENT ``lib``
packages ever coexist in one interpreter, which is the collision ADR-045 forbids.

A zero-test repo backfills to an empty report → no tags, no triage, no gate (AC2).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import traceability_baseline as tb  # noqa: E402
import traceability_layers as tl  # noqa: E402
from cli_paths import unquoted_path  # noqa: E402

# plugins/shipwright-adopt/scripts/tools/<file> → parents[4] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SUMMARY_REL = ".shipwright/adopt/traceability-baseline.json"


def _run_backfill(backfill_script: Path, project_root: Path, *, dry_run: bool) -> dict:
    """Subprocess the TT6 backfill engine (shared ``lib`` — separate interpreter, ADR-045).

    ``--repo-follows-split-convention`` is deliberately NOT passed: a brownfield repo does
    NOT follow the Shipwright ``NN-``↔split convention (there ``NN-`` is Playwright/Cypress
    execution order), so ``unique_split`` stays ADVISORY — no false coverage (TT6 C2).
    Returns the parsed backfill report, or an ``error`` dict (non-fatal — the baseline
    still scaffolds + inventories). Under ``dry_run`` the report is routed to a throwaway
    temp dir (TT6 ``write_report`` is unconditional), so a preview leaves ``.shipwright/``
    on the adopted repo untouched (code L1).
    """
    import shutil
    import tempfile
    cmd = [sys.executable, str(backfill_script), "--project-root", str(project_root)]
    tmp_report_dir: str | None = None
    if dry_run:
        tmp_report_dir = tempfile.mkdtemp(prefix="tt7-backfill-dry-")
        cmd += ["--dry-run", "--report-dir", tmp_report_dir]
        report_path = Path(tmp_report_dir) / "backfill-report.json"
    else:
        report_path = project_root / ".shipwright" / "backfill" / "backfill-report.json"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not report_path.exists():
            return {"error": (proc.stderr or proc.stdout or "backfill failed").strip()[:500],
                    "summary": {"tests": 0}, "orphans": {}, "proposals": []}
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"error": f"unreadable backfill report: {exc}", "summary": {"tests": 0},
                    "orphans": {}, "proposals": []}
    finally:
        if tmp_report_dir:
            shutil.rmtree(tmp_report_dir, ignore_errors=True)


def _resolve_ambiguities(project_root: Path, split_name: str, decisions_path: Path | None,
                         *, dry_run: bool) -> tuple[list, int]:
    """Parse the adopt spec → ambiguous FRs → resolve (never stalling).

    A predeclared decision is written back into the spec's ``Layers`` cell BEFORE Step F
    (O1), so the operator's/fixture's choice — not the raw auto-inference — is what the
    collector reads. Returns ``(resolutions, cells_written)``.
    """
    spec = project_root / ".shipwright" / "planning" / split_name / "spec.md"
    if not spec.exists():
        return [], 0
    namespace = spec.parent.name
    ambiguous = tl.find_ambiguous_frs(spec.read_text(encoding="utf-8", errors="ignore"), namespace)
    resolutions = tl.resolve_layer_ambiguities(ambiguous, tl.load_decisions(decisions_path))
    written = 0 if dry_run else tl.apply_layer_decisions_to_spec(spec, resolutions)
    return resolutions, written


def _file_triage(project_root: Path, specs: list, *, dry_run: bool) -> dict:
    """Append every triage spec idempotently to the TRACKED store (ships in Step H).

    ``to_outbox=False``: the adopt baseline items must land in the Step H commit so the
    WebUI Inbox shows them from day one (not routed to the sweep-later outbox). Idempotent
    (``dedup_key`` + no recency window) so a re-adopt never duplicates.
    """
    if dry_run:
        return {"appended": 0, "would_append": len(specs), "dry_run": True}
    sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
    from triage import append_triage_item_idempotent  # noqa: PLC0415

    appended = 0
    for s in specs:
        new_id = append_triage_item_idempotent(
            project_root, source="adopt-traceability", severity=s.severity, kind=s.kind,
            title=s.title, detail=s.detail, dedup_key=s.dedup_key, fr_id=s.fr_id,
            window_seconds=None, to_outbox=False,
        )
        if new_id:
            appended += 1
    return {"appended": appended, "candidates": len(specs)}


def run(project_root: Path, *, split_name: str, decisions_path: Path | None,
        shared_root: Path, dry_run: bool) -> dict:
    templates_dir = shared_root / "templates" / "rules"
    shared_scripts = shared_root / "scripts"
    backfill_script = shared_scripts / "tools" / "backfill_test_links.py"

    scaffold = tb.scaffold_tag_convention(project_root, templates_dir, dry_run=dry_run)
    report = _run_backfill(backfill_script, project_root, dry_run=dry_run)
    inventory = tb.repo_wide_skip_inventory(project_root, shared_scripts)
    resolutions, layers_written = _resolve_ambiguities(
        project_root, split_name, decisions_path, dry_run=dry_run)

    triage_specs = tb.build_orphan_triage_items(report) + tb.build_skip_triage_items(inventory)
    triage_result = _file_triage(project_root, triage_specs, dry_run=dry_run)

    # O-C3: a failed backfill must NOT masquerade as a clean baseline. Surface it as a
    # loud top-level warning (the manifest Step F emits would be tag-empty) so the
    # operator / campaign orchestrator remediates instead of trusting a false-green.
    warnings: list[str] = []
    if report.get("error"):
        warnings.append(
            f"backfill did not complete ({report['error']}); the traceability manifest "
            "will be tag-empty — re-run once the cause is fixed.")

    summary = {
        "schema_version": 1,
        "backfill_ok": not report.get("error"),
        "warnings": warnings,
        "backfill": report.get("summary", {}),
        "backfill_error": report.get("error"),
        "tag_convention": {"written": scaffold.written, "appended": scaffold.appended,
                           "skipped_existing": scaffold.skipped_existing},
        "skip_inventory": {"count": len(inventory), "findings": inventory},
        "layer_resolutions": [
            {"key": r.key, "required_layers": r.required_layers, "provenance": r.provenance,
             "resolved_from": r.resolved_from} for r in resolutions
        ],
        "predeclared_decisions_used": sum(
            1 for r in resolutions if r.resolved_from == "predeclared_decision"),
        "layers_written_to_spec": layers_written,
        "triage": triage_result,
        "dry_run": dry_run,
    }
    if not dry_run:
        out = project_root / _SUMMARY_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["written"] = _SUMMARY_REL
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adopt traceability baseline (TT7)")
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    parser.add_argument("--split-name", default="01-adopted",
                        help="Planning split holding the adopted spec.md (default: 01-adopted)")
    parser.add_argument("--decisions", type=unquoted_path, default=None,
                        help="Predeclared adopt-ambiguity fixture (unattended runs; else defaults)")
    parser.add_argument("--shared-root", type=unquoted_path, default=None,
                        help="Path to shared/ (default: resolved relative to this file)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only: no tag writes, no triage, no summary file")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(json.dumps({"success": False, "error": f"not a directory: {project_root}"}))
        return 1
    shared_root = (args.shared_root or (_REPO_ROOT / "shared")).resolve()

    summary = run(
        project_root, split_name=args.split_name, decisions_path=args.decisions,
        shared_root=shared_root, dry_run=args.dry_run,
    )
    for w in summary.get("warnings", []):
        print(f"WARNING: {w}", file=sys.stderr)
    print(json.dumps({"success": True, **summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
