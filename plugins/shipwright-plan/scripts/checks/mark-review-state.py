#!/usr/bin/env python3
"""Write external_review_state.json marker for Step 5 completion.

Usage:
    uv run mark-review-state.py \
        --planning-dir <path> \
        --status {completed|skipped_user_opt_out|skipped_config_disabled} \
        [--provider openrouter|gemini|openai] \
        [--reason "user opted out: offline demo"] \
        [--findings-count 5] \
        [--self-review-fallback-ran]

The skill invokes this after running (or explicitly skipping) external review.
Downstream steps (Section Splitting, compliance evidence collection) read the
marker to confirm Step 5 was completed and see how review was handled.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REVIEW_STATE_FILE = "external_review_state.json"

ALLOWED_STATUSES = {
    "completed",
    "skipped_user_opt_out",
    "skipped_config_disabled",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write external review state marker")
    parser.add_argument("--planning-dir", required=True)
    parser.add_argument("--status", required=True)
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

    marker = {
        "status": args.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "findings_count": args.findings_count,
        "self_review_fallback_ran": args.self_review_fallback_ran
            or args.status in {"skipped_user_opt_out", "skipped_config_disabled"},
        "reason": args.reason,
    }

    out_path = planning_dir / REVIEW_STATE_FILE
    out_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"success": True, "marker_path": str(out_path), "state": marker}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
