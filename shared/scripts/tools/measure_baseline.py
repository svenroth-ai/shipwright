#!/usr/bin/env python3
"""Re-run the measurements behind the baseline REPLAY report (BP unit BL0), into REPLAY.json.

    measure_baseline.py roots    --repo . --workdir W [--only ROOT ...] [--plain ROOT ...]
    measure_baseline.py fanout   --repo . --workdir W        # FRs per changed function + per executed function
    measure_baseline.py verifier --repo . --workdir W [--count 5]   # verify_iterate_finalization.py wall-clock
    measure_baseline.py label    --repo . [--workdir W]      # per-hit labels (see _baseline_label_hits.py)

Every subcommand reads and updates ``--out`` (default: the committed REPLAY.json) under ``measure.*``
(``label`` also writes ``records[].hits``), so each number in REPLAY.md can be cited to a key here.
``roots`` runs the whole test suite root by root (about 40 minutes); give it a scratch ``--venv`` so
the project environment is untouched. Nothing here gates anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verifiers._baseline_measure import discover_roots, fanout_changed, fanout_executed, time_root, verifier_wallclock  # noqa: E402

DEFAULT_OUT = ".shipwright/planning/campaigns/2026-10-27-baseline-protection-REPLAY.json"
_SECRET = ("TOKEN", "SECRET", "KEY", "PASSWORD", "GITHUB_")
PLAIN_ROOTS = ("shared/scripts/tools/tests", "plugins/shipwright-changelog/tests")


def load(out: Path) -> dict:
    return json.loads(out.read_text(encoding="utf-8"))


def save(out: Path, data: dict) -> None:
    out.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


def merge(out: Path, key: str, value) -> None:
    data = load(out)
    data.setdefault("measure", {})[key] = value
    save(out, data)


def _env(venv: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in _SECRET) and k != "CI"}
    if venv:
        env["UV_PROJECT_ENVIRONMENT"] = venv
    return env


def cmd_roots(args, repo: Path, out: Path) -> None:
    roots = args.only or discover_roots(repo)
    plain = args.plain if args.plain is not None else [r for r in PLAIN_ROOTS if r in roots]
    env, runs = _env(args.venv), []
    for root in roots:
        for contexts in (True, False):
            if contexts or root in plain:
                runs.append(time_root(repo, root, args.workdir, contexts=contexts, env=env))
                print(json.dumps(runs[-1]), file=sys.stderr, flush=True)
    merge(out, "roots", {"runs": runs, "total_context_seconds": round(sum(r["seconds"] for r in runs if r["contexts"]), 1),
                         "note": "one pytest process per root, run one after another on a shared machine (upper bounds); coverage target: shared"})


def cmd_fanout(args, repo: Path, out: Path) -> None:
    from verifiers._baseline_touch_coverage import load_contexts, merge_contexts

    data = load(out)
    merge(out, "fanout_changed", fanout_changed((data.get("code") or {}).get("prs", [])))
    dbs = sorted(p for p in Path(args.workdir).glob("cov-*") if "-plain" not in p.name and "." not in p.name and p.is_file() and p.stat().st_size)
    parts = [load_contexts(db, repo, "") for db in dbs]
    merge(out, "fanout_executed", {**fanout_executed(merge_contexts(parts), repo), "databases": [p.name for p in dbs]})


def cmd_verifier(args, repo: Path, out: Path) -> None:
    merge(out, "verifier", verifier_wallclock(repo, load(out)["records"], args.count, args.workdir))


def cmd_label(args, repo: Path, out: Path) -> None:
    from verifiers._baseline_label_hits import label_all

    data = load(out)
    label_all(repo, data, Path(args.workdir) if args.workdir else None)
    save(out, data)
    print(json.dumps(data["measure"]["hit_labels"]["by_source"], indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["roots", "fanout", "verifier", "label"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workdir")
    ap.add_argument("--venv")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--plain", nargs="*")
    ap.add_argument("--count", type=int, default=5)
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    out = Path(args.out) if args.out else repo / DEFAULT_OUT
    if args.command in ("roots", "fanout") and not args.workdir:
        ap.error(f"{args.command} needs --workdir")
    {"roots": cmd_roots, "fanout": cmd_fanout, "verifier": cmd_verifier, "label": cmd_label}[args.command](args, repo, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
