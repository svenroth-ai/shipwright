"""List the requirements (FRs) that can still be split, with the code evidence behind each (atomic-frs U1).

    uv run shared/scripts/tools/fr_cluster_report.py --project-root . [--only-splittable] [--fr FR-01.03] [--json]

Groups the criteria of every FR by bound tests, touched files and wording (:mod:`lib.fr_clusters`) and prints a worklist:
splittable FRs first, biggest first. The criterion count only sorts; it never decides. ``--fr FR-xx.yy`` prints only that FR's entry (JSON: one object; an unknown id exits 2). An unreadable catalog prints "could
not read the catalog" (JSON: ``{"unparsed": true}``) instead of an empty list. Advisory: always exits 0 (an FR
with too little evidence says ``no evidence``, never a guess). Code proposes, the operator confirms every cut.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_catalog import load_catalog  # noqa: E402
from lib.fr_cluster_evidence import collect_evidence  # noqa: E402
from lib.fr_clusters import cluster_frs  # noqa: E402


def build_report(project_root: str | Path) -> list[dict]:
    """The worklist for one project: ``cluster_frs`` over its catalog and the evidence found in its test files."""
    return _report(load_catalog(project_root), project_root)


def _report(cat: dict, project_root: str | Path) -> list[dict]:
    acs = cat["acs"]
    tests, files = collect_evidence(project_root, set(acs))
    titles = cat.get("titles", {})
    out = cluster_frs(acs, tests, files)
    for r in out:
        r["title"] = titles.get(r["fr"], "")
    return out


def render(report: list[dict], only_splittable: bool = False) -> str:
    rows = [r for r in report if r["verdict"] == "yes"] if only_splittable else report
    thin = sum(r["verdict"] in ("no evidence", "partial evidence") for r in report)
    lines = [f"{sum(r['verdict'] == 'yes' for r in report)} of {len(report)} requirement(s) can still be split, {thin} with too little "
             "test evidence to say (advisory)."]
    for r in rows:
        lines.append(f"\n{r['fr']} {r.get('title', '')} - {r['ac_count']} criteria, {r['evidenced']} bound to tests: splittable = {r['verdict']}")
        lines.append(f"  {r['reason']}")
        for i, c in enumerate(r["clusters"] if r["verdict"] == "yes" else [], 1):
            lines.append(f"  group {i}: {', '.join(a.rsplit('.', 1)[1] for a in c['acs'])}")
            lines.append(f"    tests: {', '.join(c['tests'][:3])}" + (" ..." if len(c["tests"]) > 3 else ""))
            if c["files"]:
                lines.append(f"    files: {', '.join(c['files'][:3])}" + (" ..." if len(c["files"]) > 3 else ""))
            lines.append(f"    wording: {', '.join(c['vocabulary']) or '-'}")
        if r["verdict"] == "yes":
            if r["loose"]:
                lines.append(f"  loose (share nothing, not a group): {', '.join(x.rsplit('.', 1)[1] for x in r['loose'])}")
            if r["unassigned"]:
                lines.append(f"  unassigned (no evidence): {', '.join(a.rsplit('.', 1)[1] for a in r['unassigned'])}")
            lines.append("  next: name each group in one plain sentence without 'and'; the operator confirms the cut.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--only-splittable", action="store_true")
    p.add_argument("--fr", help="print only this requirement's entry (e.g. FR-01.03)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    cat = load_catalog(args.project_root)
    if cat["unparsed"]:  # no spec.md, or one this tool cannot parse: never "0 of 0 can be split"
        if args.json:
            print(json.dumps({"unparsed": True, "reason": "could not read the catalog; treat as no evidence"}))
        else:
            print("could not read the catalog (no spec.md at all, or a spec.md has text but no requirement this tool can parse): "
                  "nothing was examined. Treat as no evidence.")
        return 0
    report = _report(cat, args.project_root)
    if args.fr:
        report = [r for r in report if r["fr"] == args.fr]
        if not report:
            print(json.dumps({"fr": args.fr, "found": False}) if args.json else f"{args.fr} is not in the catalog.")
            return 2
        if args.json:
            print(json.dumps(report[0], indent=2))
            return 0
    if args.json:
        shown = [r for r in report if r["verdict"] == "yes"] if args.only_splittable else report
        print(json.dumps(shown, indent=2))
    else:
        print(render(report, args.only_splittable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
