"""Read-only spec-chain tool: which specs shaped an AC, and does a run's chain resolve.

    uv run shared/scripts/tools/spec_chain_cli.py lookup --ac FR-01.03.AC05    # or --fr FR-01.03
    uv run shared/scripts/tools/spec_chain_cli.py coverage          # ACs that have history
    uv run shared/scripts/tools/spec_chain_cli.py replay --seed 20261031 --n 20

``replay`` draws ``--n`` iterate events (those naming an FR, seeded) and asks, per run, whether
the plan and the PR can be found and whether an AC is tied to it. It also reports the cohort of
runs that already carry ``plan_path`` (recorded after the spec-chain change), apart from the
backfilled picture of older runs. The sample cannot be guaranteed identical to the one in the
measurement report, whose script is not in the repository.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.affected_acs_gate import declaration_present, requires_declaration  # noqa: E402
from lib.spec_chain import ac_history, find_plan, find_pr, fr_history, load_events, parse_spec_acs  # noqa: E402


def _spec_acs(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for spec in sorted((root / ".shipwright" / "planning").glob("*/spec.md")):
        try:
            found.update(parse_spec_acs(spec.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def _event_ac_runs(events: list[dict]) -> dict[str, set[str]]:
    from lib.spec_chain import normalise_ac
    out: dict[str, set[str]] = {}
    for e in events:
        if e.get("type") == "work_completed" and isinstance(e.get("affected_acs"), list):
            for item in e["affected_acs"]:
                ac = normalise_ac(item.get("ac") if isinstance(item, dict) else item)
                if ac:
                    out.setdefault(ac, set()).add(str(e.get("adr_id")))
    return out


def with_history(root: Path, events: list[dict]) -> list[str]:
    """AC ids with at least one run that can be named (spec text or event)."""
    spec = _spec_acs(root)
    ids = {ac for ac, runs in spec.items() if runs} | set(_event_ac_runs(events))
    return sorted(ids)


def replay(root: Path, events: list[dict], seed: int, n: int, since: str = "") -> dict:
    pool = [e for e in events if e.get("type") == "work_completed" and e.get("affected_frs")]
    picked = random.Random(seed).sample(pool, min(n, len(pool)))
    spec, ev_acs = _spec_acs(root), _event_ac_runs(events)
    rows = []
    for e in picked:
        rid = str(e.get("adr_id") or "")
        plan, pr = find_plan(root, e), find_pr(root, e)
        ac = bool(e.get("affected_acs") or e.get("catalog_gap")) or any(rid in runs for runs in spec.values()) \
            or any(rid in runs for runs in ev_acs.values())
        rows.append({"run_id": rid, "plan": plan[0] if plan else None, "plan_kind": plan[1] if plan else None,
                     "pr": pr[0] if pr else None, "ac_link": ac, "recorded_with_plan_path": bool(e.get("plan_path"))})
    chain = [r for r in rows if r["plan"] and r["pr"]]
    # Post-change cohort: an independent boundary (--since), not "has plan_path": a run that forgot the field is a FAILURE.
    from lib.affected_acs_gate import is_scoped_intent
    after = [e for e in events if since and e.get("type") == "work_completed" and e.get("source") == "iterate"
             and is_scoped_intent(e) and str(e.get("ts") or "") >= since]
    cohort = random.Random(seed).sample(after, min(n, len(after)))
    # the AC declaration is asked of runtime-touching runs only (P1); a docs-only run needs plan and PR, not that
    cohort_ok = [e for e in cohort if e.get("plan_path") and find_plan(root, e) and find_pr(root, e)
                 and (declaration_present(e) or not requires_declaration(e, e.get("changed_files") or []))]
    return {"seed": seed, "pool": len(pool), "sampled": len(rows),
            "fr_plan_pr_resolved": len(chain), "ac_linked": sum(r["ac_link"] for r in rows),
            "fully_resolved": sum(1 for r in rows if r["plan"] and r["pr"] and r["ac_link"]),
            "post_change_cohort": {"since": since or None, "eligible": len(after), "sampled": len(cohort),
                                   "resolved_plan_pr_and_ac": len(cohort_ok), "enough_for_n": len(after) >= n,
                                   "failed": [str(e.get("adr_id")) for e in cohort if e not in cohort_ok]},
            "unresolved": [r for r in rows if not (r["plan"] and r["pr"])], "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["lookup", "coverage", "replay"])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--ac")
    ap.add_argument("--fr", help="lookup: an FR id instead of an AC (runs by affected_frs)")
    ap.add_argument("--seed", type=int, default=20261031)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--since", default="", help="replay: ISO timestamp; runs recorded at/after it form the post-change cohort")
    ap.add_argument("--no-pr", action="store_true", help="lookup: skip the git search for the PR")
    args = ap.parse_args()
    root = Path(args.project_root)
    events = load_events(root)
    if args.command == "lookup":
        if not (args.ac or args.fr):
            ap.error("lookup needs --ac or --fr")
        out = (fr_history(root, args.fr, events, with_pr=not args.no_pr) if args.fr
               else ac_history(root, args.ac, events, with_pr=not args.no_pr))
    elif args.command == "coverage":
        ids = with_history(root, events)
        out = {"acs_with_history": len(ids), "acs": ids}
    else:
        out = replay(root, events, args.seed, args.n, args.since)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
