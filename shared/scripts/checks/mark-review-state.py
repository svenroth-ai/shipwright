#!/usr/bin/env python3
"""Write external_review_state.json marker for review-step completion.

Shared across plugins (plan Step 5, iterate medium+ external review, and the
build/iterate code-review cascade). The marker confirms a review-step branch
(Branch A/B/C) ran to completion and how review was handled. Downstream
consumers (compliance evidence collection, plan resume gate, iterate
finalization) read this marker to verify the gate passed.

Two marker filenames, selected by ``--review-type``:

- ``--review-type plan|iterate`` (or omitted) →
  ``external_review_state.json`` — used by the plan/iterate Branch A/B/C flow.
- ``--review-type code`` →
  ``external_code_review_state.json`` — used by the build/iterate code-review
  cascade. The plan/iterate marker is intentionally NOT touched for
  code-review runs so the two gates stay independent.

The marker payload includes a ``review_mode`` field that records which mode
this marker was written for (one of ``plan``, ``iterate``, ``code``, or
``null`` when omitted). The field is named ``review_mode`` (NOT
``review_type``) to disambiguate from the existing ``review_type`` taxonomy
in the build-side dashboard (``self-review`` / ``full-review`` /
``external-review``). The two share no semantic overlap and are tracked
independently.

Status values cover three branches plus two pragmatic re-uses for
code-review-mode runs:

- ``completed`` — review ran to completion (success or partial-success).
- ``skipped_user_opt_out`` — operator chose to skip. Code-review-mode also
  reuses this for the empty-diff short-circuit (with reason ``"empty_diff"``)
  because the cascade has nothing to review and the existing status taxonomy
  is closed by the verifier suite.
- ``skipped_config_disabled`` — user disabled review in config. Code-review-
  mode also reuses this when no API keys are present (the build/iterate
  cascade collapses Branch B "missing_keys" + Branch C "user_disabled" into
  this single status — code-review is non-interactive and missing keys are
  treated as effective disable).

Usage:
    uv run shared/scripts/checks/mark-review-state.py \\
        --planning-dir <path> \\
        --status {completed|skipped_user_opt_out|skipped_config_disabled} \\
        [--review-type plan|iterate|code] \\
        [--provider openrouter|gemini|openai] \\
        [--reason "user opted out: offline demo"] \\
        [--findings-count 5] \\
        [--self-review-fallback-ran]
"""

import argparse
import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# The marker shape lives in lib/ so record_review_pass.py can write the same
# marker without duplicating it. This script stays the CLI it always was.
from lib.review_marker import (  # noqa: E402
    ALLOWED_REVIEW_TYPES,
    ALLOWED_STATUSES,
    CODE_REVIEW_STATE_FILE,
    REVIEW_STATE_FILE,
    build_marker,
    write_marker,
)

__all__ = [
    "ALLOWED_REVIEW_TYPES",
    "ALLOWED_STATUSES",
    "CODE_REVIEW_STATE_FILE",
    "REVIEW_STATE_FILE",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Write external review state marker")
    parser.add_argument("--planning-dir", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument(
        "--review-type",
        choices=ALLOWED_REVIEW_TYPES,
        default=None,
        help=(
            "Which review gate this marker covers. 'plan' or 'iterate' "
            "(default when omitted) writes external_review_state.json. "
            "'code' writes external_code_review_state.json for the "
            "build/iterate code-review cascade."
        ),
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--findings-count", type=int, default=0)
    parser.add_argument("--self-review-fallback-ran", action="store_true")
    args = parser.parse_args()

    if args.status not in ALLOWED_STATUSES:
        print(json.dumps({
            "success": False,
            "error": "invalid_status",
            "message": f"status must be one of {sorted(ALLOWED_STATUSES)}",
        }))
        return 2

    planning_dir = Path(args.planning_dir)
    if not planning_dir.exists() or not planning_dir.is_dir():
        print(json.dumps({
            "success": False,
            "error": "planning_dir_not_found",
            "message": f"Planning dir does not exist: {planning_dir}",
        }))
        return 2

    marker = build_marker(
        status=args.status,
        review_type=args.review_type,
        provider=args.provider,
        reason=args.reason,
        findings_count=args.findings_count,
        self_review_fallback_ran=args.self_review_fallback_ran,
    )
    out_path = write_marker(planning_dir, marker, args.review_type)

    print(json.dumps({"success": True, "marker_path": str(out_path), "state": marker}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
