#!/usr/bin/env python3
"""Render `.shipwright/agent_docs/triage_inbox.md` from `.shipwright/triage.jsonl`.

AC-2: collapses history per id (last-status-wins by file order, see
triage.read_all_items), filters to status=="triage", sorts by
(severity_rank, originalTs DESC) for the top-50 cap, groups by source,
emits the promote-action hint per item.

Markdown escaping (MED-10 from external review): pipe, leading hash,
triple-backtick collapsed; long fields truncated.

Hook context: invoked from `shared/scripts/hooks/aggregate_triage_on_stop.py`
as the LAST Stop hook (after producers — see hooks.json ordering).

Usage:
    uv run shared/scripts/tools/aggregate_triage.py --project-root .
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import (  # noqa: E402
    SEVERITY_RANK,
    read_all_items,
    suggest_domain_from_source,
    suggest_priority_from_severity,
)

TRIAGE_MD_REL = Path(".shipwright") / "agent_docs" / "triage_inbox.md"

TOP_N = 50
FIELD_TRUNCATE_AT = 120


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_md(text: str) -> str:
    """Escape Markdown-active characters for inline rendering.

    - `|` → `\\|` so list-bullet rendering inside a future table column
      stays intact
    - leading `#` → `\\#` so a title starting with `#` isn't promoted to
      a heading
    - triple-backtick `` ``` `` collapses to a single backtick so a
      producer's prose can't escape into a code fence
    - newlines → space (single-line bullet rendering)
    """
    if text is None:
        return ""
    text = str(text)
    # collapse triple-backticks first (so the per-char escape doesn't
    # re-split them)
    text = text.replace("```", "`")
    text = text.replace("|", r"\|")
    # collapse newlines to spaces for the inline bullet
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if text.startswith("#"):
        text = "\\" + text
    return text


def _truncate(text: str, limit: int = FIELD_TRUNCATE_AT) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _render_item(item: dict) -> list[str]:
    """Render a single triage item as a markdown bullet group."""
    item_id = item.get("id", "")
    severity = item.get("severity", "")
    kind = item.get("kind", "")
    title = _truncate(_escape_md(item.get("title", "")))
    detail = _truncate(_escape_md(item.get("detail", "")))
    priority = item.get("suggestedPriority") or suggest_priority_from_severity(severity)
    domain = item.get("suggestedDomain") or suggest_domain_from_source(
        item.get("source", "")
    )
    evidence = _truncate(_escape_md(item.get("evidencePath") or ""))

    lines = [
        f"- **{title}** `id={item_id} | severity={severity} | kind={kind} → "
        f"{priority}/{domain}`",
        f"  - {detail}" if detail else "",
    ]
    if evidence:
        lines.append(f"  - Evidence: `{evidence}`")
    lines.append(
        f"  - Promote: `triage_promote.py --id {item_id} --task-ref EXT:<ref>`"
    )
    return [L for L in lines if L]


def _summary_counts(items: list[dict]) -> dict[str, int]:
    counts = {"total": len(items)}
    for status in ("triage", "promoted", "dismissed", "snoozed"):
        counts[status] = sum(1 for it in items if it.get("status") == status)
    return counts


def _sort_key(item: dict) -> tuple[int, str]:
    """Sort by severity_rank asc (critical first), originalTs desc (newest first)."""
    rank = SEVERITY_RANK.get(item.get("severity", "info"), 99)
    # Negate by reversing the ISO string — string sort works because
    # ISO-8601 is lexicographically ordered
    original_ts = item.get("originalTs") or item.get("ts") or ""
    # Tuple: lower rank first; for same rank, newer ts first → reverse-string
    return (rank, _reverse_iso(original_ts))


def _reverse_iso(ts: str) -> str:
    """Return a key that sorts newest-first within stable severity rank.

    Uses string complement trick: '9' - digit per char. Falls back to
    plain string if the input is malformed.
    """
    if not ts:
        return ""
    try:
        return "".join(
            str(9 - int(c)) if c.isdigit() else c
            for c in ts
        )
    except (TypeError, ValueError):
        return ts


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_markdown(items: list[dict], *, now: str) -> str:
    counts = _summary_counts(items)
    triage_items = [it for it in items if it.get("status") == "triage"]
    triage_items.sort(key=_sort_key)

    out: list[str] = []
    out.append("# Triage Inbox")
    out.append("")
    out.append(f"> Auto-generated {now}. Items waiting for triage decision.")
    out.append(
        "> Promote via WebUI Triage tab (when v1b lands) or "
        "`shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`."
    )
    out.append("")
    out.append("## Status summary")
    out.append("")
    out.append(f"- Total: {counts['total']}")
    out.append(
        "- Triage: {triage} | Promoted: {promoted} | "
        "Dismissed: {dismissed} | Snoozed: {snoozed}".format(**counts)
    )
    out.append("")

    if not triage_items:
        out.append("No triage items pending. ✓")
        out.append("")
        return "\n".join(out) + "\n"

    rendered = triage_items[:TOP_N]
    out.append(f"## Top {len(rendered)} items (severity-sorted)")
    out.append("")
    if len(triage_items) > TOP_N:
        out.append(
            f"_Showing first {TOP_N} of {len(triage_items)} pending; "
            "remainder elided._"
        )
        out.append("")

    # Group by source while preserving severity sort within each group
    by_source: dict[str, list[dict]] = {}
    for it in rendered:
        by_source.setdefault(it.get("source", "unknown"), []).append(it)

    # Source order: alphabetical for stable diffs
    for source in sorted(by_source.keys()):
        group = by_source[source]
        out.append(f"### Source: {source} ({len(group)} item{'s' if len(group) != 1 else ''})")
        out.append("")
        for it in group:
            out.extend(_render_item(it))
            out.append("")

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate triage.jsonl into triage_inbox.md")
    p.add_argument("--project-root", default=".", help="Project root (default: .)")
    p.add_argument(
        "--now",
        default=None,
        help="ISO-8601 'now' for the header (default: current UTC). "
             "Tests pass a fixed value for snapshot stability.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    now = args.now or (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    items = read_all_items(project_root)
    md = render_markdown(items, now=now)

    out_path = project_root / TRIAGE_MD_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    # Status line goes to stderr so the CLI is safe to invoke from a
    # Stop-hook (ADR-042: Stop accepts only JSON or empty on stdout).
    # When run interactively, operators still see this because the harness
    # surfaces stderr.
    sys.stderr.write(
        f"wrote {out_path} ({len(items)} items, "
        f"{sum(1 for it in items if it.get('status') == 'triage')} triage)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
