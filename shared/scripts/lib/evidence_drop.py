"""Execution-evidence emit-side (traceability TT5 carry-forward from TT-EV).

The cross-layer F11 gate is only as good as the evidence it reads: without a run's real
runner reports dropped where ``refresh_index`` (TT-EV) looks, every required layer reads
``not_run`` and the gate MISSES everything. This module is the producer half — it stages
a run's JUnit / Playwright / Vitest reports into the conventional
``.shipwright/compliance/evidence/`` drop locations, **clearing the dir first** so a prior
run's stale report can never re-ingest as this run's evidence, and records **provenance**
(run_id + head commit + per-report mtime) so a consumer never has to treat the index's
``generated_at`` as proof the evidence matches HEAD.

Freshness contract (consumer side, :func:`evidence_is_fresh`): trusted only when a
provenance sidecar exists AND its ``run_id`` equals the current run's — fail-closed; no
provenance (or a mismatched run_id) ⇒ empty evidence ⇒ every layer MISSING.

**Multi-root JUnit staging (R1a, E-B).** 18 pytest test-roots (ADR-044: one process per
root) means one process can never emit a single ``junit.xml`` spanning all of them.
``stage_reports``/the CLI accept **repeated** ``--junit <base>=<path>`` so every root's
report is staged **byte-identical** (E-A) as ``junit-01.xml`` ... ``junit-NN.xml``, each
report's ``base`` recorded per-report in ``_provenance.json``. The bare single-report form
(base = project root ``""``) stays valid ONLY when sole; a bare path among 2+ is REJECTED.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVIDENCE_DIR = (".shipwright", "compliance", "evidence")  # artifact-path-canon: legacy
_PROVENANCE_NAME = "_provenance.json"
# Conventional single-file drop names refresh_index discovers (mirrors
# _execution_evidence_io). JUnit is NOT single-file any more (E-B) — it is staged as
# junit-01.xml .. junit-NN.xml, discovered via the JUNIT_GLOB pattern below.
REPORT_NAMES: dict[str, str] = {
    "playwright": "playwright.json",
    "vitest": "vitest.json",
}
JUNIT_GLOB = "junit-*.xml"


def _junit_report_name(index: int) -> str:
    return f"junit-{index:02d}.xml"


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

    Reports alone is not enough: the gate also reads the SEPARATELY-persisted
    ``test-evidence-index.json``, so a stale index could be trusted beside a fresh
    provenance sidecar. A removal that FAILS is fatal, not swallowed — an old
    report/index left in place is a false-green vector. Absent is a no-op; only a
    real ``OSError`` propagates.

    Every ``junit-*.xml`` is swept via the glob (E-B), plus the PRE-E-B single-file
    name (``evidence/junit.xml``) — left in place, the legacy fallback would read it
    as current once a fresh multi-root run produced zero staged reports.
    """
    d = evidence_dir(project_root)
    targets = [d / name for name in [*REPORT_NAMES.values(), "junit.xml", _PROVENANCE_NAME]]
    targets += sorted(d.glob(JUNIT_GLOB))
    targets.append(_index_path(project_root))
    for target in targets:
        if target.is_file():
            target.unlink()  # raise on failure — a stale artifact must never survive a clear


