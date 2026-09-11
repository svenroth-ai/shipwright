#!/usr/bin/env python3
"""Screen registry for shipwright-design.

Tracks generated screens, user flows, and uploaded assets.
Reads/writes ``.shipwright/designs/design-manifest.md`` (caller passes
the canonical directory; this module is parameter-driven).

Usage:
    uv run screen_registry.py list --designs-dir <path>

A screen links to the requirement(s) it implements via an
``<!-- Requirements: FR-01.02, FR-01.05 -->`` HTML comment near the top of
its own file (see ``parse_screen_linked_frs``) — mirroring the plan phase's
``Requirements:`` section field. There is no ``add --frs`` CLI subcommand;
an earlier draft of this docstring advertised one, but the comment
convention above is what ``main()`` and every caller actually use.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


_NON_UI_FRS_SECTION_RE = re.compile(r"(## Non-UI FRs\s*\n.*?)(?=\n## |\Z)", re.DOTALL)

# FR-01.04 #1 / #4 — a screen names the requirement(s) it implements via an
# HTML comment near the top of the file, mirroring the plan phase's
# `Requirements:` section field (`plan_section_quality.py`). Before this, a
# screen's `linked_frs` was never populated anywhere — `generate_manifest`
# always rendered an empty "Linked FRs" cell, so the compliance C1 gate
# (`check_design_fr_coverage`) had no data to compare against for any real
# project, and the same gap made the design phase's own in-session
# FR-Coverage Gate (`review-loop.md` Option A) unenforceable too.
_SCREEN_REQUIREMENTS_RE = re.compile(
    r"<!--\s*Requirements:\s*(?P<ids>[^>]*?)\s*-->", re.IGNORECASE
)
_FR_ID_RE = re.compile(r"^FR-\d{1,3}\.\d{1,3}$")


def parse_screen_linked_frs(html_path: Path) -> list[str]:
    """Read the ``<!-- Requirements: FR-01.02, FR-01.05 -->`` comment out of
    a generated screen/flow HTML file. Returns ``[]`` if the file is
    unreadable or carries no such comment — a screen predating this
    convention is simply unlinked, not an error."""
    try:
        content = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    match = _SCREEN_REQUIREMENTS_RE.search(content)
    if not match:
        return []
    ids: list[str] = []
    for token in match.group("ids").split(","):
        fr = token.strip()
        if _FR_ID_RE.match(fr) and fr not in ids:
            ids.append(fr)
    return ids


def _read_existing_non_ui_frs_section(manifest_path: Path) -> str | None:
    """Return the verbatim ``## Non-UI FRs`` section from an existing
    manifest, or None if there is no existing manifest or no such section.

    ``generate_manifest`` rebuilds the manifest wholesale from a disk scan
    (screens/flows/uploads) and has no way to derive this section itself —
    it is a hand-authored, ADR-cited waiver. Without round-tripping it here,
    every regeneration silently dropped it and the C1 FR->screen gate
    (`check_design_fr_coverage`) flipped red with no trace of why
    (trg-44f49504). The boundary regex mirrors
    `design_screens_parser.parse_non_ui_frs`'s section match so both readers
    agree on where the section starts and ends.
    """
    if not manifest_path.exists():
        return None
    match = _NON_UI_FRS_SECTION_RE.search(manifest_path.read_text(encoding="utf-8"))
    return match.group(1).rstrip() if match else None


@dataclass
class ScreenEntry:
    number: int
    name: str
    file: str
    status: str = "pending"
    linked_frs: list[str] = field(default_factory=list)
    entry_type: str = "screen"  # screen, flow, upload


def scan_designs_dir(designs_dir: Path) -> dict:
    """Scan a designs directory (canonical: ``.shipwright/designs``) and return inventory."""
    result = {"screens": [], "flows": [], "uploads": []}

    screens_dir = designs_dir / "screens"
    if screens_dir.is_dir():
        for f in sorted(screens_dir.iterdir()):
            if f.suffix == ".html":
                match = re.match(r"^(\d{2})-(.+)\.html$", f.name)
                if match:
                    result["screens"].append({
                        "number": int(match.group(1)),
                        "name": match.group(2),
                        "file": f"screens/{f.name}",
                        "status": "complete",
                        "linked_frs": parse_screen_linked_frs(f),
                    })

    flows_dir = designs_dir / "flows"
    if flows_dir.is_dir():
        for f in sorted(flows_dir.iterdir()):
            if f.suffix == ".html":
                result["flows"].append({
                    "name": f.stem,
                    "file": f"flows/{f.name}",
                    "status": "complete",
                })

    uploads_dir = designs_dir / "uploads"
    if uploads_dir.is_dir():
        for f in sorted(uploads_dir.iterdir()):
            if f.suffix in (".html", ".png", ".jpg", ".jpeg", ".svg", ".pdf", ".md"):
                entry = {
                    "name": f.name,
                    "file": f"uploads/{f.name}",
                    "type": f.suffix[1:],
                    "integrated": False,
                }
                # Detect visual guidelines
                if f.suffix == ".md":
                    content = f.read_text(encoding="utf-8").lower()
                    if "visual guideline" in content or "design token" in content or "color system" in content:
                        entry["is_visual_guidelines"] = True
                result["uploads"].append(entry)

    # Check for generated visual guidelines
    guidelines_path = designs_dir / "visual-guidelines.md"
    result["has_visual_guidelines"] = guidelines_path.exists()
    if guidelines_path.exists():
        result["visual_guidelines_path"] = "visual-guidelines.md"

    return result


def generate_manifest(designs_dir: Path, project_name: str = "", profile_name: str = "") -> str:
    """Generate design-manifest.md content from directory scan.

    Round-trips an existing ``## Non-UI FRs`` section (see
    `_read_existing_non_ui_frs_section`) — the only hand-authored section in
    an otherwise fully-derived file.
    """
    inventory = scan_designs_dir(designs_dir)
    non_ui_frs_section = _read_existing_non_ui_frs_section(designs_dir / "design-manifest.md")

    lines = [
        "# Design Manifest",
        "",
        f"> Generated by shipwright-design | Profile: {profile_name}",
        "",
    ]

    # Screens
    lines.append("## Screens")
    lines.append("")
    if inventory["screens"]:
        lines.append("| # | Screen | File | Status | Linked FRs |")
        lines.append("|---|--------|------|--------|-----------|")
        for s in inventory["screens"]:
            frs = ", ".join(s.get("linked_frs") or []) or "none"
            lines.append(f"| {s['number']:02d} | {s['name']} | {s['file']} | {s['status']} | {frs} |")
    else:
        lines.append("No screens generated yet.")
    lines.append("")

    # Non-UI FRs (hand-authored; round-tripped verbatim, see above)
    if non_ui_frs_section:
        lines.append(non_ui_frs_section)
        lines.append("")

    # Flows
    lines.append("## User Flows")
    lines.append("")
    if inventory["flows"]:
        lines.append("| Flow | File | Status |")
        lines.append("|------|------|--------|")
        for f in inventory["flows"]:
            lines.append(f"| {f['name']} | {f['file']} | {f['status']} |")
    else:
        lines.append("No user flows generated yet.")
    lines.append("")

    # Uploads
    if inventory["uploads"]:
        lines.append("## Uploads")
        lines.append("")
        lines.append("| File | Type | Integrated |")
        lines.append("|------|------|-----------|")
        for u in inventory["uploads"]:
            lines.append(f"| {u['name']} | {u['type']} | {'yes' if u['integrated'] else 'no'} |")
        lines.append("")

    return "\n".join(lines)


def write_manifest(designs_dir: Path, project_name: str = "", profile_name: str = "") -> Path:
    """Write design-manifest.md to the designs directory."""
    content = generate_manifest(designs_dir, project_name, profile_name)
    manifest_path = designs_dir / "design-manifest.md"
    manifest_path.write_text(content, encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen registry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("list")
    p.add_argument("--designs-dir", required=True)

    p = subparsers.add_parser("write-manifest")
    p.add_argument("--designs-dir", required=True)
    p.add_argument("--project-name", default="")
    p.add_argument("--profile-name", default="")

    args = parser.parse_args()
    designs_dir = Path(args.designs_dir).resolve()

    if args.command == "list":
        result = scan_designs_dir(designs_dir)
        print(json.dumps(result, indent=2))

    elif args.command == "write-manifest":
        path = write_manifest(designs_dir, args.project_name, args.profile_name)
        print(json.dumps({
            "success": True,
            "path": str(path),
            "inventory": scan_designs_dir(designs_dir),
        }, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
