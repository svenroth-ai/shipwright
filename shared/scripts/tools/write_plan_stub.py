"""Write a run's plan stub: ``.shipwright/planning/iterate/<run_id>/plan.md`` (one filename convention).

    uv run shared/scripts/tools/write_plan_stub.py --project-root . --run-id RID \
        --goal "WHAT the run delivers" --reason "WHY it is needed" --ref "PR/plan/brief reference" \
        [--tiny] [--ac FR-01.03.AC05 ...] [--gap-fr FR-01.11]

Three lines (goal = WHAT, reason = WHY, reference); ``--tiny`` writes one line; a run that changes
an AC (``--ac``) or declares a catalog gap (``--gap-fr``) gets the full stub. F5b stamps the file's
path on the event as ``plan_path`` when it exists. Refuses to overwrite an existing stub.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.spec_chain import plan_rel_path, render_stub, stub_kind  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--goal", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--ac", action="append", default=[])
    ap.add_argument("--gap-fr", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.run_id) or ".." in args.run_id:
        ap.error("--run-id must be a plain run id (letters, digits, '_', '.', '-')")
    target = Path(args.project_root) / plan_rel_path(args.run_id)
    if target.exists() and not args.force:
        print(f"write_plan_stub: {target} exists (use --force to replace)", file=sys.stderr)
        return 1
    kind = stub_kind(args.ac, args.gap_fr, args.tiny)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_stub(kind, args.goal, args.reason, args.ref, args.ac, args.gap_fr), encoding="utf-8", newline="\n")
    print(f"{kind} stub written: {plan_rel_path(args.run_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
