#!/usr/bin/env python3
"""Replay the baseline touched-set over the last merged PRs (BP unit BL0, measurement only).

For each merged PR the squash commit's first parent is the merge base, so the derived
touched set (T-spec, T-test, static test-dir attribution, 'moved') is computed exactly as the
CI job would compute it, then compared with the PR's historical ``fr_impact`` (fallback
``affected_frs``, else none). Nothing here gates anything; it feeds the REPLAY report.

    uv run shared/scripts/tools/replay_baseline_lock.py --repo . --limit 100 --out replay.json
    ... --code-sample 20 --workdir <scratch>      # also T-code (context runs at the merge base)
    ... --from-json replay.json                    # re-summarise without git

Reads PR metadata from ``gh pr list`` (or ``--prs-json``); needs the squash commits locally.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verifiers._baseline_touch_core import evaluate_hold, touched_set  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402
from verifiers._baseline_touch_replay_stats import declared_frs, pr_class, sample_for_operator, summarise  # noqa: E402

_RUN_ID = re.compile(r"\.shipwright/agent_docs/iterates/(iterate-[\w.-]+?)(?:\.test-results)?\.json$")


def _events_by_run(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "work_completed" and event.get("adr_id"):
            out[str(event["adr_id"])] = event
    return out


def _run_id(changes, message: str) -> str:
    for _s, _o, new in changes:
        m = _RUN_ID.search(new)
        if m:
            return m[1]
    m = re.search(r"^Run-ID:\s*(\S+)", message, re.M)
    return m[1] if m else ""


def load_prs(repo: Path, limit: int, cached: str | None) -> list[dict]:
    if cached:
        return json.loads(Path(cached).read_text(encoding="utf-8"))
    cmd = ["gh", "pr", "list", "--state", "merged", "--limit", str(limit),
           "--json", "number,title,mergeCommit,headRefName,labels,mergedAt"]
    return json.loads(subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=True).stdout)


def replay_one(repo: Path, pr: dict, events: dict[str, dict]) -> dict:
    oid = (pr.get("mergeCommit") or {}).get("oid") or ""
    rec = {"pr": pr["number"], "title": pr["title"], "branch": pr["headRefName"], "merged_at": pr.get("mergedAt"),
           "class": pr_class(pr["headRefName"], pr["title"]), "merge": oid, "labels": [l["name"] for l in pr.get("labels", [])]}
    try:
        rev = GitRev(repo, f"{oid}^", oid)
        changes = rev.changed()
        message = rev.git("log", "-1", "--format=%B", oid)[1]
        run_id = _run_id(changes, message)
        declared, source = declared_frs(events.get(run_id))
        touched = touched_set(rev)
        verdict = evaluate_hold(touched)
        rec.update({
            "run_id": run_id, "declared": declared, "declared_from": source, "files": len(changes),
            "sources": {fr: sorted(s) for fr, s in touched.sources().items()},
            "moved": [list(m) for m in touched.moved], "new_frs": sorted(touched.new_frs),
            "held": verdict["held"], "incomplete": verdict["incomplete"],
            "evidence": {"test": {fr: sorted(ids)[:4] for fr, ids in touched.test.items()},
                         "static": {fr: sorted(ids)[:3] for fr, ids in touched.static.items()}},
        })
    except Exception as exc:  # one broken PR is reported, never fatal to the replay
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--prs-json")
    ap.add_argument("--events", help="events file (default: <repo>/shipwright_events.jsonl)")
    ap.add_argument("--out", help="write the per-PR records and summary as JSON")
    ap.add_argument("--from-json", help="re-summarise a previous --out file")
    ap.add_argument("--code-sample", type=int, default=0, help="also run T-code over this many PRs")
    ap.add_argument("--workdir", help="scratch directory for the context runs")
    ap.add_argument("--probes-only", action="store_true", help="re-run only the probes over the databases in --workdir")
    ap.add_argument("--probes", type=int, default=0, help="mutation probes over this many of the code-sample PRs")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()

    if args.from_json:
        records = json.loads(Path(args.from_json).read_text(encoding="utf-8"))["records"]
    else:
        events = _events_by_run(Path(args.events) if args.events else repo / "shipwright_events.jsonl")
        records = [replay_one(repo, pr, events) for pr in load_prs(repo, args.limit, args.prs_json)]
    payload = {"records": records, "summary": summarise(records), "sample": [r["pr"] for r in sample_for_operator(records)]}
    if args.probes_only:
        if not (args.from_json and args.workdir):
            ap.error("--probes-only needs --from-json (records with code_files) and --workdir (the context databases)")
        from verifiers._baseline_touch_replay_code import rerun_probes

        probes = rerun_probes(repo, records, args.probes, Path(args.workdir))
        if args.out:
            Path(args.out).write_text(json.dumps(probes, indent=1, sort_keys=True), encoding="utf-8")
        print(json.dumps(probes, indent=1, sort_keys=True))
        return 0
    if args.code_sample:
        from verifiers._baseline_touch_replay_code import replay_code

        if not args.workdir:
            ap.error("--code-sample needs --workdir")
        payload["code"] = replay_code(repo, records, args.code_sample, Path(args.workdir), args.probes)
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
