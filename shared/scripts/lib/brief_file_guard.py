"""Run-route guard for ``brief_intake``: an explicit brief FILE that cannot be used is refused.

Split out of ``brief_intake.py`` (300-LOC bloat guideline). ``load_brief`` degrades an unreadable
explicit file to ``None`` = the legacy interview; on the run route that silently swaps a
pre-delivered brief for an unanchored interview, so the CLI refuses instead. ``/shipwright-adopt``
calls ``intake`` without ``package`` and keeps the degrade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

# A document someone meant as the brief, not a description (a PDF cannot be read as text).
DOC_SUFFIXES = frozenset({".pdf", ".doc", ".docx", ".rtf", ".odt", ".pptx", ".xlsx", ".csv", ".html", ".htm"})
_SHORT_PATH_WORDS = 3  # "my notes v2.pdf" is a file name; "Build a dashboard for sales.csv" is prose


def _path_like(path_str: str) -> bool:
    if "\n" in path_str:
        return False
    return (any(c in path_str for c in "/\\") or not any(c.isspace() for c in path_str)
            or len(path_str.split()) <= _SHORT_PATH_WORDS)


def refusal(source, load_brief: Callable, brief_suffixes) -> Optional[dict]:
    """``None`` when ``source`` is usable or is not a file reference at all."""
    text = source.strip() if isinstance(source, str) else ""
    if not text or text.startswith("{"):
        return None
    path_str = text[1:] if text.startswith("@") else text
    suffix = Path(path_str).suffix.lower()
    shaped = _path_like(path_str)
    file_like = text.startswith("@") or (shaped and suffix in (set(brief_suffixes) | DOC_SUFFIXES))
    unsupported = suffix not in brief_suffixes  # load_brief would read a bare .pdf path as the description text
    if not file_like or (not unsupported and load_brief(source) is not None):
        return None
    why = (f"unsupported suffix {suffix or '(none)'!r} (supported: {sorted(brief_suffixes)})"
           if unsupported else "not a readable file within the size limit")
    return {"refused": True, "code": "brief_unreadable", "has_brief": False,
            "message": f"brief file {path_str!r} cannot be used: {why}. It is NOT replaced by the interview: "
                       "fix the file, or start the run without --brief to interview on purpose.",
            "issues": [why]}
