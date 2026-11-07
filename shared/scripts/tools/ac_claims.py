"""Build the claims file the post-build AC review reads (ac-at-start Q2, phase 1).

    uv run shared/scripts/tools/ac_claims.py build --project-root . --run-id RID --base-ref {base_branch}

Reads the run's ``ac-record.jsonl`` (working tree) and the requirement catalog at merge-base(base-ref, HEAD), and
writes ``.shipwright/planning/iterate/<run_id>/ac-claims.json`` beside the record (:mod:`lib.ac_claims`): code only, no
model, no agent-written field. Hand that path to the ``spec-reviewer`` as its optional third input. The file is derived
and regenerable: do not commit it (F11 recomputes the claims from the committed record).

Prints ``{"path", "claims"}`` and exits 0. An unreadable base ref is ``{"status": "skipped", "note"}`` and exit 0
(the review then simply has no third input; F11 says so). An unsafe ``--run-id`` is exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_claims import build_claims, write_claims  # noqa: E402
from lib.ac_mode import is_safe_run_id  # noqa: E402
from lib.ac_surface import merge_base  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write ac-claims.json beside the AC record")
    b.add_argument("--project-root", default=".")
    b.add_argument("--run-id", required=True)
    b.add_argument("--base-ref", required=True, help="the ref the change branches from; resolved to merge-base(base-ref, HEAD)")
    args = ap.parse_args(argv)
    if not is_safe_run_id(args.run_id):
        print(json.dumps({"error": "--run-id must be a plain run id (letters, digits, '_', '.', '-'; no '..')"}))
        return 2
    try:
        base = merge_base(args.project_root, args.base_ref)
        count = len(build_claims(args.project_root, args.run_id, base)["claims"])
        path = write_claims(args.project_root, args.run_id, base)
    except (RuntimeError, OSError) as exc:
        print(json.dumps({"status": "skipped", "note": f"cannot build the claims against {args.base_ref!r}: {str(exc)[:200]}"}))
        return 0
    print(json.dumps({"path": str(path), "claims": count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
