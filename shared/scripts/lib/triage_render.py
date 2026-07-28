"""How a Triage Inbox entry is rendered to a terminal.

Extracted from ``tools/triage_cli.py`` when the deferred section arrived and
pushed that file past the 300-line budget. The CLI keeps argument parsing and
dispatch; everything about *how an entry looks on a TTY* lives here.

One rule governs the whole module: **nothing printed from a stored entry is
text this project controls.** Titles and details are built from workflow
names, branch names and PR titles that come off the code host; reasons are
typed by whoever made the decision, on either surface; and the file itself can
be hand-edited. So every field goes through :func:`safe_display` on its way
out, and the row's open/deferred token is emitted at a FIXED position before
any stored field — a marker searched for anywhere in the row would be forgeable
by a `source` or `dedupKey` containing it.

The *crowding* half is split by surface: the ``github_triage`` producers cap
the stored ``detail`` at write time, and this module caps the ONE-LINE fields
of both blocks at display time — the same three-field, same-value rule the
sibling renderer ``aggregate_triage`` already applies, so the two TTY-facing
views of one record agree on crowding as well as on escaping. The launch-payload
fence is deliberately exempt: it is multi-line by design and a one-line cap
would misrepresent it.

What the display cap adds over the writers: nothing for a Command-Center write
(that route caps a reason at the same 500) and nothing for a producer's
``detail``. It bounds a **hand-edited file** and any direct ``mark_status``
caller — neither of which validates anything — which is the threat this
module's first paragraph already assumes.
"""

from __future__ import annotations

from .tty_sanitize import (
    is_visually_empty,
    strip_control_chars,
    strip_control_chars_inline,
)

NO_REASON = "(no reason recorded)"

#: Token every row carries, immediately after the bullet and before any stored
#: field. The section header alone was not enough: before the deferred section
#: existed, every line starting `- trg-` meant an OPEN entry and both a reader
#: and a script could rely on it. Marking only the deferred rows would not fix
#: that either — `source` and `dedupKey` are attacker-influenceable (a dedup key
#: is built from a workflow's display name), so a token merely *contained* in
#: the row can be forged by an open entry. Classify by prefix, never by search.
OPEN_MARK = "[open] "
DEFERRED_MARK = "[deferred] "

#: Per-field render cap for the one-line free-text fields of BOTH blocks
#: (`source`, `dedupKey`, `title`, `statusReason`). Same value as the sibling
#: renderer's
#: `aggregate_triage.FIELD_TRUNCATE_AT`; the cut is also `rstrip`ped the same
#: way, so a cut landing on a space does not render as "… …". `id`, `severity`
#: and `kind` are NOT clipped: they are closed vocabularies validated on append
#: (`triage.py`), so clipping them would only disguise a hand-edited file.
FIELD_MAX_LEN = 120


def _clip(text: str) -> str:
    """Truncate only what exceeds the cap, marking where the cut happened."""
    if len(text) <= FIELD_MAX_LEN:
        return text
    return text[: FIELD_MAX_LEN - 1].rstrip() + "…"


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
    title = _clip(safe_display(item.get("title", "")))
    payload = item.get("launchPayload")
    # Both of these STORED values drive a branch below; only their sanitized
    # copies are ever printed. Deciding on a display-massaged string would let
    # a rendering rule quietly change which branch an entry lands in — a
    # dedupKey of nothing but control characters collapses to "" and would
    # silently suppress the field.
    source = item.get("source", "")
    dedup_key = item.get("dedupKey") or ""
    lines = [
        f"- {OPEN_MARK}{item_id}  severity={severity} kind={kind} "
        f"source={_clip(safe_display(source))}"
        + (f" dedupKey={_clip(safe_display(dedup_key))}" if dedup_key else ""),
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
    """Render one DEFERRED entry — compactly, marked, and capped.

    The launch payload is omitted: it is the "do this now" instruction, so
    reprinting it for items the operator explicitly parked would re-create the
    very crowding a capped view exists to avoid.

    Two rules the first version got wrong:

    - The ``NO_REASON`` fallback is decided AFTER sanitising, and on whether
      anything VISIBLE survives (`is_visually_empty`) rather than on
      truthiness. A reason of ``"   "`` — or of one zero-width space — is
      truthy but renders blank, so falling back first printed an empty
      ``reason:`` line. Reachability, stated precisely because an earlier
      version of this docstring got it wrong: the Command Center's route
      **does** validate (same control-char class, same 500-char cap) and
      normalises a whitespace-only reason to ``null`` — so what it can produce
      is the ABSENT case. A blank-but-present reason arrives from a direct
      ``mark_status`` caller or a hand-edited file, which validate nothing.
      Both must read the same to the operator.
    - The row itself carries ``DEFERRED_MARK``. A section header printed once
      is not a property of the row, and rows here are otherwise shaped exactly
      like open ones.
    """
    shown = safe_display(item.get("statusReason") or "")
    reason = NO_REASON if is_visually_empty(shown) else shown
    return (
        f"- {DEFERRED_MARK}{safe_display(item.get('id', ''))}  "
        f"severity={safe_display(item.get('severity', ''))} "
        f"kind={safe_display(item.get('kind', ''))} "
        f"source={_clip(safe_display(item.get('source', '')))}\n"
        f"  reason: {_clip(reason)}\n"
        f"  title: {_clip(safe_display(item.get('title', '')))}"
    )
