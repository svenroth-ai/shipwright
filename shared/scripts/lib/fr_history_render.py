"""Rendering the FR change-history answer for a human (campaign S7).

Split from ``tools/fr_history.py`` so neither module crosses the size limit, and
because the split is real: the tool owns argument parsing, exit codes and the
JSON contract; this owns what a person sees.

**Body text is written as one logical string and wrapped at runtime.** The
alternative — hand-breaking each sentence across adjacent string literals inside
a list of display lines — produces exactly the shape a genuinely missing comma
takes, on operator-facing output where silently merging two lines is the defect
class this whole change is about. CodeQL flagged seven instances of it; the
intent was correct in all seven, which is precisely why the shape had to go
rather than be annotated.
"""

from __future__ import annotations

from lib.fr_change_history import STATUS_NO_CHANGES

def _ascii(text: str) -> str:
    """Render safely on a legacy-codepage stderr.

    stdout is pinned to UTF-8; stderr deliberately is not, so everything written
    there must survive cp1252. Non-ASCII is escaped rather than dropped, so a
    mistyped id is still recognisable in the message that rejects it.
    """
    return text.encode("ascii", "backslashreplace").decode("ascii")


def _render_text(history, coverage) -> str:
    # ``history.fr_id`` is already folded: argv is sanitised once at main()'s
    # entry, and every field off the log is sanitised in
    # ``fr_change_history._clean``. Nothing reaching this renderer is raw.
    lines = [f"# {history.fr_id} — recorded changes", ""]

    if history.status == STATUS_NO_CHANGES:
        lines.append("No recorded changes.")
        lines.append("")
        if history.existence_verified:
            # Only claim the requirement exists when that was actually checked.
            # Printing it unconditionally is the positive-claim-over-an-empty-set
            # shape this module exists to remove — and it contradicted the NOTE
            # rendered a few lines below for the very same query.
            lines += _para(
                "This requirement exists and no completed change in the event"
                " log names it."
            )
        else:
            lines += _para(
                "No completed change in the event log names this id — and"
                " whether the id names a real requirement could NOT be checked"
                " (see the note below)."
            )
        lines += _para(
            "That is an answer, not a failure — but note the coverage below"
            " before reading it as 'this capability never changed'."
        )
    else:
        if not history.in_catalog:
            lines += _para(
                "This id is not a live requirement in the catalog — it was"
                " retired or folded. Its recorded history is still shown below."
            )
            lines.append("")
        lines.append(f"{len(history.changes)} recorded change(s), oldest first:")
        lines.append("")
        for i, c in enumerate(history.changes, 1):
            date = c.ts[:10] or "(no date)"
            mark = "+" if c.relation == "introduced" else "~"
            lines.append(f"{i:>3}. {mark} {date}  {c.label}")
            if c.summary:
                lines.append(f"        {_wrap(c.summary)}")
            detail = []
            if c.spec_impact:
                detail.append(f"impact={c.spec_impact}")
            if c.commit:
                detail.append(f"commit={c.commit[:12]}")
            if detail:
                lines.append(f"        ({', '.join(detail)})")
        lines += ["", "  + introduced this requirement   ~ affected it"]

    lines += ["", "## Coverage"]
    if coverage.work_events:
        pct = 100.0 * coverage.fr_linked_events / coverage.work_events
        lines.append(
            f"{coverage.fr_linked_events} of {coverage.work_events} recorded "
            f"changes name any requirement ({pct:.0f}%)."
        )
        lines += _para(
            "(Share of this tree's event log at the moment it was read, not an"
            " audited figure.) The rest are recorded as behaviour-preserving or"
            " pre-date the requirement link, so this list is what the log can"
            " prove, not everything that ever happened."
        )
        if coverage.fr_linked_events < coverage.work_events:
            lines.append("")
            lines += _para(
                "Changes this cannot account for are still recoverable — they"
                " are in the commit history and in the planning document that"
                " produced them:"
            )
            lines.append("")
            # Verbatim, never wrapped: a reader copies this line.
            lines.append("    git log --all --grep '<FR-id or feature name>'")
    else:
        lines.append("No completed changes are recorded in this tree's event log.")

    if history.corrupt_fragments:
        lines.append("")
        lines += _para(
            f"WARNING: {history.corrupt_fragments} unreadable fragment(s) in the"
            f" event log were skipped. Some change may be missing from this"
            f" answer for that reason rather than because it never happened."
            f" Run tools/triage_repair.py-style inspection on the log."
        )

    if not history.existence_verified:
        lines.append("")
        lines += _para(
            "NOTE: no requirements could be read from .shipwright/planning/, so"
            " this id was not checked for existence. A typo would look the same"
            " as an empty history here."
        )
    return "\n".join(lines)


#: Display width for wrapped prose. Body text is written as ONE logical string
#: and wrapped here at runtime.
#:
#: The alternative — hand-breaking each sentence across adjacent string literals
#: inside a list of display lines — produces exactly the shape a genuinely
#: missing comma takes, on operator-facing output where a silent merge of two
#: lines is the defect class this whole change is about. CodeQL flagged seven
#: instances; the intent was correct in all seven, which is precisely why the
#: shape had to go rather than be annotated.
_WIDTH = 78


def _fold(text: str, width: int) -> list[str]:
    """Greedy word-wrap. One logical string in, display lines out."""
    out: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        out.append(cur)
    return out


def _para(text: str, width: int = _WIDTH) -> list[str]:
    """A paragraph of body text as display lines."""
    return _fold(text, width)


def _wrap(text: str, width: int = 68) -> str:
    """Soft-wrap a summary onto continuation lines aligned under the entry.

    Shares :func:`_fold` with :func:`_para` so there is one wrapping rule; only
    the indent and width differ.

    Sanitising happens at the BOUNDARY (``fr_change_history._clean``), which is
    what makes every rendered field safe rather than only the one that happened
    to pass through here. The ``split()`` inside ``_fold`` is therefore about
    wrapping, not defence — an older comment claiming it was the newline guard
    described a protection that covered exactly one of the six fields rendered.
    """
    return "\n        ".join(_fold(text, width))
