"""Filesystem + CLI side of the execution-evidence reader (traceability TT-EV).

Split out of ``execution_evidence.py`` to keep both modules under the 300-LOC cap
(ADR-099): the pure parse/normalize/waiver core lives there; this owns raw-report
discovery, the index writer, and the ``uv run`` CLI. One-directional dependency
(io → core): it imports ``build_index`` from the pure module, never the reverse.

``refresh_index`` is the producer the ``test_links`` collector calls before it
loads evidence: it emits ``.shipwright/compliance/test-evidence-index.json`` from
whatever runner reports a run dropped, and is NON-DESTRUCTIVE — when no report
exists it leaves any existing index untouched (an absent report is fail-closed
``not_run`` at the consumer, never a silent wipe of prior evidence).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .execution_evidence import build_index

# Conventional raw-report drop locations (relative to project_root). Finalization
# (F0.5/F5) drops a run's reporter output here; refresh_index picks it up.
_JUNIT_CANDIDATES = (".shipwright/compliance/evidence/junit.xml", "junit.xml", "test-results/junit.xml")
_PLAYWRIGHT_CANDIDATES = (".shipwright/compliance/evidence/playwright.json", "test-results.json", "playwright-report/results.json")
_VITEST_CANDIDATES = (".shipwright/compliance/evidence/vitest.json", "vitest-report.json")


def _first_existing(root: Path, candidates: tuple[str, ...]) -> Path | None:
    for rel in candidates:
        p = root / rel
        if p.is_file():
            return p
    return None


def discover_reports(project_root: Path) -> dict:
    """Locate raw runner reports under the conventional drop locations."""
    root = Path(project_root)
    found: dict = {}
    for key, cands in (
        ("junit", _JUNIT_CANDIDATES),
        ("playwright", _PLAYWRIGHT_CANDIDATES),
        ("vitest", _VITEST_CANDIDATES),
    ):
        hit = _first_existing(root, cands)
        if hit is not None:
            found[key] = hit
    return found


def _write_index(out: Path, index: dict) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _index_path(project_root: Path) -> Path:
    # Segmented with `/` so the artifact-path-canon lint recognizes the canonical
    # `.shipwright/compliance` base (a standalone quoted path segment trips it).
    return Path(project_root) / ".shipwright" / "compliance" / "test-evidence-index.json"


def refresh_index(project_root: Path) -> Path | None:
    """Emit the evidence index from any raw runner reports found (non-destructive).

    Returns the written path, or ``None`` when no report exists (leaving any prior
    index untouched — fail-closed at the consumer).
    """
    root = Path(project_root)
    reports = discover_reports(root)
    if not reports:
        return None
    junit = reports["junit"].read_text(encoding="utf-8") if "junit" in reports else None
    playwright = json.loads(reports["playwright"].read_text(encoding="utf-8")) if "playwright" in reports else None
    vitest = json.loads(reports["vitest"].read_text(encoding="utf-8")) if "vitest" in reports else None
    index = build_index(
        junit=junit, playwright=playwright, vitest=vitest,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_reports=[p.relative_to(root).as_posix() for p in reports.values()],
        waivers=_existing_waivers(_index_path(root)),  # machine refresh must not drop operator waivers
    )
    return _write_index(_index_path(root), index)


def _existing_waivers(index_path: Path) -> list[dict] | None:
    """Read operator-authored waivers from a prior index so a machine-results
    refresh carries them forward (waivers are policy config, not run evidence)."""
    if not index_path.is_file():
        return None
    try:
        return json.loads(index_path.read_text(encoding="utf-8")).get("waivers")
    except (json.JSONDecodeError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit the per-test execution-evidence index")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--junit", help="JUnit XML report path")
    parser.add_argument("--playwright", help="Playwright JSON report path")
    parser.add_argument("--vitest", help="Vitest JSON report path")
    parser.add_argument("--out", help="Explicit output path (defaults to the compliance index)")
    args = parser.parse_args()

    if args.junit or args.playwright or args.vitest:
        junit = Path(args.junit).read_text(encoding="utf-8") if args.junit else None
        playwright = json.loads(Path(args.playwright).read_text(encoding="utf-8")) if args.playwright else None
        vitest = json.loads(Path(args.vitest).read_text(encoding="utf-8")) if args.vitest else None
        index = build_index(junit=junit, playwright=playwright, vitest=vitest)
        out = Path(args.out) if args.out else _index_path(Path(args.project_root))
        _write_index(out, index)
    else:
        out = refresh_index(Path(args.project_root))
    print(json.dumps({"success": True, "written": str(out) if out else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
