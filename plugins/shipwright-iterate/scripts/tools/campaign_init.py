#!/usr/bin/env python3
"""Initialize an iterate campaign from a structured plan.

Creates the campaign directory structure:
  .shipwright/planning/iterate/campaigns/<slug>/
    campaign.md
    sub-iterates/<id>-<slug>.md
    status.json

Usage:
    uv run campaign_init.py --project-root /path/to/project \
        --campaign-slug iterate-15 \
        --intent "Add dashboard features" \
        --sub-iterates '[{"id":"15.0","slug":"layout","title":"...","scope":"..."}]' \
        --branch-strategy stacked
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def init_campaign(
    project_root: Path,
    campaign_slug: str,
    intent: str,
    sub_iterates: list[dict],
    branch_strategy: str = "stacked",
) -> dict:
    campaign_dir = project_root / ".shipwright" / "planning" / "iterate" / "campaigns" / campaign_slug
    sub_dir = campaign_dir / "sub-iterates"
    sub_dir.mkdir(parents=True, exist_ok=True)

    campaign_md = f"""---
campaign: {campaign_slug}
branch_strategy: {branch_strategy}
created: {datetime.now(timezone.utc).isoformat()}
---

# Campaign: {campaign_slug}

## Intent

{intent}

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
"""
    for si in sub_iterates:
        campaign_md += f"| {si['id']} | {si['slug']} | {si.get('title', '')} | pending |\n"

    (campaign_dir / "campaign.md").write_text(campaign_md, encoding="utf-8")

    for si in sub_iterates:
        spec = f"""# Sub-Iterate: {si['id']} — {si.get('title', si['slug'])}

## Scope

{si.get('scope', 'TBD')}

## Acceptance Criteria

{si.get('acceptance_criteria', '- [ ] TBD')}
"""
        filename = f"{si['id']}-{si['slug']}.md"
        (sub_dir / filename).write_text(spec, encoding="utf-8")

    status = {
        "campaign": campaign_slug,
        "branch_strategy": branch_strategy,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sub_iterates": [
            {
                "id": si["id"],
                "slug": si["slug"],
                "spec_path": str(sub_dir / f"{si['id']}-{si['slug']}.md"),
                "status": "pending",
                "commit": None,
                "branch": None,
                "tests_passed": None,
                "tests_total": None,
            }
            for si in sub_iterates
        ],
    }
    (campaign_dir / "status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "campaign_dir": str(campaign_dir),
        "status_path": str(campaign_dir / "status.json"),
        "sub_iterate_count": len(sub_iterates),
        "branch_strategy": branch_strategy,
    }


def validate_independent_strategy(sub_iterates: list[dict]) -> list[str]:
    """Check for file overlaps when using independent branch strategy."""
    warnings = []
    seen_files: dict[str, str] = {}
    for si in sub_iterates:
        files = si.get("affected_files", [])
        for f in files:
            if f in seen_files:
                warnings.append(
                    f"File '{f}' claimed by both {seen_files[f]} and {si['id']} "
                    f"— 'independent' strategy may cause conflicts"
                )
            else:
                seen_files[f] = si["id"]
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an iterate campaign")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--campaign-slug", required=True)
    parser.add_argument("--intent", required=True)
    parser.add_argument("--sub-iterates", required=True, help="JSON array of sub-iterate specs")
    parser.add_argument("--branch-strategy", default="stacked", choices=["stacked", "independent"])
    args = parser.parse_args()

    try:
        sub_iterates = json.loads(args.sub_iterates)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON for --sub-iterates: {e}", file=sys.stderr)
        return 1

    if not sub_iterates:
        print("ERROR: At least one sub-iterate required", file=sys.stderr)
        return 1

    if args.branch_strategy == "independent":
        warnings = validate_independent_strategy(sub_iterates)
        for w in warnings:
            print(f"WARNING: {w}", file=sys.stderr)

    result = init_campaign(
        Path(args.project_root),
        args.campaign_slug,
        args.intent,
        sub_iterates,
        args.branch_strategy,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
