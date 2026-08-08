#!/usr/bin/env python3
"""CLI: resolve the model tier for all three spawn roles in one call.

Mirrors ``plugins/shipwright-iterate/scripts/lib/classify_complexity.py``'s
flat-argparse, single-JSON-object-to-stdout shape. Resolves ``review``,
``finalization`` and ``execution`` together (one process start, one
`shipwright_model_config.json` read) — the calling skill prose reads only the
roles it has a live spawn site for.

Usage::

    uv run resolve_model_tier.py --project-root . \
        [--review-model opus|sonnet|haiku|inherit] \
        [--finalization-model ...] [--execution-model ...]

Prints, e.g.::

    {
      "review": {"resolved": "opus", "source": "flag", "agent_param": "opus"},
      "finalization": {"resolved": "inherit", "source": "unset", "agent_param": null},
      "execution": {"resolved": "inherit", "source": "unset", "agent_param": null}
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.model_tier_config import (  # noqa: E402
    ROLES,
    agent_model_param,
    load_model_config,
    resolve_model_tier,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve per-role Claude model tiers for Shipwright subagent spawns")
    parser.add_argument("--project-root", default=".", help="Project root (config is resolved from its MAIN repo root)")
    parser.add_argument("--review-model", default=None, help="Per-run override for the review role")
    parser.add_argument("--finalization-model", default=None, help="Per-run override for the finalization role")
    parser.add_argument("--execution-model", default=None, help="Per-run override for the execution role")
    args = parser.parse_args()

    flag_values = {
        "review": args.review_model,
        "finalization": args.finalization_model,
        "execution": args.execution_model,
    }

    config = load_model_config(args.project_root)
    result = {}
    for role in sorted(ROLES):
        resolved, source = resolve_model_tier(
            role, args.project_root, flag_values[role], _config=config)
        result[role] = {
            "resolved": resolved,
            "source": source,
            "agent_param": agent_model_param(resolved),
        }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
