"""How a Triage Inbox entry is rendered to a terminal.

Extracted from ``tools/triage_cli.py`` when the deferred section arrived and
pushed that file past the 300-line budget. The CLI keeps argument parsing and
dispatch; everything about *how an entry looks on a TTY* lives here.

One rule governs the whole module: **nothing printed from a stored entry is
text this project controls.** Titles and details are built from workflow
names, branch names and PR titles that come off the code host; reasons are
typed by whoever made the decision, on either surface; and the file itself can
be hand-edited. So every field goes through :func:`safe_display` on its way
out. That is the escaping half of the guarantee — the *crowding* half (a
length cap, so one entry cannot push the rest out of a capped view) belongs to
the producers in ``github_triage``, which cap the detail line at write time.
"""

from __future__ import annotations

from .tty_sanitize import strip_control_chars, strip_control_chars_inline

NO_REASON = "(no reason recorded)"


def safe_display(value: object) -> str:
    """Coerce one single-line field to a string safe to print.

    The *inline* sanitizer, not the payload one: these fields occupy one line
    each in a line-oriented listing, so a stored newline would let whoever
    wrote the entry forge rows that look like other entries. Only the launch
    payload — multi-line by design — keeps its line breaks.
    """
    return strip_control_chars_inline(str(value))


def _fence_opener(payload: str) -> str:
    """Pick a fence opener long enough to contain ``payload``."""
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


def format_item(item: dict) -> str:
    """Render one OPEN entry: header, title, and its launch payload fenced.

    F31 (SECURITY): the list view prints straight to a TTY, and these fields
    can carry an attacker-influenceable GitHub workflow name or branch with
    embedded ESC/BEL — so every one of them goes through ``safe_display``, not
    just the title and the payload.
    """
    item_id = safe_display(item.get("id", ""))
    severity = safe_display(item.get("severity", ""))
    kind = safe_display(item.get("kind", ""))
    title = safe_display(item.get("title", ""))
    dedup_key = safe_display(item.get("dedupKey") or "")
    payload = item.get("launchPayload")
    # The stored value drives the placeholder branch below; the sanitized one
    # is only ever printed. Deciding on a display-massaged string would let a
    # rendering rule quietly change which branch a producer lands in.
    source = item.get("source", "")
    lines = [
        f"- {item_id}  severity={severity} kind={kind} "
        f"source={safe_display(source)}"
        + (f" dedupKey={dedup_key}" if dedup_key else ""),
        f"  title: {title}",
    ]
    if isinstance(payload, str) and payload.strip():
        clean = strip_control_chars(payload)
        fence = _fence_opener(clean)
        lines.append("  launch payload (copy into a new Claude session):")
        lines.append(f"  {fence}text")
        for line in clean.splitlines():
            lines.append(f"  {line}")
        lines.append(f"  {fence}")
    elif source == "github":
        lines.append("  [!] no launch payload — producer bug; please report")
    return "\n".join(lines)


def format_deferred(item: dict) -> str:
    """Render one DEFERRED entry — compactly, and without its launch payload.

    The payload is the "do this now" instruction, so reprinting it for items
    the operator explicitly parked would re-create the very crowding a capped
    view exists to avoid. The reason may be absent — the Command Center's
    snooze route makes it optional — in which case say so rather than printing
    a bare ``None``.
    """
    return (
        f"- {safe_display(item.get('id', ''))}  "
        f"severity={safe_display(item.get('severity', ''))} "
        f"kind={safe_display(item.get('kind', ''))} "
        f"source={safe_display(item.get('source', ''))}\n"
        f"  reason: {safe_display(item.get('statusReason') or NO_REASON)}\n"
        f"  title: {safe_display(item.get('title', ''))}"
    )
