"""Write a run's plan stub: ``.shipwright/planning/iterate/<run_id>/plan.md`` (one filename convention).

    uv run shared/scripts/tools/write_plan_stub.py --project-root . --run-id RID \
        --goal "WHAT the run delivers" --reason "WHY it is needed" --ref "PR/plan/brief reference" \
        [--tiny] [--ac FR-01.03.AC05 ...] [--gap-fr FR-01.11] [--ac-decision decided.json]

    uv run shared/scripts/tools/write_plan_stub.py --project-root . --from-json stub.json
        # stub.json: {"run_id","goal","reason","ref","tiny","ac":[...],"gap_fr","ac_decision","force"} - free text
        # never passes through a shell command line (flags given explicitly win over the file)

Three lines (goal = WHAT, reason = WHY, reference); ``--tiny`` writes one line; a run that changes
an AC (``--ac``) or declares a catalog gap (``--gap-fr``) gets the full stub. F5b stamps the file's
path on the event as ``plan_path`` when it exists. Refuses to overwrite an existing stub.

``--ac-decision`` takes the file ``ac_decision.py --out`` wrote (status ok): the stub then carries the frozen AC
copy (one line per item, the per-AC decisions) and is always the full stub. The authoritative freeze is an
append-only record next to it (``ac-record.jsonl``, :mod:`lib.ac_record`): ``--force`` appends a ``superseded``
line, it never replaces. An iterate writes it BEFORE the build; F5b only stamps the path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_decision import stub_lines  # noqa: E402
from lib.ac_record import append_record  # noqa: E402
from lib.spec_chain import plan_rel_path, render_stub, stub_kind  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--from-json", default="", help="JSON file with run_id/goal/reason/ref/tiny/ac/gap_fr/force (free text never on a command line)")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--goal", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--ref", default="")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--ac", action="append", default=[])
    ap.add_argument("--gap-fr", default="")
    ap.add_argument("--ac-decision", default="", help="decided.json from ac_decision.py --out (status ok): adds the frozen AC record")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.from_json:
        try:
            data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            ap.error(f"--from-json unreadable: {exc}")
        if not isinstance(data, dict):
            ap.error("--from-json must hold a JSON object")
        if not args.ac_decision and data.get("ac_decision"):
            args.ac_decision = str(data["ac_decision"])
        for key in ("run_id", "goal", "reason", "ref", "gap_fr"):
            if not getattr(args, key) and data.get(key):
                setattr(args, key, str(data[key]))
        args.tiny = args.tiny or bool(data.get("tiny"))
        args.force = args.force or bool(data.get("force"))
        if not args.ac and isinstance(data.get("ac"), list):
            args.ac = [str(a) for a in data["ac"]]
    for key in ("run_id", "goal", "reason", "ref"):
        if not getattr(args, key):
            ap.error(f"{key.replace('_', '-')} is required (flag or --from-json)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.run_id) or ".." in args.run_id:
        ap.error("--run-id must be a plain run id (letters, digits, '_', '.', '-')")
    target = Path(args.project_root) / plan_rel_path(args.run_id)
    if target.exists() and not args.force:
        print(f"write_plan_stub: {target} exists (use --force to replace)", file=sys.stderr)
        return 1
    ac_lines: list[str] = []
    if args.ac_decision:
        try:
            decided = json.loads(Path(args.ac_decision).read_text(encoding="utf-8"))
            if decided.get("status") != "ok":
                raise ValueError(f"status is {decided.get('status')!r}, not 'ok' (answer the questions first)")
            ac_lines = stub_lines(decided)
        except (OSError, ValueError, KeyError, AttributeError) as exc:
            ap.error(f"--ac-decision unusable: {exc}")
    kind = "full" if ac_lines else stub_kind(args.ac, args.gap_fr, args.tiny)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = render_stub(kind, args.goal, args.reason, args.ref, args.ac, args.gap_fr) + "".join(line + "\n" for line in ac_lines)
    target.write_text(body, encoding="utf-8", newline="\n")
    if ac_lines:
        append_record(args.project_root, args.run_id, decided)
    print(f"{kind} stub written: {plan_rel_path(args.run_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
