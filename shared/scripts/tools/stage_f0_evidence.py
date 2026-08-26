#!/usr/bin/env python3
"""Stage F0's OWN retained JUnit reports as this run's compliance evidence
(iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC3).

The ONLY staging call for a run that went through F0's suite runner
(`run_test_suite.py`, AC2) — replaces the generic multi-`--junit`
`evidence_drop` invocation for that case, not adds to it (`evidence_drop.
stage_reports` clears the evidence dir first, so two staging calls in one run
would race). No pytest process runs here: every report was already produced
and retained by F0 itself; this only relocates/stages what already exists.

Refuses to stage unless the retained run is COMPLETE and GREEN:

  * every unit `discover_units` currently finds in this tree has an entry in
    the retained run's side-manifest, and vice versa (a stale retained run —
    e.g. one from before a new plugin's tests/ existed — must not silently
    stage as if it covered the live suite);
  * every entry's `outcome` is `"pass"` — a fully-reported but red run must
    never stage as complete evidence (a red root's JUnit report is real
    evidence of a FAILURE, not evidence the suite is safe to certify from);
  * every entry has a retained report.

The side-manifest itself is validated before any of that: every entry
carries `unit_id`/`outcome`/`base` (the fields `main()` indexes unguarded
past this point), unit ids are unique, and every non-null `report_path`
resolves to an existing regular file strictly beneath the run directory it
came from — a manifest whose `report_path` could point outside that
directory (a `..` segment, an absolute path) is refused rather than
trusted, the same defense-in-depth discipline this repo applies to any file
the run itself did not just write moments ago and can still name precisely.

`--run-id` / `--head-commit` are REQUIRED — no defaults. A wrong or missing
value here does not fail loud on its own; it silently degrades the F11
cross-layer gate to MISSING everywhere, because
`_layer_coverage_evidence.fresh_evidence` only trusts staged evidence when
its provenance matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2]
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

# Both via the SAME `shared/` sys.path root (`scripts` a namespace package,
# `scripts.lib`/`scripts.tools` real packages) — a SECOND root (`shared/scripts`,
# for a bare `lib`/`tools` import) is deliberately not added: this file's own
# CLI invocation (`uv run shared/scripts/tools/stage_f0_evidence.py ...`) is
# not a pytest collection, which is the only context that adds one for free.
from scripts.lib import evidence_drop  # noqa: E402
from scripts.tools.suite_retention import retention_root  # noqa: E402
from scripts.tools.suite_units import discover_units  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 2


class StageError(Exception):
    """The retained run, or its side-manifest, cannot be trusted to stage."""


def find_published_run(project_root: Path, run_id: str) -> Path | None:
    """The most-recently-published retention run recorded under ``run_id``.

    Scans by content (each `manifest.json`'s own `run_id` field), not by
    reconstructing `Retention`'s directory-naming scheme — that scheme
    includes a random per-invocation suffix specifically so this lookup
    never has to guess it.
    """
    published_root = retention_root(project_root) / "published"
    if not published_root.is_dir():
        return None
    candidates = []
    for run_dir in published_root.iterdir():
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("run_id") == run_id:
            candidates.append(run_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_and_validate_manifest(run_dir: Path) -> list[dict]:
    """Load `manifest.json` and validate it structurally. Returns the `units` list."""
    manifest_path = run_dir / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StageError(f"cannot read {manifest_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StageError(f"{manifest_path} is not valid JSON: {exc}") from exc

    units = data.get("units")
    if not isinstance(units, list):
        raise StageError(f"{manifest_path}: 'units' must be a list")

    seen_ids: set[str] = set()
    run_dir_resolved = run_dir.resolve()
    for entry in units:
        if (not isinstance(entry, dict) or "unit_id" not in entry
                or "outcome" not in entry or "base" not in entry):
            raise StageError(f"{manifest_path}: malformed unit entry: {entry!r}")
        unit_id = entry["unit_id"]
        if unit_id in seen_ids:
            raise StageError(f"{manifest_path}: duplicate unit_id {unit_id!r}")
        seen_ids.add(unit_id)
        report_path = entry.get("report_path")
        if report_path is None:
            continue
        resolved = (run_dir / report_path).resolve()
        try:
            resolved.relative_to(run_dir_resolved)
        except ValueError as exc:
            raise StageError(
                f"{manifest_path}: unit {unit_id!r}'s report_path {report_path!r} "
                f"resolves outside the run directory"
            ) from exc
        if not resolved.is_file():
            raise StageError(
                f"{manifest_path}: unit {unit_id!r}'s report_path {report_path!r} "
                f"does not exist"
            )
    return units


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", default=".", type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--head-commit", required=True)
    args = ap.parse_args(argv)
    root = args.project_root.resolve()

    run_dir = find_published_run(root, args.run_id)
    if run_dir is None:
        print(
            f"ERROR: no published F0 retention run found for run_id={args.run_id!r} "
            f"under {retention_root(root) / 'published'}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        units = load_and_validate_manifest(run_dir)
    except StageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    expected_ids = {u.id for u in discover_units(root)}
    manifest_ids = {entry["unit_id"] for entry in units}
    missing, unexpected = expected_ids - manifest_ids, manifest_ids - expected_ids
    if missing or unexpected:
        print(
            "ERROR: the retained run's unit set does not match the units "
            f"discovered in this tree right now - missing={sorted(missing)} "
            f"unexpected={sorted(unexpected)}; refusing to stage a run that "
            "does not cover the live suite.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    not_green = sorted(e["unit_id"] for e in units if e["outcome"] != "pass")
    if not_green:
        print(
            f"ERROR: the retained run is not fully green - {not_green} did not "
            "pass; refusing to stage a red run as compliance evidence.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    missing_reports = sorted(e["unit_id"] for e in units if e.get("report_path") is None)
    if missing_reports:
        print(
            f"ERROR: {missing_reports} have no retained report; refusing to "
            "stage incomplete evidence.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    junit_reports = [(e["base"], run_dir / e["report_path"]) for e in units]
    prov = evidence_drop.stage_reports(
        root, run_id=args.run_id, head_commit=args.head_commit, junit_reports=junit_reports,
    )
    print(json.dumps({
        "staged": len(prov.get("reports", {}).get("junit", [])),
        "run_id": prov.get("run_id"),
        "source_run_dir": str(run_dir),
    }, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
