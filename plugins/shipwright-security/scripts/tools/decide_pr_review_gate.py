#!/usr/bin/env python3
"""CLI wrapper for `pr_review_gate_verdict.decide_gate`, invoked by the final
"Post the PR Review verdict" step in `.github/workflows/pr-review-run.yml`.

Isolated from that step's stale-head / impostor-check-run bash above it,
which stays bash — that logic's own risk is git/API-history shaped, not this
state-composition seam. Prints ``state=<state>`` and ``desc=<description>``
on stdout for the caller to capture with plain-text parsing (never `eval` —
the caller's inputs are step outcomes and a small closed vocabulary of
reason strings, but posting a commit status is not the place to trust that).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from pr_review_gate_verdict import decide_gate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1-conclusion", required=True)
    parser.add_argument("--tier-outcome", required=True)
    parser.add_argument("--all-generated", required=True)
    parser.add_argument("--all-generated-reason", default="")
    parser.add_argument("--needs-review", required=True)
    parser.add_argument("--consume-waiver-outcome", default="")
    parser.add_argument("--review-outcome", default="")
    parser.add_argument("--tier-reason", default="")
    args = parser.parse_args(argv)

    state, desc = decide_gate(
        stage1_ok=args.stage1_conclusion == "success",
        tier_ok=args.tier_outcome == "success",
        all_generated=args.all_generated == "true",
        all_generated_reason=args.all_generated_reason,
        needs_review=args.needs_review == "true",
        waiver_consumed_ok=args.consume_waiver_outcome == "success",
        review_outcome=args.review_outcome,
        tier_reason=args.tier_reason,
    )
    print(f"state={state}")
    print(f"desc={desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
