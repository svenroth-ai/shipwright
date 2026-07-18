#!/usr/bin/env python3
"""Shared backfill / retrofit engine: map existing tests → FRs (traceability TT6).

Best-effort, **deterministic-first, LLM-assisted-second** (Spec §7). Enumerate
every test in a repo that has tests but few/no ``@FR`` tags, run the signal
cascade (``backfill_signals``), and emit three things:

  (i)   high-confidence ``@FR`` tag edits written **into the test files** — only
        for a deterministic, unique match (``backfill_signals`` gates this);
  (ii)  a ``backfill-report.{json,md}`` of low-confidence proposals with their
        confidences (a review list — TT7/TT8 convert it to triage);
  (iii) orphan candidates split into ``confirmed`` / ``possible`` / ``unmapped``
        (Spec §11-R4) — **never auto-deleted**; deletion is a human decision.

Idempotent: a re-run re-scans, sees the tags it wrote as existing (``honoured``),
and writes nothing new. Offline by default; the ``--use-llm`` leg only adjudicates
the residue and can never auto-write (Spec §11-R1/R4). The written tags feed the
TT1 ``test_links`` collector directly — it regenerates the manifest from them.

Shared by adopt (TT7, baseline) and the retrofit step (TT8); built once here,
standalone + testable.

Notes for callers:

* The engine EDITS test files in place (unless ``--dry-run``); run it on a
  dedicated branch / clean tree so the additive covers-comment/decorator edits
  stay trivially reviewable and revertable.
* It maps ``test → FR`` only; a requirement's ``required_layers`` (TT3) are
  consumed *downstream* by the TT1 manifest / RTM the written tags feed — the
  engine reports each test's *detected* layer, it does not gate on layers.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import backfill_scan as scan  # noqa: E402
import backfill_signals as sig  # noqa: E402
import fr_fold_map as fold  # noqa: E402
from backfill_write import apply_writes  # noqa: E402

ENGINE_VERSION = "backfill_test_links/1.0.0"
_REPORT_DIRNAME = ".shipwright/backfill"


def discover_specs(project_root: Path) -> list[Path]:
    """Find the spec.md files whose FR tables seed the mapping."""
    out: list[Path] = []
    top = project_root / ".shipwright" / "agent_docs" / "spec.md"
    if top.exists():
        out.append(top)
    planning = project_root / ".shipwright" / "planning"
    if planning.is_dir():
        for d in sorted(planning.iterdir()):
            if d.is_dir() and d.name != "iterate" and (d / "spec.md").exists():
                out.append(d / "spec.md")
    root_spec = project_root / "spec.md"
    if root_spec.exists():
        out.append(root_spec)
    return out


def _default_test_roots(project_root: Path) -> list[Path]:
    names = ("tests", "test", "__tests__", "e2e", "integration-tests", "src", "app", "packages")
    roots = [project_root / n for n in names if (project_root / n).is_dir()]
    return roots or [project_root]


def run_backfill(
    project_root: Path, *,
    spec_files: list[Path] | None = None,
    test_roots: list[Path] | None = None,
    commit_frs: dict | None = None,
    adjudicator=None,
    use_llm: bool = False,
    apply: bool = True,
    split_convention: bool = False,
) -> dict:
    """Run the full cascade over a repo and return the backfill report (pure of I/O
    except the optional tag writes gated by ``apply``)."""
    project_root = Path(project_root).resolve()
    if spec_files is None:
        spec_files = discover_specs(project_root)
    if test_roots is None:
        test_roots = _default_test_roots(project_root)

    frs: list = []
    fold_maps: list = []
    for spec in spec_files:
        text = Path(spec).read_text(encoding="utf-8", errors="ignore")
        frs.extend(scan.parse_frs(text))
        # A spec may fold fine-grained FRs into a capability FR; an existing tag on a
        # folded id still names real coverage, so the engine must resolve it rather than
        # report a false orphan and propose a redundant re-tag.
        fold_maps.append(fold.parse_fold_map(text, spec_path=str(spec)))
    fold_map = fold.merge_fold_maps(fold_maps)

    records = scan.scan_tests(test_roots, project_root)
    if commit_frs is None:
        commit_frs = scan.introducing_commit_map(
            project_root, sorted({r.rel_path for r in records}))
    ctx = sig.build_ctx(frs, commit_frs=commit_frs, adjudicator=adjudicator,
                        use_llm=use_llm, split_convention=split_convention,
                        fold_map=fold_map)

    writes: list[tuple] = []
    proposals: list[dict] = []
    orphans: dict[str, list] = {"confirmed_orphan": [], "possible_orphan": [], "unmapped": []}
    honoured: list[dict] = []

    for record in records:
        res = sig.resolve_test(record, ctx)
        if res.honoured:  # a live existing tag — carried so TT7/TT8 see prior coverage
            honoured.append({"test": record.test_id, "frs": res.honoured, "layer": record.layer})
        for cand in res.auto_write:
            writes.append((record, cand))
        if res.proposals or res.conflict:
            proposals.append({
                "test": record.test_id, "layer": record.layer,
                "conflict": res.conflict,
                "candidates": [
                    {"fr": c.fr, "confidence": round(c.confidence, 3), "signals": c.signals}
                    for c in res.proposals
                ],
            })
        for orph in res.orphans:
            cat = orph["category"]
            if cat == "unmapped":
                orphans["unmapped"].append(record.test_id)
            else:
                orphans[cat].append({"test": record.test_id, **{
                    k: v for k, v in orph.items() if k != "category"}})

    written, write_failures = (apply_writes(project_root, writes) if apply else (writes, []))

    # Canonical ordering so the machine-readable report is byte-stable across runs
    # (AC3; TT7/TT8 consume it) — no dependence on scan/apply/set iteration order.
    written = sorted(written, key=lambda rc: (rc[0].test_id, rc[1].fr))
    proposals.sort(key=lambda p: p["test"])
    honoured.sort(key=lambda h: h["test"])
    write_failures.sort(key=lambda f: (f["test"], f["fr"]))
    orphans["confirmed_orphan"].sort(key=lambda o: o["test"])
    orphans["possible_orphan"].sort(key=lambda o: o["test"])
    orphans["unmapped"].sort()

    return {
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "applied": apply,
        "summary": {
            "tests": len(records),
            "auto_written": len(written),
            "proposals": len(proposals),
            "confirmed_orphan": len(orphans["confirmed_orphan"]),
            "possible_orphan": len(orphans["possible_orphan"]),
            "unmapped": len(orphans["unmapped"]),
            "already_tagged": len(honoured),
            "write_failures": len(write_failures),
        },
        "auto_written": [
            {"test": r.test_id, "fr": c.fr, "layer": r.layer,
             "confidence": round(c.confidence, 3), "signals": c.signals}
            for r, c in written
        ],
        "proposals": proposals,
        "orphans": orphans,
        "already_tagged": honoured,
        "write_failures": write_failures,
    }


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Backfill test→FR report", "",
        f"- engine: `{report['engine_version']}`  ·  generated: {report['generated_at']}",
        f"- tests scanned: **{s['tests']}**  ·  auto-written: **{s['auto_written']}**  ·  "
        f"proposals: **{s['proposals']}**  ·  already tagged: **{s['already_tagged']}**",
        f"- orphans — confirmed: **{s['confirmed_orphan']}**  ·  possible: "
        f"**{s['possible_orphan']}**  ·  unmapped: **{s['unmapped']}**", "",
        "## Auto-written tags (deterministic, high-confidence)", "",
    ]
    if report["auto_written"]:
        lines.append("| Test | FR | Layer | Confidence | Signals |")
        lines.append("|---|---|---|---|---|")
        for w in report["auto_written"]:
            lines.append(f"| `{w['test']}` | {w['fr']} | {w['layer']} | "
                         f"{w['confidence']} | {', '.join(w['signals'])} |")
    else:
        lines.append("_none_")
    lines += ["", "## Proposals (review — NOT auto-written)", ""]
    if report["proposals"]:
        for p in report["proposals"]:
            cands = "; ".join(f"{c['fr']} ({c['confidence']}, {'/'.join(c['signals'])})"
                              for c in p["candidates"]) or "—"
            flag = " **[conflict]**" if p.get("conflict") else ""
            lines.append(f"- `{p['test']}` ({p['layer']}){flag}: {cands}")
    else:
        lines.append("_none_")
    lines += ["", "## Orphan candidates (surface only — never auto-deleted)", ""]
    orph = report["orphans"]
    for c in orph["confirmed_orphan"]:
        lines.append(f"- **confirmed** `{c['test']}` → {c.get('tagged_fr')} ({c.get('reason')})")
    for c in orph["possible_orphan"]:
        lines.append(f"- **possible** `{c['test']}` ~ {c.get('candidate_fr')} "
                     f"({c.get('reason')}, {c.get('confidence')})")
    for t in orph["unmapped"]:
        lines.append(f"- **unmapped** `{t}`")
    if not (orph["confirmed_orphan"] or orph["possible_orphan"] or orph["unmapped"]):
        lines.append("_none_")
    if report.get("write_failures"):
        lines += ["", "## Write failures (skipped — file left untouched)", ""]
        for wf in report["write_failures"]:
            lines.append(f"- `{wf['test']}` → {wf['fr']} ({wf['reason']})")
    return "\n".join(lines) + "\n"


def write_report(report: dict, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "backfill-report.json"
    md_path = report_dir / "backfill-report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill test→FR tags + manifest (traceability TT6)")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--spec-file", action="append", help="Spec.md (repeatable; else auto-discover)")
    parser.add_argument("--test-root", action="append", help="Test dir (repeatable; else auto-detect)")
    parser.add_argument("--report-dir", help=f"Where to write the report (default <root>/{_REPORT_DIRNAME})")
    parser.add_argument("--use-llm", action="store_true", help="Adjudicate the residue with GPT+Gemini (opt-in)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write tags; only produce the report")
    parser.add_argument(
        "--repo-follows-split-convention", action="store_true",
        help="Trust a bare NN- filename prefix as a Shipwright split id (auto-write a "
             "unique-split match). OFF by default: on a brownfield repo NN- is the "
             "Playwright/Cypress execution-order convention, so it stays advisory.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()

    def _resolve(p: str) -> Path:
        # A relative --spec-file / --test-root is anchored to --project-root (not
        # the CWD) so `--project-root /repo --test-root tests` behaves as expected.
        path = Path(p)
        return path if path.is_absolute() else (project_root / path)

    spec_files = [_resolve(s) for s in args.spec_file] if args.spec_file else None
    test_roots = [_resolve(t) for t in args.test_root] if args.test_root else None

    adjudicator = None
    if args.use_llm:
        from external_review_config import load_review_config, resolve_model
        from backfill_llm import build_adjudicator
        adjudicator = build_adjudicator(True, load_review_config(project_root=project_root), resolve_model)

    report = run_backfill(
        project_root, spec_files=spec_files, test_roots=test_roots,
        adjudicator=adjudicator, use_llm=args.use_llm, apply=not args.dry_run,
        split_convention=args.repo_follows_split_convention,
    )
    report_dir = Path(args.report_dir) if args.report_dir else project_root / _REPORT_DIRNAME
    json_path, md_path = write_report(report, report_dir)
    print(json.dumps({
        "success": True, "report_json": str(json_path), "report_md": str(md_path),
        "summary": report["summary"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
