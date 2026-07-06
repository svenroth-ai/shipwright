#!/usr/bin/env python3
"""run_empirical — the empirical calibration runner (opt-in launch gate).

Drives the manifest → replay-or-refresh → grade → assert band + ordering → write
the HTML report gallery + a summary table. A **thin CLI** over the shared helpers
(``record`` / ``calibration`` / ``gallery``); the ``-m empirical`` pytest driver
calls the same helpers, so there is one code path, two entry points.

    # Offline (default): replay recorded fixtures, assert bands + ordering.
    uv run tests/empirical/run_empirical.py --out /tmp/gallery

    # Refresh (network + gh): re-record fixtures for the selected repos.
    uv run tests/empirical/run_empirical.py --refresh --repos flask,express,request

Exit: 0 = all bands + ordering hold · 1 = a band/ordering/missing-fixture failure
· 2 = usage / preflight error.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Standalone-CLI bootstrap: make the grader's core lib + the empirical helpers
# importable bare (pytest does this via conftest + rootdir; a bare `uv run` does
# not). Kept minimal + smoke-tested (test_run_empirical).
_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent.parent
for _p in (_HERE, _PLUGIN_ROOT / "scripts" / "lib", _PLUGIN_ROOT / "scripts" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import yaml  # noqa: E402

from calibration import (  # noqa: E402
    OrderingError,
    assert_band,
    assert_ordering,
    grade_from_fixture,
    result_for,
)
from gallery import SummaryRow, summary_table, write_index, write_report  # noqa: E402
from record import record_repo  # noqa: E402
from replay import FIXTURES_DIR, is_pinned_sha, replay  # noqa: E402

_MANIFEST = _HERE / "repos.yaml"
_DEFAULT_OUT = _HERE / ".gallery"


def load_manifest(path: Path = _MANIFEST) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["repos"]


def _is_calibration(entry: dict) -> bool:
    return bool(entry.get("expected_band"))


def _select(entries: list[dict], repos: str | None) -> list[dict]:
    # Case-insensitive substring match; tolerant of spaces after commas (a UI /
    # workflow input like "flask, Express" selects both).
    wanted = [t.strip().lower() for t in repos.split(",")] if repos else None
    out = []
    for e in entries:
        if wanted and not any(w and w in e["name"].lower() for w in wanted):
            continue
        out.append(e)
    return out


@dataclass
class RunReport:
    rows: list[SummaryRow] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    recorded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.missing


def _replay_fixture(entry: dict, *, cache_dir: Path) -> dict | None:
    """Replay a recorded fixture for ``entry``. None = not cached / bad SHA."""
    sha = str(entry["pinned_sha"])
    if not is_pinned_sha(sha):
        return None
    return replay(f"{entry['name']}@{sha}", cache_dir=cache_dir)


def run(
    entries: list[dict],
    *,
    refresh: bool,
    strict: bool,
    include_ci_only: bool,
    out_dir: Path,
    generated_at: str,
    cache_dir: Path = FIXTURES_DIR,
) -> RunReport:
    report = RunReport()
    results = []
    for entry in entries:
        name = entry["name"]
        ci_only = "ci-only" in (entry.get("tags") or [])
        if refresh and ci_only and not include_ci_only:
            # Intentional skip (huge/expensive → CI launch-gate job), NOT a missing
            # fixture — a partial refresh must not fail on it.
            report.skipped.append(f"{name}: ci-only (recorded by the CI gate)")
            print(f"   skip  {name}: ci-only", file=sys.stderr)
            continue
        if refresh:
            try:
                fixture, _path = record_repo(entry, cache_dir=cache_dir)
            except Exception as exc:  # one repo's fetch/record failure ≠ whole run
                report.failures.append(f"{name}: record failed: {exc}")
                print(f"   FAIL  {name}: record failed: {exc}", file=sys.stderr)
                continue
            report.recorded.append(name)
        else:
            fixture = _replay_fixture(entry, cache_dir=cache_dir)
            if fixture is None:
                # A pinned entry with no cache: FAIL in strict/CI (a green-but-empty
                # launch gate is a false pass), loud skip locally.
                msg = f"{name}: no cached fixture (run with --refresh to record)"
                (report.missing if strict else report.skipped).append(msg)
                print(f"{'MISSING' if strict else 'skip':>7}  {msg}", file=sys.stderr)
                continue
        model = grade_from_fixture(fixture)
        expected = entry.get("expected_band")
        calib = _is_calibration(entry)
        # assert_band(..., None) for an edge entry asserts only that the repo is
        # gradeable (robustness) — so the CLI gate and the `-m empirical` pytest
        # gate stay identical: an edge repo that regresses to '?' FAILS here too,
        # never a silent green 'robust'.
        try:
            assert_band(name, model, expected)
            outcome = "pass" if calib else "robust"
        except AssertionError as exc:
            outcome = "FAIL"
            report.failures.append(str(exc))
        if calib:
            results.append(result_for(name, model, entry))
        # Gallery: curated entries + any failure (size cap). Only rows whose report
        # is actually written are linked in the index (no dead 404 links).
        report_file = ""
        if calib or outcome == "FAIL":
            report_file = write_report(name, model, out_dir, generated_at=generated_at).name
        report.rows.append(SummaryRow(
            name=name, band=model.grade, expected=expected or "",
            outcome=outcome, score=model.score, report_file=report_file))

    try:
        assert_ordering(results)
    except OrderingError as exc:
        report.failures.append(str(exc))

    write_index(report.rows, out_dir, generated_at=generated_at)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_empirical", description=__doc__)
    p.add_argument("--refresh", action="store_true",
                   help="Re-record fixtures from the network (needs git + gh auth)")
    p.add_argument("--repos", default=None,
                   help="Comma-separated name substrings to select (default: all)")
    p.add_argument("--out", default=str(_DEFAULT_OUT), help="Gallery output dir")
    p.add_argument("--strict", action="store_true",
                   help="A missing fixture is a FAILURE (auto-on under CI)")
    p.add_argument("--include-ci-only", action="store_true",
                   help="Also record `ci-only` (huge/expensive) targets on --refresh")
    p.add_argument("--manifest", default=str(_MANIFEST))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    strict = args.strict or os.environ.get("CI", "").lower() in ("1", "true")
    if args.refresh:
        from fetch import preflight_network
        problems = preflight_network()
        if problems:
            for pr in problems:
                print(f"preflight: {pr}", file=sys.stderr)
            return 2
    entries = _select(load_manifest(Path(args.manifest)), args.repos)
    if not entries:
        print("run_empirical: no manifest entries selected", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = run(entries, refresh=args.refresh, strict=strict,
                 include_ci_only=args.include_ci_only, out_dir=Path(args.out),
                 generated_at=stamp)
    print("\n" + summary_table(report.rows))
    for f in report.failures:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"\ngallery: {Path(args.out) / 'index.html'}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