def stage_reports(
    project_root: Path,
    *,
    run_id: str,
    head_commit: str = "",
    junit: Path | str | None = None,
    junit_reports: list[tuple[str, Path | str]] | None = None,
    playwright: Path | str | None = None,
    vitest: Path | str | None = None,
) -> dict:
    """Clear the evidence dir, copy each provided report to its conventional name, and
    write the provenance sidecar. Returns the provenance dict.

    A source path that does not exist is skipped (never fabricates evidence) — correct
    HERE, a library call already scoped to reports the caller confirmed exist; the CLI
    (:func:`main`) additionally hard-validates every NAMED source first, since a
    human-typed typo is not a legitimate skip (Stage-3 review). ``run_id`` is the
    freshness key the gate checks; ``head_commit`` + per-report mtime are recorded.

    ``junit`` is the legacy single-report form (base = project root, ``""``).
    ``junit_reports`` (E-B) is the multi-root form: an ordered ``[(base, path), ...]``
    list, staged **byte-identical** (E-A) as ``junit-01.xml`` .. ``junit-NN.xml``
    (numbering only the ones that exist). When both are given, ``junit`` is prepended
    as an additional entry with base ``""``.
    """
    d = evidence_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    clear_evidence_reports(project_root)

    staged: dict[str, object] = {}

    junit_sources: list[tuple[str, Path]] = []
    if junit is not None:
        junit_sources.append(("", Path(junit)))
    for base, src in junit_reports or []:
        junit_sources.append((str(base), Path(src)))

    junit_entries: list[dict] = []
    index = 0
    for base, src_path in junit_sources:
        if not src_path.is_file():
            continue  # never fabricates evidence for a report that does not exist
        index += 1
        name = _junit_report_name(index)
        dest = d / name
        shutil.copyfile(src_path, dest)  # raise on failure — provenance must not claim an unstaged report
        junit_entries.append({
            "name": name,
            "base": base,
            "mtime": datetime.fromtimestamp(
                dest.stat().st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    if junit_entries:
        staged["junit"] = junit_entries

    for key, src in (("playwright", playwright), ("vitest", vitest)):
        if src is None:
            continue
        src_path = Path(src)
        if not src_path.is_file():
            continue
        dest = d / REPORT_NAMES[key]
        shutil.copyfile(src_path, dest)  # raise on failure — provenance must not claim an unstaged report
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


def _parse_junit_args(values: list[str]) -> list[tuple[str, str]]:
    """Parse repeated ``--junit`` CLI values into ``[(base, path), ...]`` (E-B/E-C).

    Each value is either ``<path>`` (bare — legacy single-report form, base = project
    root ``""``) or ``<base>=<path>`` (E-B repeatable multi-root form). Bare is ONLY
    accepted when it is the SOLE ``--junit``; with 2+, every value needs an explicit
    ``base=`` (empty base spelled ``=<path>``) — a bare path among 2+ is REJECTED, not
    silently defaulted (AC: "ein Report ohne Basis wird abgelehnt").

    A **duplicate base is legal and common** — this repo alone has FOUR roots that all
    rebase at base ``""`` (Stage-2 review: rejecting a repeated base broke the workflow
    E-B exists for, and disagreed with the ``stage_reports`` API, which never rejected
    it). Staged entries are an ORDERED LIST — nothing is keyed by base, so nothing
    silently overwrites a same-base sibling. What IS rejected: an exact duplicate
    ``(base, path)`` pair, or the same source ``path`` twice — both a copy-paste mistake.
    """
    if not values:
        return []
    if len(values) == 1 and "=" not in values[0]:
        return [("", values[0])]
    parsed: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    for raw in values:
        if "=" not in raw:
            raise SystemExit(
                f"--junit {raw!r}: a base is required once more than one --junit is given "
                "(use --junit <base>=<path>; an explicit empty base is --junit =<path>)"
            )
        base, _, path = raw.partition("=")
        if (base, path) in seen_pairs:
            raise SystemExit(f"--junit: duplicate --junit {base!r}={path!r} given twice")
        if path in seen_paths:
            raise SystemExit(f"--junit: the same source path {path!r} was given more than once")
        seen_pairs.add((base, path))
        seen_paths.add(path)
        parsed.append((base, path))
    return parsed


def _missing_named_sources(
    junit_reports: list[tuple[str, str]], playwright: str | None, vitest: str | None
) -> list[str]:
    """Every NAMED ``--junit``/``--playwright``/``--vitest`` source that does not exist.

    ``stage_reports`` itself skips a missing source silently — right for a
    programmatic caller like ``run_full_suite_evidence.stage_all``, which already
    filtered to roots it KNOWS produced a report. The CLI is different: every path
    here was NAMED BY A HUMAN, so missing means typo, not a legitimate skip —
    Stage-3 review found the CLI staged nothing and exited 0 on a typo (same bug
    class already fixed for ``--head-commit`` defaulting to empty).
    """
    missing = [path for _, path in junit_reports if not Path(path).is_file()]
    for src in (playwright, vitest):
        if src is not None and not Path(src).is_file():
            missing.append(src)
    return missing


def main(argv: list[str] | None = None) -> int:
    """CLI so the iterate F0.5/F5 lifecycle can drive the emit-side without embedding it
    in (and ratcheting) the grandfathered ``surface_verification.py``. ``clear`` empties
    the evidence dir before a run; ``stage`` drops this run's reports + provenance after.

        uv run shared/scripts/lib/evidence_drop.py clear --project-root .
        # single report (legacy form, base = project root):
        uv run shared/scripts/lib/evidence_drop.py stage --project-root . --run-id foo \\
            --head-commit "$(git rev-parse HEAD)" --junit junit.xml
        # N reports, one per pytest test-root (E-B — repeatable, base required per flag):
        uv run shared/scripts/lib/evidence_drop.py stage --project-root . --run-id foo \\
            --head-commit "$(git rev-parse HEAD)" --junit =shared-tests.xml \\
            --junit plugins/shipwright-compliance=compliance-tests.xml
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
    s.add_argument(
        "--junit", action="append", default=[],
        help="<path> (single-report, base=project root) or <base>=<path> (repeatable)",
    )
    s.add_argument("--playwright", default=None)
    s.add_argument("--vitest", default=None)
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if args.cmd == "clear":
        clear_evidence_reports(root)
        print(json.dumps({"cleared": str(evidence_dir(root))}))
        return 0
    junit_reports = _parse_junit_args(args.junit)
    missing = _missing_named_sources(junit_reports, args.playwright, args.vitest)
    if missing:
        for path in missing:
            print(f"ERROR: --junit/--playwright/--vitest source not found: {path!r}", file=sys.stderr)
        print("ERROR: stage aborted — a named source that does not exist is a typo, "
              "never a silent skip. Nothing was staged.", file=sys.stderr)
        return 1
    prov = stage_reports(
        root, run_id=args.run_id, head_commit=args.head_commit,
        junit_reports=junit_reports, playwright=args.playwright, vitest=args.vitest,
    )
    print(json.dumps({"staged": sorted(prov.get("reports", {})), "run_id": prov.get("run_id")}))
    return 0


__all__ = [
    "REPORT_NAMES",
    "JUNIT_GLOB",
    "evidence_dir",
    "clear_evidence_reports",
    "stage_reports",
    "read_provenance",
    "evidence_is_fresh",
]


if __name__ == "__main__":
    raise SystemExit(main())
