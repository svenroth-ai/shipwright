#!/usr/bin/env python3
"""Render `.shipwright/agent_docs/triage_inbox.md` from `.shipwright/triage.jsonl`.

Collapses history per id (last-status-wins by file order, see
``triage.read_all_items``), renders open items by source under the existing
top-50 rule, and renders still-parked items in their own capped section with
revisit date, reason, and un-park hint. Expired parks already resolve as open in
the reader, so every surface receives the same effective status.

Untrusted Markdown text is HTML-escaped and CommonMark punctuation is
backslash-escaped; code spans choose a delimiter longer than stored backtick
runs. Long fields are truncated.

Hook context: invoked from `shared/scripts/hooks/aggregate_triage_on_stop.py`
as the LAST Stop hook (after producers — see hooks.json ordering).

Usage:
    uv run shared/scripts/tools/aggregate_triage.py --project-root .
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.events_log import latest_event_dt  # noqa: E402
from lib.triage_render import clip as _truncate  # noqa: E402
from lib.triage_render_md import code_span as _code_span, escape_md as _escape_md  # noqa: E402
from lib.triage_render_md import render_deferred_markdown  # noqa: E402
from lib.tty_sanitize import strip_control_chars as _strip_control_chars  # noqa: E402

from triage import (  # noqa: E402
    SEVERITY_RANK,
    read_all_items,
    suggest_domain_from_source,
    suggest_priority_from_severity,
)

_AGENT_DOCS_DIRNAME = ".shipwright/agent_docs"
TRIAGE_MD_REL = Path(_AGENT_DOCS_DIRNAME) / "triage_inbox.md"
TRIAGE_MD_FILENAME = "triage_inbox.md"

TOP_N = 50

# `_escape_md` and `_truncate` moved to `lib/triage_render*` in
# iterate-2026-08-01-triage-defer-lifecycle and are imported above under their
# old local names. Two reasons, both load-bearing: this file is at its ADR-090
# ceiling and the deferred section it now renders had to be paid for, and the
# TTY renderer already carried a byte-identical clip under a different name —
# one function means the two views of one record cannot drift apart.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fence_opener(payload: str) -> str:
    """Pick a backtick-fence opener long enough to contain ``payload``.

    Standard markdown idiom: if the payload contains a run of N backticks,
    the fence must use at least N+1 backticks so the payload can never
    accidentally close the fence. Minimum 3 (the usual ``` ``` ```` opener).
    """
    longest = 0
    run = 0
    for ch in payload:
        if ch == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return "`" * max(3, longest + 1)


def _render_launch_payload(item: dict) -> list[str]:
    """Render the ``launchPayload`` block for one item, if applicable.

    Three cases (iterate-2026-05-20-triage-launch-surface):

    - Non-empty string → emit fenced code block (operator copy-pastes
      the fence content into a new Claude session). Terminal control
      chars are stripped before rendering (review finding #10 + LOW #6).
    - Source ``"github"`` AND payload empty/null → visible loud-failure
      placeholder (review finding #13: a github action-unit MUST carry
      a payload; missing one is a producer regression that should
      surface, not silently degrade).
    - Anything else (legacy producer omitting the kwarg) → no fence,
      no placeholder. Render exactly as today.
    """
    payload = item.get("launchPayload")
    source = item.get("source", "")
    if isinstance(payload, str) and payload.strip():
        clean = _strip_control_chars(payload)
        fence = _fence_opener(clean)
        return [
            "  - Launch payload (copy into a new Claude session):",
            f"    {fence}text",
            *(f"    {line}" for line in clean.splitlines()),
            f"    {fence}",
        ]
    if source == "github":
        return [
            "  - > [no launch payload — producer bug; please report]",
        ]
    return []


def _render_item(item: dict) -> list[str]:
    """Render a single triage item as a markdown bullet group.

    Each item starts with an HTML anchor `<a id="trg-XXX"></a>` so external
    artifacts — primarily the compliance RTM (`traceability-matrix.md`) —
    can deep-link straight to a card via standard markdown anchors
    (`[FAIL → trg-XXX](triage_inbox.md#trg-XXX)`). VS Code's preview, GitHub,
    and CommonMark all honor this. Iterate B0 (2026-05-21).
    """
    item_id = str(item.get("id") or "")
    anchor_id = html.escape(
        _strip_control_chars(item_id).replace("\r", " ").replace("\n", " "),
        quote=True,
    )
    severity = item.get("severity", "")
    source = item.get("source", "")
    kind = item.get("kind", "")
    # F31: escape_md owns control/newline stripping plus Markdown/HTML escaping.
    title = _truncate(_escape_md(item.get("title", "")))
    detail = _truncate(_escape_md(item.get("detail", "")))
    safe_severity = severity if isinstance(severity, str) and severity in SEVERITY_RANK else "info"
    priority = item.get("suggestedPriority") or suggest_priority_from_severity(safe_severity)
    domain = item.get("suggestedDomain") or suggest_domain_from_source(
        source if isinstance(source, str) else ""
    )
    evidence = _truncate(_strip_control_chars(str(item.get("evidencePath") or "")))
    metadata = (
        f"id={item_id} | severity={severity} | kind={kind} → "
        f"{priority}/{domain}"
    )
    lines = [
        f'<a id="{anchor_id}"></a>' if item_id else "",
        f"- **{title}** {_code_span(metadata)}",
        f"  - {detail}" if detail else "",
    ]
    if evidence:
        lines.append(f"  - Evidence: {_code_span(evidence)}")
    lines.extend(_render_launch_payload(item))
    command = f"triage_promote.py --id {item_id} --task-ref EXT:<ref>"
    lines.append(f"  - Promote: {_code_span(command)}")
    return [L for L in lines if L]


def _split_info_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition items into (signal, info-noise).

    Iterate B0 — pragmatism dial for solo dev: `info`-severity items are
    rarely actionable on their own (they describe drift / observability /
    informational findings). Surface them collapsed so the top of the inbox
    only shows critical/high/medium/low cards. `info` items still render in
    a ``<details>`` block at the end so they're not lost — just out of the
    way.
    """
    signal: list[dict] = []
    info: list[dict] = []
    for it in items:
        (info if it.get("severity") == "info" else signal).append(it)
    return signal, info


def _summary_counts(items: list[dict]) -> dict[str, int]:
    counts = {"total": len(items)}
    for status in ("triage", "promoted", "dismissed", "snoozed"):
        counts[status] = sum(1 for it in items if it.get("status") == status)
    return counts


def _sort_key(item: dict) -> tuple[int, str]:
    """Sort by severity_rank asc (critical first), originalTs desc (newest first)."""
    severity = item.get("severity", "info")
    rank = SEVERITY_RANK.get(severity, 99) if isinstance(severity, str) else 99
    # Reverse the ISO string; ISO-8601 is lexicographically ordered.
    original_ts = item.get("originalTs") or item.get("ts") or ""
    return (rank, _reverse_iso(original_ts))


def _reverse_iso(ts: object) -> str:
    """Return a key that sorts newest-first within stable severity rank.

    Uses string complement trick: '9' - digit per char. Falls back to
    plain string if the input is malformed.
    """
    if not isinstance(ts, str) or not ts:
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
    # A park whose revisit date has arrived already resolved to `triage` in
    # `read_all_items`, so it is in the list above; what remains here is the
    # genuinely-still-parked set.
    deferred_items = [it for it in items if it.get("status") == "snoozed"]

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
        # Still emitted: "nothing open" and "nothing at all" are different
        # answers, and showing a parked entry as a bare count in the summary
        # above is exactly what made a deferred finding read as gone.
        out.extend(render_deferred_markdown(deferred_items, SEVERITY_RANK))
        return "\n".join(out) + "\n"

    # Info-severity items are collapsed into a <details> block at the end
    # (Iterate B0). Sort key is already applied to the full list, so the
    # partition keeps each bucket pre-sorted.
    signal_items, info_items = _split_info_items(triage_items)

    rendered = signal_items[:TOP_N]
    if rendered:
        out.append(f"## Top {len(rendered)} items (severity-sorted)")
        out.append("")
        if len(signal_items) > TOP_N:
            out.append(
                f"_Showing first {TOP_N} of {len(signal_items)} pending; "
                "remainder elided._"
            )
            out.append("")

        # Group by source while preserving severity sort within each group
        by_source: dict[str, list[dict]] = {}
        for it in rendered:
            source = str(it.get("source") or "unknown")
            by_source.setdefault(source, []).append(it)

        # Source order: alphabetical for stable diffs
        for source in sorted(by_source.keys()):
            group = by_source[source]
            heading = _escape_md(source)
            out.append(
                f"### Source: {heading} "
                f"({len(group)} item{'s' if len(group) != 1 else ''})"
            )
            out.append("")
            for it in group:
                out.extend(_render_item(it))
                out.append("")
    else:
        # All open items are info-severity — keep the header so the file
        # structure stays stable for grep / diff tooling.
        out.append("No non-info triage items pending. ✓")
        out.append("")

    if info_items:
        out.append(
            f"<details><summary>Info-level items ({len(info_items)}) — "
            "expand to view</summary>"
        )
        out.append("")
        for it in info_items:
            out.extend(_render_item(it))
            out.append("")
        out.append("</details>")
        out.append("")

    out.extend(render_deferred_markdown(deferred_items, SEVERITY_RANK))

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
    p.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Override output directory (default: <project-root>/"
            ".shipwright/agent_docs). The Stop hook passes "
            "<project-root>/.shipwright/agent_docs/runtime to keep the "
            "live aggregation out of the tracked snapshot. Constrained "
            "to be under --project-root for write-safety."
        ),
    )
    return p.parse_args(argv)


def _resolve_render_now(project_root: Path) -> str:
    """Banner timestamp derived from events.jsonl, not wall-clock.

    See iterate-2026-05-22-deterministic-render-timestamps — using
    `datetime.now()` caused the rendered triage_inbox.md banner to drift
    on every Stop hook. The `--now` CLI arg still overrides this for
    tests and scaffold scripts that need a fixed snapshot value.
    """
    dt = latest_event_dt(project_root)
    if dt is None:
        return "(no events)"
    return dt.isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    now = args.now or _resolve_render_now(project_root)

    items = read_all_items(project_root)
    md = render_markdown(items, now=now)

    # Resolve and constrain --out-dir per external review #10
    # (write-safety: refuse paths that escape project_root).
    if args.out_dir:
        from lib.artifact_paths import ensure_path_within_project_root  # noqa: E402

        candidate = Path(args.out_dir)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        try:
            out_dir = ensure_path_within_project_root(candidate, project_root)
        except ValueError as exc:
            sys.stderr.write(f"--out-dir rejected: {exc}\n")
            return 2
        out_path = out_dir / TRIAGE_MD_FILENAME
    else:
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
