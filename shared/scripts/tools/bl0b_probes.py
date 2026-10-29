#!/usr/bin/env python3
"""BL0b item 6: blind mutation probes judged by test failure (see verifiers/_baseline_b_probes.py).

    bl0b_probes.py --head T --runs R --probe-tree P --out O.json [--count 50] [--seed N] [--budget-minutes 100]

``T`` is the detached HEAD worktree the context run used, ``R`` its run directory (databases, junit), ``P`` a second
detached worktree at the same commit that is mutated and restored. Measurement only; serial, one pytest process at a time.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verifiers._baseline_b_headmap import HeadMapper  # noqa: E402
from verifiers._baseline_b_probes import _root_of_test, candidate_tests, classify, draw, eligible_functions, junit_failures, mutate, run_probe, tokens_for  # noqa: E402
from verifiers._baseline_touch_coverage import _spans  # noqa: E402
from verifiers._baseline_head_run import load_head_contexts, prefix_of  # noqa: E402
from verifiers._baseline_proc import clean_env, guard_workdir  # noqa: E402


def _second_pass(args, mapper, ptree: Path, runs_dir: Path, pre: set[str]) -> int:
    """Probes with no textual candidate whose function an FR-bound test executes per the contexts: run exactly those bound tests.
    Reported separately: the test choice reads T-code's data, so it measures how often a T-code flag is a real detection, not T-code's recall."""
    data = json.loads(Path(args.out).read_text(encoding="utf-8"))
    env = clean_env()
    for rec in data["results"]:
        if rec.get("cause") != "no_candidate_bound_test_references_module" or not rec.get("tcode_attributes_fr"):
            continue
        span = next(s for s in _spans((ptree / rec["file"]).read_text(encoding="utf-8")) if s[0] == rec["func"])
        lines = mapper.contexts.get(rec["file"], {})
        bound = sorted({t for ln in range(span[1], span[2] + 1) for t in lines.get(ln, set()) if mapper.tokens_of(t)})
        by_root: dict[str, set[str]] = {}
        for t in bound:
            f = t.partition("::")[0]
            by_root.setdefault(_root_of_test(f), set()).add(f)
        if not mutate(ptree, rec):
            continue
        try:
            failed: set[str] = set()
            for root, files in sorted(by_root.items()):
                failed |= set(run_probe(ptree, root, sorted(files)[:8], runs_dir, env, args.root_timeout)["failed"]) - pre
        finally:
            subprocess.run(["git", "-C", str(ptree), "checkout", "--", rec["file"]], capture_output=True, check=False)
        rec["second_pass"] = {"bound_tests_named_by_contexts": len(bound), "bound_failures": sorted(t for t, b in tokens_for(ptree, failed).items() if b)}
        Path(args.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
        print("second pass", rec["file"], rec["func"], bool(rec["second_pass"]["bound_failures"]), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--head", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--probe-tree", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261028)
    ap.add_argument("--budget-minutes", type=float, default=100)
    ap.add_argument("--root-timeout", type=int, default=420)
    ap.add_argument("--second-pass", action="store_true", help="re-judge the probes no textual candidate could test but T-code links to an FR, with the tests the contexts name")
    args = ap.parse_args(argv)
    head, runs_dir, ptree, out = Path(args.head), Path(args.runs), Path(args.probe_tree), Path(args.out)
    guard_workdir(head, runs_dir)
    runs = json.loads((runs_dir / "runs.json").read_text(encoding="utf-8"))
    pre = {f for r in runs if r.get("junit") for f in junit_failures(runs_dir / r["junit"], head / prefix_of(r["root"]).rstrip("/") if prefix_of(r["root"]) else head, prefix_of(r["root"]))}
    mapper = HeadMapper(head, load_head_contexts(head, runs_dir, runs))
    if args.second_pass:
        return _second_pass(args, mapper, ptree, runs_dir, pre)
    funcs = eligible_functions(ptree)
    sample = draw(funcs, int(args.count * 1.4), args.seed)
    env, results, deadline = clean_env(), [], time.monotonic() + args.budget_minutes * 60
    for probe in sample:
        if len([r for r in results if r["status"] == "judged"]) >= args.count or time.monotonic() > deadline:
            break
        rec = {**probe, "status": "judged"}
        if not mutate(ptree, probe):
            rec["status"] = "skipped_mutation_did_not_parse"
            results.append(rec)
            continue
        try:
            cand = candidate_tests(ptree, probe)
            failed: set[str] = set()
            rec["roots_run"] = []
            for root, files in sorted(cand.items()):
                res = run_probe(ptree, root, files, runs_dir, env, args.root_timeout)
                rec["roots_run"].append({k: res[k] for k in ("root", "rc", "seconds")} | {"files": files})
                failed |= set(res["failed"]) - pre
            bound = tokens_for(ptree, failed)
            rel, func = probe["file"], probe["func"]
            span = next((s for s in _spans((head / rel).read_text(encoding="utf-8")) if s[0] == func), None)
            lines = mapper.contexts.get(rel, {})
            tests = set().union(*(lines.get(ln, set()) for ln in range(span[1], span[2] + 1))) if span else set()
            fr_attr = any(mapper.tokens_of(t) for t in tests)
            rec.update({"new_failures": sorted(failed), "bound_failures": sorted(t for t, b in bound.items() if b),
                        "tcode_attributes_fr": fr_attr, "executed_by_any_test": bool(tests),
                        "cause": classify(probe, bound, fr_attr, bool(tests), bool(cand), bool(cand))})
        finally:
            subprocess.run(["git", "-C", str(ptree), "checkout", "--", probe["file"]], capture_output=True, check=False)
        results.append(rec)
        out.write_text(json.dumps({"seed": args.seed, "eligible_functions": len(funcs), "results": results}, indent=1), encoding="utf-8")
        print(probe["file"], probe["func"], rec.get("cause"), flush=True)
    out.write_text(json.dumps({"seed": args.seed, "eligible_functions": len(funcs), "preexisting_failures": len(pre), "results": results}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
