#!/usr/bin/env python3
"""Replay the independent gap check over merged PRs (measurement; read-only on the repo).

For each PR it rebuilds what the check would have seen at the time: the PR's own diff
(``git diff <merge>^1 <merge>``, the full merge-base diff of a squash merge), the requirement
catalog as it stood just before the merge, and the declaration the PR itself recorded (the
``work_completed`` event lines the PR added to ``shipwright_events.jsonl``). No label or
verdict is passed to the model.

    uv run shared/scripts/tools/ai_gap_check_replay.py --prs 843,869 --out-dir DIR [--reviewer openai]
    uv run shared/scripts/tools/ai_gap_check_replay.py --fresh 10 --seed 20261031 --exclude 843,... --out-dir DIR

One ``pr-<n>.json`` per PR lands in ``--out-dir`` (the check record plus the declaration used);
re-running skips PRs that already have a record unless ``--force``.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
for _p in (str(_TOOLS.parent), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.ai_gap_check import run_check  # noqa: E402
from lib.ai_gap_check_core import declaration_from_event  # noqa: E402


def _run(args: list[str], cwd: Path, timeout: int = 300) -> str:
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def merge_commit(root: Path, pr: int) -> str:
    return json.loads(_run(["gh", "pr", "view", str(pr), "--json", "mergeCommit"], root))["mergeCommit"]["oid"]


def pr_diff(root: Path, merge: str) -> str:
    return _run(["git", "diff", "--no-color", f"{merge}^1", merge], root)


def specs_before(root: Path, merge: str) -> list[str]:
    names = _run(["git", "ls-tree", "-r", "--name-only", f"{merge}^1", ".shipwright/planning/"], root).split()
    return [_run(["git", "show", f"{merge}^1:{n}"], root) for n in names if n.endswith("/spec.md") and n.count("/") == 3]


def event_in_diff(diff: str) -> dict:
    """The last iterate ``work_completed`` event the PR added to the event log ({} when it added none)."""
    found: dict = {}
    inside = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            inside = line.endswith(" b/shipwright_events.jsonl")
        elif inside and line.startswith("+") and not line.startswith("+++"):
            try:
                evt = json.loads(line[1:])
            except ValueError:
                continue
            if isinstance(evt, dict) and evt.get("type") == "work_completed" and evt.get("source") == "iterate":
                found = evt
    return found


def recent_iterate_prs(root: Path, limit: int = 150) -> list[int]:
    rows = json.loads(_run(["gh", "pr", "list", "--state", "merged", "--limit", str(limit), "--json", "number,headRefName"], root))
    return sorted(r["number"] for r in rows if str(r.get("headRefName") or "").startswith("iterate/"))


def one(root: Path, pr: int, reviewer: str, out_dir: Path, force: bool) -> dict:
    target = out_dir / f"pr-{pr}.json"
    if target.exists() and not force:
        return json.loads(target.read_text(encoding="utf-8"))
    merge = merge_commit(root, pr)
    diff = pr_diff(root, merge)
    event = event_in_diff(diff)
    declaration = declaration_from_event(event)
    record = run_check(diff, declaration, specs_before(root, merge), reviewer, root)
    record.update({"pr": pr, "merge": merge, "declaration": declaration, "declaration_source": "event added by the PR" if event else "none found in the PR diff"})
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay the independent gap check over merged PRs")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--prs", default="", help="comma list of PR numbers")
    ap.add_argument("--fresh", type=int, default=0, help="draw N recent iterate PRs not in --exclude")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--seed", type=int, default=20261031)
    ap.add_argument("--reviewer", default="openai", choices=("openai", "glm"))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    root = Path(args.project_root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prs = [int(x) for x in args.prs.split(",") if x.strip()]
    if args.fresh:
        excluded = {int(x) for x in args.exclude.split(",") if x.strip()}
        pool = [n for n in recent_iterate_prs(root) if n not in excluded]
        prs = sorted(random.Random(args.seed).sample(pool, min(args.fresh, len(pool))))
        (out_dir / "fresh-draw.json").write_text(json.dumps({"seed": args.seed, "pool": pool, "drawn": prs}) + "\n", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool_ex:
        futures = {n: pool_ex.submit(one, root, n, args.reviewer, out_dir, args.force) for n in prs}
        for n, fut in futures.items():
            try:
                rec = fut.result()
                res = rec.get("result") or {}
                print(f"#{n}: {rec['status']} verdict={res.get('verdict')} gap={res.get('gap')} {rec.get('reason', '')[:120]}", flush=True)
            except Exception as exc:  # noqa: BLE001 - report and continue with the other PRs
                print(f"#{n}: ERROR {exc}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
