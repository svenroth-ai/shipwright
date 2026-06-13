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
        --branch-strategy serial   # default; interleaved (build->PR->merge->next)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Canonical triage-item id shape — `trg-` + 8 lowercase hex chars, mirroring
# shared/scripts/triage.py:_generate_id (`f"trg-{uuid4().hex[:8]}"`). Used to
# validate the --expands-triage / --from-triage anchor before it is stamped
# into status.json + the campaign.md frontmatter that the WebUI joins on.
TRIAGE_ID_RE = re.compile(r"^trg-[0-9a-f]{8}$")


def _validate_triage_id(value: str | None, flag: str) -> str | None:
    """Return the validated triage id, or raise ValueError.

    `None` (flag omitted) passes through unchanged. `flag` names the source
    (`--expands-triage` / `expands_triage`) so the error message points at the
    offending input.
    """
    if value is None:
        return None
    if not TRIAGE_ID_RE.match(value):
        raise ValueError(
            f"{flag} {value!r} does not match ^trg-[0-9a-f]{{8}}$ "
            "(canonical shape: trg-<8 hex>, e.g. trg-1a2b3c4d)."
        )
    return value


def _find_shared_scripts() -> Path:
    """Locate shared/scripts/ by walking up — robust to plugin-layout depth
    (dev monorepo root vs installed plugin-cache ``shipwright/`` root)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


def _read_triage_item(project_root: Path, triage_id: str) -> dict | None:
    """Return the resolved triage item for `triage_id`, or None if absent.

    Reads via the shared triage SSoT (`triage.read_all_items`) so --from-triage
    sees the same status-resolved view the WebUI / RTM consume. The import is
    lazy: only --from-triage pays the shared/scripts path cost.
    """
    shared_scripts = str(_find_shared_scripts())
    if shared_scripts not in sys.path:
        sys.path.insert(0, shared_scripts)
    from triage import read_all_items

    for item in read_all_items(project_root):
        if item.get("id") == triage_id:
            return item
    return None


def _seed_intent(item: dict) -> str:
    """Build a campaign intent string from a triage item's title + detail."""
    title = (item.get("title") or "").strip()
    detail = (item.get("detail") or "").strip()
    if title and detail:
        return f"{title}\n\n{detail}"
    return title or detail or "(seeded from triage item)"


def init_campaign(
    project_root: Path,
    campaign_slug: str,
    intent: str,
    sub_iterates: list[dict],
    branch_strategy: str = "serial",
    expands_triage: str | None = None,
) -> dict:
    # Defensive validation — `init_campaign` is imported directly (tests,
    # campaign mode), not only reached through `main`'s CLI guard.
    expands_triage = _validate_triage_id(expands_triage, "expands_triage")

    campaign_dir = project_root / ".shipwright" / "planning" / "iterate" / "campaigns" / campaign_slug
    sub_dir = campaign_dir / "sub-iterates"
    sub_dir.mkdir(parents=True, exist_ok=True)

    # The anchor line (when set) is what the WebUI join reads:
    # `fm.expandsTriage || fm.expands_triage == triage item id`, per project.
    anchor_line = f"expands_triage: {expands_triage}\n" if expands_triage else ""
    campaign_md = f"""---
campaign: {campaign_slug}
status: draft
branch_strategy: {branch_strategy}
created: {datetime.now(timezone.utc).isoformat()}
{anchor_line}---

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
        # Producer-owned campaign lifecycle status (draft -> active -> complete).
        # A fresh campaign is "draft" (planned, triage-only) until it is started.
        # Consumers that predate this field treat its absence as legacy and fall
        # back to derived done<total. Canonical lowercase; see campaign_progress.py.
        "status": "draft",
        "branch_strategy": branch_strategy,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Present only when anchored (un-anchored campaigns stay legacy-shaped).
        **({"expands_triage": expands_triage} if expands_triage else {}),
        "sub_iterates": [
            {
                "id": si["id"],
                "slug": si["slug"],
                # Repo-relative POSIX (portable across machines/OS; N1, trg-196f4aa6).
                "spec_path": f".shipwright/planning/iterate/campaigns/{campaign_slug}"
                             f"/sub-iterates/{si['id']}-{si['slug']}.md",
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
        "expands_triage": expands_triage,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize an iterate campaign")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--campaign-slug", required=True)
    parser.add_argument("--intent", default=None,
                        help="Campaign intent. Optional when --from-triage is "
                             "given (then seeded from the triage item); required "
                             "otherwise.")
    parser.add_argument("--sub-iterates", required=True, help="JSON array of sub-iterate specs")
    parser.add_argument("--branch-strategy", default="serial", choices=["serial", "stacked", "independent"])
    parser.add_argument("--expands-triage", default=None,
                        help="Triage item id (trg-<8 hex>) this campaign expands. "
                             "Stamped into status.json AND the campaign.md "
                             "frontmatter so the WebUI shows the 'Start Campaign' "
                             "CTA on that triage card (per-project join).")
    parser.add_argument("--from-triage", default=None,
                        help="Promote a triage item: seeds --intent from the "
                             "item's title/detail (when --intent is omitted) and "
                             "implies --expands-triage <id>. Reads "
                             "<project-root>/.shipwright/triage.jsonl.")
    args = parser.parse_args(argv)

    try:
        sub_iterates = json.loads(args.sub_iterates)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON for --sub-iterates: {e}", file=sys.stderr)
        return 1

    if not sub_iterates:
        print("ERROR: At least one sub-iterate required", file=sys.stderr)
        return 1

    # Validate triage-id shapes up front for clean CLI errors (before any I/O).
    try:
        expands_triage = _validate_triage_id(args.expands_triage, "--expands-triage")
        from_triage = _validate_triage_id(args.from_triage, "--from-triage")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    project_root = Path(args.project_root)
    intent = args.intent

    # --from-triage: promote a triage item — seed the intent and imply the anchor.
    if from_triage is not None:
        if expands_triage is not None and expands_triage != from_triage:
            print(
                f"ERROR: --from-triage {from_triage} conflicts with "
                f"--expands-triage {expands_triage}; the anchor is ambiguous. "
                "Pass only one (or matching ids).",
                file=sys.stderr,
            )
            return 1
        item = _read_triage_item(project_root, from_triage)
        if item is None:
            print(
                f"ERROR: --from-triage {from_triage} not found in "
                f"{project_root / '.shipwright' / 'triage.jsonl'}",
                file=sys.stderr,
            )
            return 1
        # Warn (don't block — re-promoting a dismissed item is valid) when the
        # anchor isn't open: the WebUI hides non-open cards, so the CTA may not show.
        item_status = item.get("status")
        if item_status and item_status != "triage":
            print(
                f"WARNING: --from-triage {from_triage} has status "
                f"{item_status!r} (not an open triage item); the WebUI "
                "'Start Campaign' CTA may not surface on a non-open card.",
                file=sys.stderr,
            )
        expands_triage = from_triage  # promoting THIS item ⇒ it is the anchor
        if intent is None:
            intent = _seed_intent(item)

    if intent is None:
        print("ERROR: --intent is required (or pass --from-triage to seed it).",
              file=sys.stderr)
        return 1

    if args.branch_strategy == "independent":
        warnings = validate_independent_strategy(sub_iterates)
        for w in warnings:
            print(f"WARNING: {w}", file=sys.stderr)

    result = init_campaign(
        project_root,
        args.campaign_slug,
        intent,
        sub_iterates,
        args.branch_strategy,
        expands_triage=expands_triage,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
