#!/usr/bin/env python3
"""BL0b analyses over the 100 replayed PRs, written under ``phaseA.*`` of the BL0B JSON (measurement only).

    bl0b_analyze.py paths   --repo .                                   # item 3: path-ownership baseline
    bl0b_analyze.py headmap --repo . --tree T --runs R                 # items 2 + 4: HEAD run mapped to history, new-code classes
    bl0b_analyze.py ac      --repo . [--tree T --runs R]               # item 5: the same touched sets at AC granularity

``--out`` defaults to the BL0B JSON beside the REPLAY report; the PR list and the git leg come from the REPLAY JSON
(``--replay``). Every number the report cites is recomputable from the keys written here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verifiers._baseline_touch_git import GitRev  # noqa: E402

CAMPAIGNS = ".shipwright/planning/campaigns/"
REPLAY = CAMPAIGNS + "2026-10-27-baseline-protection-REPLAY.json"
OUT = CAMPAIGNS + "2026-10-27-baseline-protection-BL0B.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


def _write(path: Path, text: str) -> None:
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def _put(out: Path, key: str, value) -> None:
    data = _load(out)
    data.setdefault("phaseA", {})[key] = value
    _save(out, data)


def _revs(repo: Path, replay: dict):
    for rec in replay["records"]:
        if rec.get("merge") and not rec.get("error"):
            yield rec, GitRev(repo, f"{rec['merge']}^", rec["merge"])


def cmd_paths(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers._baseline_b_paths import import_owners, path_frs, plugin_owners

    spec = (repo / ".shipwright/planning/01-adopted/spec.md").read_text(encoding="utf-8")
    owners = plugin_owners(spec)
    reach = import_owners(repo, owners)
    per_pr = {}
    for rec, rev in _revs(repo, replay):
        per_pr[str(rec["pr"])] = {fr: sorted(set(files))[:5] for fr, files in path_frs(rev.changed(), owners, reach).items()}
    _put(out, "paths", {"owners": owners, "shared_stems": len(reach), "shared_stems_with_importer": sum(1 for v in reach.values() if v),
                        "per_pr": per_pr, "tree": "HEAD of the repo given by --repo (import graph by module stem)"})
    print(f"paths: {sum(1 for v in per_pr.values() if v)} of {len(per_pr)} PRs have a path-baseline FR set")


def cmd_headmap(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers._baseline_b_headmap import HeadMapper, new_code_class
    from verifiers._baseline_head_run import load_head_contexts

    tree, runs_dir = Path(args.tree).resolve(), Path(args.runs)
    runs = json.loads((runs_dir / "runs.json").read_text(encoding="utf-8"))
    mapper = HeadMapper(tree, load_head_contexts(tree, runs_dir, runs))
    per_pr = {}
    for rec, rev in _revs(repo, replay):
        mapped = mapper.map_pr(rev, rev.changed())
        mapped["new_code"] = new_code_class(rev, mapped)
        for drop in ("callers", "added_imports"):
            mapped.pop(drop, None)
        per_pr[str(rec["pr"])] = mapped
    _put(out, "headmap", {"head": tree.name, "roots": [{k: r[k] for k in ("root", "rc", "seconds", "summary", "db_bytes")} for r in runs], "per_pr": per_pr})
    print(f"headmap: {sum(1 for v in per_pr.values() if v['touched'])} of {len(per_pr)} PRs reach an FR through the HEAD run")


def cmd_ac(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers import _baseline_touch_binding as binding
    from verifiers._baseline_touch_binding import test_touched
    from verifiers._baseline_touch_static import static_touched

    keep = binding._frs
    binding._frs = lambda raw: frozenset(t for t in raw if binding._FR_RE.match(t))  # keep FR-xx.yy/ACnn tokens
    try:
        per_pr = {}
        for rec, rev in _revs(repo, replay):
            changes = rev.changed()
            tests = test_touched(rev, changes).touched
            static, _notes = static_touched(rev, changes)
            per_pr[str(rec["pr"])] = {"test": {k: sorted(v)[:3] for k, v in tests.items()}, "static": {k: sorted(v)[:3] for k, v in static.items()}}
    finally:
        binding._frs = keep
    _put(out, "ac_git_leg", per_pr)
    print(f"ac: {len(per_pr)} PRs")


BEHAVIOUR_DECLARED_ONLY = (937, 936, 934, 933, 925, 924, 923, 920, 913, 892, 891, 883, 866, 842, 839, 837)  # REPLAY section 2 (902, 872 are prose)
CONTROLS_AGREE = (935, 871)       # git leg and author agree
CONTROLS_NOTHING = (914, 911, 884, 859)   # behaviour-titled PRs where neither the author nor the git leg named an FR


def cmd_packs(args, repo: Path, replay: dict, out: Path) -> None:
    import random

    from verifiers._baseline_b_packs import build_pack, catalog, write_catalog

    recs = {r["pr"]: r for r in replay["records"]}
    derived_only = sorted(p for p, r in recs.items() if r["sources"] and not set(r["declared"]) & set(r["sources"]))
    strata = {**{p: "declared_only_behaviour" for p in BEHAVIOUR_DECLARED_ONLY}, **{p: "derived_only" for p in derived_only},
              **{p: "control_agree" for p in CONTROLS_AGREE}, **{p: "control_nothing_found" for p in CONTROLS_NOTHING}}
    cat = catalog((repo / ".shipwright/planning/01-adopted/spec.md").read_text(encoding="utf-8"))
    run = Path(args.run_dir)
    labels = run / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    write_catalog(cat, labels / "FR_CATALOG.md")
    order = sorted(strata)
    random.Random(20261028).shuffle(order)  # the pack order carries no stratum
    packs = []
    for pr in order:
        rec = recs[pr]
        text = build_pack(GitRev(repo, f"{rec['merge']}^", rec["merge"]), rec["title"], pr, cat)
        _write(labels / f"PR-{pr}.md", text)
        packs.append({"pr": pr, "pack": f"PR-{pr}.md", "bytes": len(text.encode("utf-8"))})
    _write(labels / "packs.json", json.dumps({"catalog": "FR_CATALOG.md", "packs": packs}, indent=1))
    _write(run / "strata.json", json.dumps({str(p): strata[p] for p in sorted(strata)}, indent=1))
    print(f"packs: {len(packs)} written to {labels}; strata in {run / 'strata.json'}")


def cmd_summary(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers._baseline_b_summary import summarise_phase_a

    strata = json.loads((Path(args.run_dir) / "strata.json").read_text(encoding="utf-8"))
    summary = summarise_phase_a(replay, _load(out)["phaseA"], strata)
    _put(out, "summary", summary)
    print(json.dumps(summary, indent=1, sort_keys=True)[:6000])


def cmd_probes(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers._baseline_b_summary import summarise_probes

    probes = json.loads(Path(args.probes_json).read_text(encoding="utf-8"))
    _put(out, "probes", {"summary": summarise_probes(probes), "results": probes["results"]})
    print(json.dumps(summarise_probes(probes), indent=1, sort_keys=True))


def cmd_eval(args, repo: Path, replay: dict, out: Path) -> None:
    from verifiers._baseline_b_eval import evaluate

    labels = Path(args.run_dir) / "labels"
    la, lb = (json.loads((labels / f"labeler_{x}.json").read_text(encoding="utf-8")) for x in "AB")
    data = _load(out)
    data["eval"] = evaluate(replay, data, la, lb)
    _save(out, data)
    print(json.dumps({"rules": data["eval"]["rules"], "labels": data["eval"]["labels"], "recall": data["eval"]["recall_on_confirmed"]}, indent=1)[:7000])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["paths", "headmap", "ac", "packs", "summary", "probes", "eval"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--replay")
    ap.add_argument("--out")
    ap.add_argument("--tree")
    ap.add_argument("--runs")
    ap.add_argument("--probes-json")
    ap.add_argument("--run-dir", help="packs: the unit run directory (labels/ goes under it)")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    replay = _load(Path(args.replay) if args.replay else repo / REPLAY)
    out = Path(args.out) if args.out else repo / OUT
    if args.command == "headmap" and not (args.tree and args.runs):
        ap.error("headmap needs --tree and --runs")
    {"paths": cmd_paths, "headmap": cmd_headmap, "ac": cmd_ac, "packs": cmd_packs, "summary": cmd_summary, "probes": cmd_probes, "eval": cmd_eval}[args.command](args, repo, replay, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
