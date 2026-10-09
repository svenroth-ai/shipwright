"""Print whether the runner's review rows let ``3f-bis`` skip its re-review.

    review_attested.py --project-root <unit worktree> --run-id <id> --head <sha>

stdout is one JSON line ``{"attested": bool, "reason": str}``; the exit code is
``0`` for either answer (``2`` for a usage error), so a caller that cannot parse
the line treats it as not attested and runs the cascade. Logic and rationale:
``lib.review_attestation``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_attestation import attest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--diff-lines", type=int, default=None,
                        help="3f-bis's own diff size; omitted = unknown, so doubt must have completed")
    args = parser.parse_args(argv)
    try:
        attested, reason = attest(args.project_root, args.run_id, args.head, args.diff_lines)
    except Exception as exc:  # noqa: BLE001 -- any failure is "not attested", with its reason
        attested, reason = False, f"attestation error: {exc}"
    print(json.dumps({"attested": attested, "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
