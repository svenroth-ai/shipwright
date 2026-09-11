"""A minimal HTML tag/attribute scanner shared by design-gate checks
(``design_gate_extras.py``'s #5 shared-chrome and #6 standalone-HTML gates).

A hand-rolled ``<[^>]+>`` tag regex is not quote-aware — a ``>`` inside an
earlier quoted value (``onclick="i => i"``) truncates the tag and drops
every attribute after it (external code review, PR #726 round 8). The
stdlib parser also gives duplicate attributes their correct FIRST-wins
resolution and skips comments/``<script>``/``<style>`` bodies rather than
parsing them as tags.
"""

from __future__ import annotations

from html.parser import HTMLParser

__all__ = ["parse_tags"]


class _TagAttrCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def handle_comment(self, data: str) -> None:
        # An interpreter-dependent comment-closing quirk can hide a real
        # tag inside malformed markup (e.g. `<!--><script src=...>...-->`,
        # external review, PR #726 round 8b) — rescan the comment body too
        # so the gate fails CLOSED rather than trusting the parser's idea
        # of where the comment ends.
        self.tags.extend(parse_tags(data))

    def _record(self, attrs: list[tuple[str, str | None]]) -> None:
        seen: dict[str, str] = {}
        for name, value in attrs:
            seen.setdefault(name.lower(), value or "")
        self.tags.append(seen)


def parse_tags(html: str) -> list[dict[str, str]]:
    """Every start tag in ``html`` as a lowercased attribute-name → value
    dict (duplicate attributes resolve FIRST-wins, per the HTML spec)."""
    parser = _TagAttrCollector()
    parser.feed(html)
    return parser.tags
