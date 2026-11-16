"""A campaign unit's DECLARED complexity — the operator's floor.

The operator decides in the campaign brief that a unit is, say, ``medium``.
``campaign_init.py`` writes that decision into the unit's sub-iterate spec as one
explicit line::

    Complexity: medium

Both classification points read it back through this module — Stage 1
(``classify_complexity``) and the diff-driven Step 3.4 re-check
(``diff_risk_recheck``) — and apply it as a FLOOR: the diff may raise the tier,
never lower it. Before this module the declaration existed only as prose in the
brief, so a 113-178-line unit classified ``small`` and its plan, architecture and
doubt reviews were closed ``not_applicable``.

A spec with no such line (every hand-written or pre-existing unit) returns
``None``: today's behaviour is unchanged. The spec is read only from an explicit
``--spec`` path, never mined out of a free-text message, and only its HEADER (the
text before the first ``## `` heading, where the planner writes the line) is
searched, so Scope or Acceptance-Criteria prose can neither declare a floor nor
fail a unit. Standard library plus ``complexity_vocabulary`` only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from complexity_vocabulary import COMPLEXITY_ORDER  # noqa: E402

#: ``[^\S\n]`` is "any whitespace except a newline" (spaces and tabs).
_B = r"[^\S\n]*"

#: A declaring line, nothing else on it: optional list marker and bold, the key, a
#: colon, ONE word, optional trailing punctuation. A multi-word sentence such as
#: "Complexity: small changes are fine here" never matches, so prose is not a floor.
_DECLARING_LINE = re.compile(
    rf"^{_B}(?:[-*][^\S\n]+)?\**{_B}complexity{_B}\**{_B}:{_B}\**{_B}"
    rf"([A-Za-z0-9_-]+)([.!;,]*)\**{_B}$",
    re.IGNORECASE | re.MULTILINE,
)

#: The header ends at the first level-2 heading.
_BODY_START = re.compile(r"^## ", re.MULTILINE)


def parse_declared_complexity(text: str | None) -> str | None:
    """The unit's declared level (lowercase), or ``None`` when it declares none.

    The FIRST declaring line in the header decides. If it is not a clean level
    (``Complexity: mediun``, ``Complexity: medium.``) this raises ``ValueError``:
    dropping a typo silently would switch the floor off, recreating the bug this
    module closes, and a later valid line must not paper over it.
    """
    if not text:
        return None
    header = _BODY_START.split(text, maxsplit=1)[0]
    match = _DECLARING_LINE.search(header)
    if match is None:
        return None
    word, punctuation = match.group(1).lower(), match.group(2)
    if word in COMPLEXITY_ORDER and not punctuation:
        return word
    raise ValueError(
        f"declared complexity {match.group(1) + punctuation!r} is not one of "
        f"{COMPLEXITY_ORDER}; fix the Complexity line in the unit spec"
    )


def read_declared_complexity(spec_path: str | Path | None) -> str | None:
    """:func:`parse_declared_complexity` over a spec file.

    ``None`` when no path is given (nothing to consult). A path that was given but
    cannot be read raises ``OSError``/``UnicodeDecodeError``: a mistyped or
    shell-split ``--spec`` must stop the caller, never silently drop the floor.
    """
    if not spec_path:
        return None
    return parse_declared_complexity(Path(spec_path).read_text(encoding="utf-8-sig"))


def apply_floor(level: str, declared: str | None) -> str:
    """``max(level, declared)`` by tier rank — never by string order."""
    if declared is None:
        return level
    return max(level, validate_declared(declared), key=COMPLEXITY_ORDER.index)


def validate_declared(value: object) -> str:
    """Return the canonical level or raise ``ValueError`` (campaign planner input)."""
    level = str(value).strip().lower()
    if level not in COMPLEXITY_ORDER:
        raise ValueError(f"complexity {value!r} is not one of {COMPLEXITY_ORDER}")
    return level
