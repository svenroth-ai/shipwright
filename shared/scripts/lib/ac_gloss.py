"""Plain-language glosses for the questions the operator answers.

A question about a new promise quotes the promise as the agent worded it, and the operator may not know every
technical word in it. ``shared/config/plain_language_glossary.json`` maps a jargon term to one everyday sentence;
when the promise contains a term, the question appends ONE parenthetical with the gloss (at most two terms, in order
of first appearance, each explained once). Deterministic: same text, same glossary, same gloss. Stdlib only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = ["gloss", "jargon_terms", "load_glossary"]

GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "config" / "plain_language_glossary.json"
MAX_GLOSSES = 2


def load_glossary(path: Path | None = None) -> dict[str, str]:
    """``{term: everyday sentence}``; an unreadable or malformed file gives an empty glossary (no gloss, never an error)."""
    try:
        terms = json.loads((path or GLOSSARY_PATH).read_text(encoding="utf-8")).get("terms")
    except (OSError, ValueError, AttributeError):
        return {}
    return {k.lower(): v for k, v in terms.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(terms, dict) else {}


def jargon_terms(text: str, glossary: dict[str, str] | None = None) -> list[str]:
    """The glossary terms that occur in ``text`` (whole word, case-insensitive), in order of first appearance."""
    terms = load_glossary() if glossary is None else glossary
    found = []
    for term in terms:
        m = re.search(rf"(?<![\w-]){re.escape(term)}(?:s|es)?(?![\w-])", text or "", re.IGNORECASE)
        if m:
            found.append((m.start(), term))
    return [t for _, t in sorted(found)]


def gloss(text: str, glossary: dict[str, str] | None = None) -> str:
    """`` (term: explanation; term: explanation)`` for the first terms of ``text``, or an empty string."""
    terms = load_glossary() if glossary is None else glossary
    parts = [f"{t}: {terms[t]}" for t in jargon_terms(text, terms)[:MAX_GLOSSES]]
    return f" ({'; '.join(parts)})" if parts else ""
