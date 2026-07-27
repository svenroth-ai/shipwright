"""The canon frontmatter block at the top of ``.shipwright/agent_docs/session_handoff.md``.

Written by ``tools/generate_session_handoff.py --canon-marker``; it records which
run last generated the handoff, so a later reader can tell "this run wrote it"
from "something else did".

Two consumers depend on that answer and must agree on it exactly:

* ``hooks/generate_handoff_on_stop.py`` — skips regeneration when the marker names
  the current run, so a session-end handoff cannot clobber a canon one.
* ``tools/verifiers/handoff_freshness.py`` — the F11 check that the handoff names
  the run currently finishing.

The parser used to be a private copy inside the Stop hook. It moved here in
iterate-2026-07-27-name-the-blocker when the verifier became the second reader:
two implementations of one format drift, and here they would drift on the meaning
of "fresh". Semantics are carried over verbatim — only a top-of-file block that
declares ``canon_generated: true`` counts.
"""

from __future__ import annotations

import re

#: The frontmatter block itself — anchored at the very start of the file so a
#: fenced YAML sample further down can never be read as the marker.
_CANON_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

#: One ``key: value`` line, with optional surrounding quotes on the value.
_CANON_FIELD_RE = re.compile(r'^(?P<key>[a-z_]+):\s*"?(?P<value>[^"\n]*?)"?\s*$')


def parse_canon_frontmatter(content: str) -> dict[str, str] | None:
    """Return the parsed canon frontmatter dict, or ``None``.

    Only returns a dict if the top-of-file block is present AND it contains
    ``canon_generated: true``. Anything else (no frontmatter, manual YAML for
    other purposes, malformed) is treated as "no canon marker — regenerate as
    normal". Unparsable lines inside an otherwise valid block are skipped rather
    than failing the whole read.
    """
    m = _CANON_FRONTMATTER_RE.match(content)
    if not m:
        return None
    parsed: dict[str, str] = {}
    for line in m.group(1).splitlines():
        fm = _CANON_FIELD_RE.match(line)
        if fm:
            parsed[fm.group("key")] = fm.group("value")
    if parsed.get("canon_generated", "").lower() != "true":
        return None
    return parsed


__all__ = ["parse_canon_frontmatter"]
