#!/usr/bin/env python3
"""Render the markdown body for the bloat-check PR comment.

Reads:
- ``--base``    path to the base-branch baseline JSON
- ``--head``    path to the PR-branch baseline JSON
- ``--ratchet`` path to ``anti_ratchet_check --json`` output

Emits a structured markdown block on stdout — content is paths +
counts only (no file contents) per OpenAI review finding F12.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(p: Path) -> dict:
    if not p.is_file():
        return {"version": 1, "entries": []}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "entries": []}
    if not isinstance(doc, dict):
        return {"version": 1, "entries": []}
    return doc


def _index(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for entry in doc.get("entries", []):
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str):
            out[path] = entry
    return out


def _diff(base: dict[str, dict], head: dict[str, dict]) -> dict[str, list]:
    added: list[dict] = []
    removed: list[dict] = []
    changed: list[tuple[dict, dict]] = []
    for path, head_entry in sorted(head.items()):
        base_entry = base.get(path)
        if base_entry is None:
            added.append(head_entry)
        elif base_entry.get("current") != head_entry.get("current"):
            changed.append((base_entry, head_entry))
    for path, base_entry in sorted(base.items()):
        if path not in head:
            removed.append(base_entry)
    return {"added": added, "removed": removed, "changed": changed}


def _render(diff: dict[str, list], ratchet: dict) -> str:
    lines: list[str] = ["## Shipwright Bloat Check", ""]
    status = ratchet.get("status", "ok")
    if status == "block":
        lines.append("**Status:** :no_entry: ANTI-RATCHET BLOCK")
        lines.append("")
        lines.append("| Path | Baseline `current` | Measured |")
        lines.append("|---|---:|---:|")
        for r in ratchet.get("ratchets", []):
            lines.append(
                f"| `{r.get('path')}` | {r.get('baseline_current')} | "
                f"{r.get('measured')} |"
            )
        lines.append("")
    elif status == "skipped":
        lines.append("**Status:** :information_source: baseline missing — check skipped")
    else:
        lines.append("**Status:** :white_check_mark: no anti-ratchet violation")
    lines.append("")

    if diff["changed"]:
        lines.append("### Allowlist `current` changes")
        lines.append("")
        lines.append("| Path | Base | Head | Delta |")
        lines.append("|---|---:|---:|---:|")
        for old, new in diff["changed"]:
            old_c = old.get("current", 0)
            new_c = new.get("current", 0)
            lines.append(
                f"| `{new.get('path')}` | {old_c} | {new_c} | "
                f"{new_c - old_c:+d} |"
            )
        lines.append("")

    if diff["added"]:
        lines.append("### Added baseline entries")
        lines.append("")
        for e in diff["added"]:
            lines.append(
                f"- `{e.get('path')}` — limit {e.get('limit')}, "
                f"current {e.get('current')}, state `{e.get('state')}`"
            )
        lines.append("")

    if diff["removed"]:
        lines.append("### Removed baseline entries")
        lines.append("")
        for e in diff["removed"]:
            lines.append(f"- `{e.get('path')}`")
        lines.append("")

    new_crossings = ratchet.get("new_crossings", []) or []
    if new_crossings:
        lines.append("### New crossings (advisory — NOT blocking CI)")
        lines.append("")
        lines.append("| Path | Limit | Measured |")
        lines.append("|---|---:|---:|")
        for c in new_crossings:
            lines.append(
                f"| `{c.get('path')}` | {c.get('limit')} | "
                f"{c.get('current')} |"
            )
        lines.append("")
        lines.append(
            "These will be picked up by the Group H detective audit "
            "post-merge. Add to the baseline only via the "
            "`_template-bloat-exception.md` ADR path."
        )
        lines.append("")

    if (not diff["added"] and not diff["removed"]
            and not diff["changed"] and status == "ok" and not new_crossings):
        lines.append(
            "_No baseline changes vs base ref._"
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_bloat_diff")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--ratchet", required=True)
    args = p.parse_args(argv)

    base = _index(_load(Path(args.base)))
    head = _index(_load(Path(args.head)))
    ratchet_doc = _load(Path(args.ratchet))

    sys.stdout.write(_render(_diff(base, head), ratchet_doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
