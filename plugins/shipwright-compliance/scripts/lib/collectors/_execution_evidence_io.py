"""Filesystem + CLI side of the execution-evidence reader (traceability TT-EV).

Split out of ``execution_evidence.py`` (ADR-099 300-LOC cap): this owns raw-report
discovery, the index writer, and the ``uv run`` CLI. One-directional dependency
(io → core): it imports ``build_index`` from the core, never the reverse.

``refresh_index`` is the producer the ``test_links`` collector calls before it loads
evidence: it emits ``.shipwright/compliance/test-evidence-index.json`` from whatever
runner reports a run dropped, normalizing paths against ``project_root``. It is
NON-DESTRUCTIVE — no report ⇒ any existing index is left untouched (absent report is
fail-closed ``not_run`` at the consumer, never a silent wipe). A corrupt/truncated
report is skipped fail-closed rather than crashing the whole ``update_compliance``.

CARRY-FORWARD (TT5): ``generated_at`` is stamped as *now* on any present report with
NO HEAD check — a stale all-pass report re-ingests as "fresh". The emit-side owner
(TT5) MUST clear ``.shipwright/compliance/evidence/`` per run and record report
provenance; a consumer must NOT treat ``generated_at`` as proof the evidence matches
the current HEAD.
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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_json(path: Path) -> dict | None:
    """Parse a JSON report, fail-closed: a truncated/corrupt report → None (that
    runner is skipped) rather than crashing the whole compliance regen."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _write_index(out: Path, index: dict) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _index_path(project_root: Path) -> Path:
    # Segmented with `/` so the artifact-path-canon lint recognizes the canonical
    # `.shipwright/compliance` base (a standalone quoted path segment trips it).
    return Path(project_root) / ".shipwright" / "compliance" / "test-evidence-index.json"


def _existing_waivers(index_path: Path) -> list[dict] | None:
    """Read operator-authored waivers from a prior index so a machine-results refresh
    carries them forward (waivers are policy config, not run evidence)."""
    if not index_path.is_file():
        return None
    data = _read_json(index_path)
    return data.get("waivers") if isinstance(data, dict) else None


def refresh_index(project_root: Path) -> Path | None:
    """Emit the evidence index from any raw runner reports found (non-destructive).

    Returns the written path, or ``None`` when no report exists (leaving any prior
    index untouched — fail-closed at the consumer). Paths are normalized against
    ``project_root`` so absolute Vitest / per-plugin pytest ids join.
    """
    root = Path(project_root)
    reports = discover_reports(root)
    if not reports:
        return None
    junit = _read_text(reports["junit"]) if "junit" in reports else None
    playwright = _read_json(reports["playwright"]) if "playwright" in reports else None
    vitest = _read_json(reports["vitest"]) if "vitest" in reports else None
    index = build_index(
        junit=junit, playwright=playwright, vitest=vitest, root=root,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_reports=[p.relative_to(root).as_posix() for p in reports.values()],
        waivers=_existing_waivers(_index_path(root)),  # machine refresh must not drop operator waivers
    )
    return _write_index(_index_path(root), index)


def _confined(path_str: str, root: Path) -> Path:
    """Resolve ``path_str`` and REJECT any that escapes ``root`` (an absolute path
    outside the root or a ``..``-traversal) — a CLI report/out path is untrusted."""
    root_r = root.resolve()
    p = Path(path_str)
    p = (p if p.is_absolute() else root_r / p).resolve()
    try:
        p.relative_to(root_r)
    except ValueError:
        raise SystemExit(f"refusing path outside project-root: {path_str}")
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit the per-test execution-evidence index")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--junit", help="JUnit XML report path (within project-root)")
    parser.add_argument("--playwright", help="Playwright JSON report path (within project-root)")
    parser.add_argument("--vitest", help="Vitest JSON report path (within project-root)")
    parser.add_argument("--junit-base", default="", help="Subdir the JUnit runner ran in (id rebase)")
    parser.add_argument("--vitest-base", default="", help="Subdir the Vitest runner ran in (id rebase)")
    parser.add_argument("--out", help="Explicit output path (within project-root)")
    args = parser.parse_args()

    root = Path(args.project_root)
    if args.junit or args.playwright or args.vitest:
        junit = _read_text(_confined(args.junit, root)) if args.junit else None
        playwright = _read_json(_confined(args.playwright, root)) if args.playwright else None
        vitest = _read_json(_confined(args.vitest, root)) if args.vitest else None
        index = build_index(
            junit=junit, playwright=playwright, vitest=vitest, root=root,
            bases={"junit": args.junit_base, "vitest": args.vitest_base},
        )
        out = _confined(args.out, root) if args.out else _index_path(root)
        _write_index(out, index)
    else:
        out = refresh_index(root)
    print(json.dumps({"success": True, "written": str(out) if out else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
