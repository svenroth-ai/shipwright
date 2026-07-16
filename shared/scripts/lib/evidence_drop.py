"""Execution-evidence emit-side (traceability TT5 carry-forward from TT-EV).

The cross-layer F11 gate is only as good as the evidence it reads: without a run's real
runner reports dropped where ``refresh_index`` (TT-EV) looks, every required layer reads
``not_run`` and the gate MISSES everything. This module is the producer half — it stages
a run's JUnit / Playwright / Vitest reports into the conventional
``.shipwright/compliance/evidence/`` drop locations, **clearing the dir first** so a prior
run's stale report can never re-ingest as this run's evidence, and records **provenance**
(run_id + head commit + per-report mtime) so a consumer never has to treat the index's
``generated_at`` as proof the evidence matches HEAD (TT-EV explicitly warned that it is not).

Freshness contract (consumer side, :func:`evidence_is_fresh`): evidence is trusted only
when a provenance sidecar exists AND its ``run_id`` equals the current run's — a fail-closed
guard. No provenance (or a mismatched run_id) ⇒ the gate loads EMPTY evidence ⇒ every layer
is MISSING ⇒ the gate blocks rather than crediting a stale pass.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

_EVIDENCE_DIR = (".shipwright", "compliance", "evidence")  # artifact-path-canon: legacy
_PROVENANCE_NAME = "_provenance.json"
# Conventional drop filenames refresh_index discovers (mirrors _execution_evidence_io).
REPORT_NAMES: dict[str, str] = {
    "junit": "junit.xml",
    "playwright": "playwright.json",
    "vitest": "vitest.json",
}


def evidence_dir(project_root: Path) -> Path:
    return Path(project_root).joinpath(*_EVIDENCE_DIR)


def _provenance_path(project_root: Path) -> Path:
    return evidence_dir(project_root) / _PROVENANCE_NAME


def _index_path(project_root: Path) -> Path:
    # The normalized per-test evidence index refresh_index emits (sibling of evidence/).
    return evidence_dir(project_root).parent / "test-evidence-index.json"


def clear_evidence_reports(project_root: Path) -> None:
    """Remove the runner reports, the provenance sidecar, AND the normalized evidence index
    before a run.

    Clearing the reports alone is not enough (external-review MUST-FIX): the gate consumes
    the SEPARATELY-persisted ``test-evidence-index.json``, so a stale index from a prior run
    could be trusted while a fresh provenance sidecar sits beside it. Deleting the index too
    means that if ``refresh_index`` does not run (or fails) this run, the consumer loads
    EMPTY evidence (fail-closed → MISSING), never a prior run's passes. Missing files ignored.
    """
    d = evidence_dir(project_root)
    for target in [d / name for name in list(REPORT_NAMES.values()) + [_PROVENANCE_NAME]] + [
        _index_path(project_root)
    ]:
        try:
            if target.is_file():
                target.unlink()
        except OSError:
            pass


def stage_reports(
    project_root: Path,
    *,
    run_id: str,
    head_commit: str = "",
    junit: Path | str | None = None,
    playwright: Path | str | None = None,
    vitest: Path | str | None = None,
) -> dict:
    """Clear the evidence dir, copy each provided report to its conventional name, and
    write the provenance sidecar. Returns the provenance dict.

    A source path that does not exist is skipped (never fabricates evidence). ``run_id``
    is the freshness key the gate checks; ``head_commit`` + per-report mtime are recorded
    for audit (a report older than the run is visible in the sidecar).
    """
    d = evidence_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    clear_evidence_reports(project_root)

    staged: dict[str, dict] = {}
    for key, src in (("junit", junit), ("playwright", playwright), ("vitest", vitest)):
        if src is None:
            continue
        src_path = Path(src)
        if not src_path.is_file():
            continue
        dest = d / REPORT_NAMES[key]
        try:
            shutil.copyfile(src_path, dest)
        except OSError:
            continue
        staged[key] = {
            "name": REPORT_NAMES[key],
            "mtime": datetime.fromtimestamp(
                dest.stat().st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    provenance = {
        "run_id": run_id,
        "head_commit": head_commit,
        "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reports": staged,
    }
    _provenance_path(project_root).write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return provenance


def read_provenance(project_root: Path) -> dict | None:
    path = _provenance_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def evidence_is_fresh(project_root: Path, run_id: str) -> bool:
    """True iff provenance exists, its ``run_id`` matches, and a report was staged.

    Fail-closed: a missing sidecar, a run_id mismatch (a prior run's evidence), or a
    sidecar with no staged reports all read as NOT fresh ⇒ the gate uses empty evidence.
    """
    prov = read_provenance(project_root)
    if not prov or not run_id:
        return False
    return str(prov.get("run_id", "")) == run_id and bool(prov.get("reports"))


def main(argv: list[str] | None = None) -> int:
    """CLI so the iterate F0.5/F5 lifecycle can drive the emit-side without embedding it
    in (and ratcheting) the grandfathered ``surface_verification.py``. ``clear`` empties
    the evidence dir before a run; ``stage`` drops this run's reports + provenance after.

        uv run shared/scripts/lib/evidence_drop.py clear   --project-root .
        uv run shared/scripts/lib/evidence_drop.py stage --project-root . \\
            --run-id iterate-2026-07-15-foo --head-commit "$(git rev-parse HEAD)" \\
            --junit junit.xml --playwright test-results.json --vitest vitest-report.json
    """
    import argparse  # noqa: PLC0415 — CLI-only

    parser = argparse.ArgumentParser(description="Execution-evidence emit-side (TT5)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clear", help="Clear staged reports + provenance before a run")
    c.add_argument("--project-root", required=True)
    s = sub.add_parser("stage", help="Stage this run's reports + provenance after a run")
    s.add_argument("--project-root", required=True)
    s.add_argument("--run-id", required=True)
    s.add_argument("--head-commit", default="")
    s.add_argument("--junit", default=None)
    s.add_argument("--playwright", default=None)
    s.add_argument("--vitest", default=None)
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if args.cmd == "clear":
        clear_evidence_reports(root)
        print(json.dumps({"cleared": str(evidence_dir(root))}))
        return 0
    prov = stage_reports(
        root, run_id=args.run_id, head_commit=args.head_commit,
        junit=args.junit, playwright=args.playwright, vitest=args.vitest,
    )
    print(json.dumps({"staged": sorted(prov.get("reports", {})), "run_id": prov.get("run_id")}))
    return 0


__all__ = [
    "REPORT_NAMES",
    "evidence_dir",
    "clear_evidence_reports",
    "stage_reports",
    "read_provenance",
    "evidence_is_fresh",
]


if __name__ == "__main__":
    raise SystemExit(main())
