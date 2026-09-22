#!/usr/bin/env python3
"""Per-unit review-diff attribution guard CLI (campaign-dag-scheduler R3).

See ``lib/review_attribution.py`` for the full mechanism. Three commands:

- ``pin`` — call once per attempt, at the TOP of ``campaign-mode.md``
  3f-bis, unconditionally (even for a below-threshold unit that skips the
  review cascade — pass ``--review-skipped``).
- ``ship`` — call once, right after the ``reviews.json`` record commit is
  pushed, to record its SHA into the pin's ``shipped_head`` field. Never
  needed for a ``--review-skipped`` unit.
- ``verify`` — call before merging (3g) with ``--against shipped_head``, or
  right after pinning / independently with ``--against reviewed_head``.

Exit codes:
- 0 — ``pin``/``ship`` succeeded, or ``verify`` found the field still
  matches (ALLOW)
- 1 — ``verify`` found a mismatch (BLOCK — do not merge) or any command hit
  a structural failure (unknown unit, missing pin file, git failure)

CLI:
    uv run shared/scripts/checks/check_review_attribution.py --mode pin \\
        --state "{state_path}" --unit-id "{sub_iterate_id}" \\
        --project-root "{project_root}" --campaign-worktree "{campaign_worktree}" \\
        --loop-id "{loop_id}" [--default-branch main] [--review-skipped] \\
        [--pr-node-id ID] [--pr-head-ref REF] [--pr-base-ref REF] [--json]

    uv run shared/scripts/checks/check_review_attribution.py --mode ship \\
        --state "{state_path}" --unit-id "{sub_iterate_id}" \\
        --project-root "{project_root}" --campaign-worktree "{campaign_worktree}" \\
        --loop-id "{loop_id}" --shipped-head "{sha}" [--json]

    uv run shared/scripts/checks/check_review_attribution.py --mode verify \\
        --state "{state_path}" --unit-id "{sub_iterate_id}" \\
        --project-root "{project_root}" --campaign-worktree "{campaign_worktree}" \\
        --loop-id "{loop_id}" --against {reviewed_head|shipped_head} \\
        [--expect-file review_pin.json] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_LIB = Path(__file__).resolve().parents[1]
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from lib.review_attribution import ReviewAttributionError, pin, ship, verify  # noqa: E402

# Which flags are meaningful under which --mode. A flag left out of a mode's
# set parses cleanly (argparse has no "only valid with X" primitive) but
# does nothing there; validated explicitly below so a mis-typed invocation
# fails loudly instead of silently no-op'ing (code-review round 2, low).
_MODE_ONLY_FLAGS = {
    "pin": {"default_branch", "review_skipped", "pr_node_id", "pr_head_ref", "pr_base_ref"},
    "ship": {"shipped_head"},
    "verify": {"against", "expect_file"},
}
_FLAG_CLI_NAMES = {
    "default_branch": "--default-branch", "review_skipped": "--review-skipped",
    "pr_node_id": "--pr-node-id", "pr_head_ref": "--pr-head-ref",
    "pr_base_ref": "--pr-base-ref", "shipped_head": "--shipped-head",
    "against": "--against", "expect_file": "--expect-file",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-unit review-diff attribution guard.",
    )
    parser.add_argument("--mode", required=True, choices=["pin", "ship", "verify"])
    parser.add_argument("--state", required=True, help="Path to loop_state.json")
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--project-root", required=True,
                         help="Where runs/{loop_id}/... is rooted (the shared campaign worktree today)")
    parser.add_argument("--campaign-worktree", required=True,
                         help="Fallback worktree when the unit's row carries none yet (pre-R5a: every row)")
    parser.add_argument("--loop-id", required=True)
    parser.add_argument("--json", action="store_true")

    # --mode pin only
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--review-skipped", action="store_true")
    parser.add_argument("--pr-node-id", default=None)
    parser.add_argument("--pr-head-ref", default=None)
    parser.add_argument("--pr-base-ref", default=None)

    # --mode ship only
    parser.add_argument("--shipped-head", default=None)

    # --mode verify only
    parser.add_argument("--against", choices=["reviewed_head", "shipped_head"], default=None)
    parser.add_argument("--expect-file", default="review_pin.json")

    args = parser.parse_args(argv)
    if args.mode == "verify" and args.against is None:
        parser.error("--mode verify requires --against {reviewed_head,shipped_head}")
    if args.mode == "ship" and args.shipped_head is None:
        parser.error("--mode ship requires --shipped-head")

    # Reject every flag that belongs to a DIFFERENT mode and was set away
    # from its default, so a mis-typed invocation fails loudly instead of
    # silently no-op'ing. Defaults are read from the parser itself (not a
    # hand-maintained table, which could drift from the `add_argument` calls
    # above and silently turn this into a false reject or a false pass —
    # code-review round 3, low), so this loop covers every flag every OTHER
    # mode declares.
    this_mode_flags = _MODE_ONLY_FLAGS[args.mode]
    other_mode_flags = set(_FLAG_CLI_NAMES) - this_mode_flags
    for flag in other_mode_flags:
        if getattr(args, flag) != parser.get_default(flag):
            parser.error(
                f"{_FLAG_CLI_NAMES[flag]} is a --mode {'/'.join(m for m, fs in _MODE_ONLY_FLAGS.items() if flag in fs)} "
                f"flag, not valid with --mode {args.mode}")

    try:
        if args.mode == "pin":
            result = pin(
                args.state, args.unit_id,
                project_root=args.project_root, campaign_worktree=args.campaign_worktree,
                loop_id=args.loop_id, default_branch=args.default_branch,
                review_skipped=args.review_skipped, pr_node_id=args.pr_node_id,
                pr_head_ref=args.pr_head_ref, pr_base_ref=args.pr_base_ref,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"check_review_attribution pin: ALLOW "
                      f"({result['unit_id']} @ {result['reviewed_head']})")
            return 0

        if args.mode == "ship":
            result = ship(
                args.state, args.unit_id,
                project_root=args.project_root, campaign_worktree=args.campaign_worktree,
                loop_id=args.loop_id, shipped_head=args.shipped_head,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"check_review_attribution ship: ALLOW "
                      f"({result['unit_id']} @ {result['shipped_head']})")
            return 0

        result = verify(
            args.state, args.unit_id,
            project_root=args.project_root, campaign_worktree=args.campaign_worktree,
            loop_id=args.loop_id, against=args.against, expect_file=args.expect_file,
        )
    except ReviewAttributionError as exc:
        print(f"check_review_attribution {args.mode}: BLOCK\n{exc}", file=sys.stderr)
        return 1

    verdict = "ALLOW" if result["ok"] else "BLOCK"
    if args.json:
        print(json.dumps({"decision": verdict.lower(), **result}, indent=2, ensure_ascii=False))
    else:
        print(f"check_review_attribution verify: {verdict}")
        print(result["detail"], file=sys.stderr if not result["ok"] else sys.stdout)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
