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

**Multi-root JUnit (R1a, E-C).** ``evidence_drop.stage_reports`` stages one JUnit file
PER pytest test-root (ADR-044) as ``junit-01.xml`` .. ``junit-NN.xml``, each report's
``base`` (the dir its runner ran in, for id-rebase) recorded per-report in
``_provenance.json``. When those staged reports exist, ``discover_reports`` returns ALL
of them (not just one) and ``refresh_index`` reads EACH with its OWN base so a
cross-root id actually joins. A report file discovered under the staged convention with
no matching (or malformed) provenance entry is **rejected** — skipped, not silently
read at base="" — because a wrong base does not fail to join (safe); it can join the
WRONG id (unsafe). The legacy single-file fallback (``junit.xml`` at the conventional
or a bare repo-root/``test-results/`` location, no provenance at all) is unaffected:
base="" there, exactly as before.
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
_JUNIT_GLOB = "junit-*.xml"  # evidence_drop's multi-root staging convention (E-B)


def _first_existing(root: Path, candidates: tuple[str, ...]) -> Path | None:
    for rel in candidates:
        p = root / rel
        if p.is_file():
            return p
    return None


def _staged_junit_reports(root: Path) -> list[Path]:
    """All evidence_drop-staged ``junit-NN.xml`` reports (E-B), sorted by name."""
    d = root / ".shipwright" / "compliance" / "evidence"
    if not d.is_dir():
        return []
    return sorted(d.glob(_JUNIT_GLOB))


def discover_reports(project_root: Path) -> dict:
    """Locate raw runner reports under the conventional drop locations.

    ``found["junit"]`` is always a **list** of paths (E-C — 1+ staged reports, or a
    single legacy-fallback file); ``playwright``/``vitest`` stay single ``Path``s
    (unaffected — this repo's multi-root problem is pytest-specific, ADR-044).
    """
    root = Path(project_root)
    found: dict = {}
    staged = _staged_junit_reports(root)
    if staged:
        found["junit"] = staged
    else:
        hit = _first_existing(root, _JUNIT_CANDIDATES)
        if hit is not None:
            found["junit"] = [hit]
    for key, cands in (
        ("playwright", _PLAYWRIGHT_CANDIDATES),
        ("vitest", _VITEST_CANDIDATES),
    ):
        hit = _first_existing(root, cands)
        if hit is not None:
            found[key] = hit
    return found


def _junit_bases_from_provenance(evidence_d: Path) -> dict[str, str]:
    """``{report filename: base}`` for every staged JUnit report (E-C).

    Missing/corrupt provenance, or an entry missing ``name``/``base``, is simply
    ABSENT from the returned map — the caller then rejects (skips) that report
    rather than guessing a base for it (fail-closed: see module docstring).
    """
    prov_path = evidence_d / "_provenance.json"
    if not prov_path.is_file():
        return {}
    data = _read_json(prov_path)
    if not isinstance(data, dict):
        return {}
    entries = (data.get("reports") or {}).get("junit")
    if not isinstance(entries, list):
        return {}
    out: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict) and "name" in entry and "base" in entry:
            out[str(entry["name"])] = str(entry["base"])
    return out


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

    ``junit`` is discovered as a LIST (E-C — one or more staged pytest-root reports).
    When they came from the ``evidence_drop`` multi-report staging convention, EACH is
    parsed with its OWN base recorded in ``_provenance.json``; a staged report with no
    matching provenance entry is skipped (fail-closed — see module docstring). The
    legacy single-file fallback keeps its always-base="" behaviour, unchanged.
    """
    root = Path(project_root)
    reports = discover_reports(root)
    if not reports:
        return None
    junit_paths: list[Path] = reports.get("junit") or []
    evidence_d = root / ".shipwright" / "compliance" / "evidence"
    staged_junit_paths = _staged_junit_reports(root)
    is_staged = bool(staged_junit_paths) and junit_paths == staged_junit_paths

    junit_reports: list[tuple[str, str]] = []
    source_reports: list[str] = []
    if is_staged:
        bases = _junit_bases_from_provenance(evidence_d)
        for p in junit_paths:
            base = bases.get(p.name)
            if base is None:
                continue  # no recorded base for this staged report — reject, fail-closed
            text = _read_text(p)
            if text is not None:
                junit_reports.append((text, base))
                source_reports.append(p.relative_to(root).as_posix())
    else:
        for p in junit_paths:  # legacy single-file fallback: base="" as before
            text = _read_text(p)
            if text is not None:
                junit_reports.append((text, ""))
                source_reports.append(p.relative_to(root).as_posix())

    playwright = _read_json(reports["playwright"]) if "playwright" in reports else None
    vitest = _read_json(reports["vitest"]) if "vitest" in reports else None
    if "playwright" in reports:
        source_reports.append(reports["playwright"].relative_to(root).as_posix())
    if "vitest" in reports:
        source_reports.append(reports["vitest"].relative_to(root).as_posix())

    index = build_index(
        junit_reports=junit_reports, playwright=playwright, vitest=vitest, root=root,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_reports=source_reports,
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
