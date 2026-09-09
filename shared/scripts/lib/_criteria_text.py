"""Bullet-line TEXT extraction for ``lib.fr_criteria`` — decoration
stripping, continuation-line joining, whitespace normalisation, placeholder
rejection.

Split out of ``fr_criteria.py`` (crossed the 300-line bloat-baseline
threshold adding ``strip_ac_marker`` — P3.4 doubt review, #689): this half
answers "what does one bullet's TEXT actually say", never "where in the
document is a block" (that stays in ``fr_criteria.py``, the only importer,
the same split ``_ac_blocks.py``/``_ac_markers.py`` already made for
``ac_identity.py``).
"""

from __future__ import annotations

import re
from typing import Iterable

from lib._ac_markers import strip_leading_ac_marker as _strip_leading_ac_marker

#: A criterion bullet: ``-``/``*``/``+`` or ``1.``/``1)``, incl. the ``- [ ]``
#: checkbox form ``fr-authoring.md`` §3's worked example uses.
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.*\S)\s*$")

#: Leading decoration stripped before a bullet's text is judged: a task
#: checkbox (``[ ]``/``[x]``) and the assertion marker (``(E)``) the house
#: style puts in front of "Given … when … then …".
_CHECKBOX = re.compile(r"^\[[ xX]\]\s*")
_ASSERTION_MARKER = re.compile(r"^\([A-Za-z]\)\s*")

#: Placeholder bodies meaning "not written yet", compared after stripping all
#: non-alphanumerics so ``TBD``, ``- [ ] TBA`` and ``N/A`` land on one token.
#: A bullet reduced to nothing (a bare ``- [ ]``) is likewise not a criterion.
_PLACEHOLDERS = frozenset({"tbd", "todo", "tba", "na", "none", "tbc"})

#: A single whole-line italic attribution, e.g. ``_Source: tests._`` —
#: `/shipwright-adopt`'s real per-FR shape (``spec_document.py:181-184``,
#: ``generate_adoption_artifacts.py:308``/``:376``). Tolerated by
#: ``fr_criteria._leading_bullet_run`` as the ONE exception to "first
#: non-blank line must be a bullet" (Stage-3 doubt review, high, 2026-08-25).
LEADING_ATTRIBUTION_RE = re.compile(r"^_[^_\n]+_\.?\s*$")


def _flush(out: list[str], current: list[str]) -> None:
    joined = " ".join(" ".join(current).split())
    core = re.sub(r"[^0-9a-z]+", "", joined.lower())
    if core and core not in _PLACEHOLDERS:
        out.append(joined)


def criteria_texts(lines: Iterable[str], *, strip_ac_marker: bool = True) -> list[str]:
    """The criteria in ``lines``, whitespace-normalised, continuation lines
    joined onto the bullet that opened them, placeholders dropped.

    A line indented under an open bullet extends it; a blank line or a line
    starting in column 0 ends it. Non-bullet lines before/between bullets are
    skipped, not treated as terminators — a body may carry prose (a
    ``**Description:**`` paragraph, an old ``**Acceptance Criteria:**``
    label) ahead of its bullets and still yield them.

    ``strip_ac_marker`` (default ``True``) strips a leading ``[ACnn]`` marker
    (``lib.ac_identity``'s minted id) as ordinary decoration, exactly like
    the checkbox/assertion marker beside it — one seam fixing every reader
    of this module rather than teaching each one the marker's shape (P3.4
    doubt review, #689; see ``fr_criteria``'s module docstring). Lenient by
    shape, not canonical validity. ``ac_identity.read()`` is the one caller
    that must still see the marker, so it passes ``False``.

    Stripping applies only to a bullet's OPENING line, never a continuation
    line (external review, 2026-09-09): ``_ac_blocks.insert_marker`` always
    splices ``[ACnn]`` onto the SAME physical line as the bullet's own text,
    so a real minted marker can never legitimately start a continuation
    line. Stripping there too would risk deleting a legitimate ``[AC03]``-
    shaped reference inside wrapped prose (e.g. a criterion that mentions
    another AC by id) — a live false positive traded for a shape ``mint()``
    never produces.
    """
    out: list[str] = []
    current: list[str] | None = None
    for line in lines:
        bullet = BULLET_RE.match(line)
        if bullet:
            if current is not None:
                _flush(out, current)
            text = _CHECKBOX.sub("", bullet.group("text")).strip()
            text = _ASSERTION_MARKER.sub("", text).strip()
            if strip_ac_marker:
                text = _strip_leading_ac_marker(text).strip()
            current = [text]
            continue
        if current is None:
            continue
        if not line.strip() or not line[:1].isspace():
            _flush(out, current)
            current = None
            continue
        current.append(line.strip())
    if current is not None:
        _flush(out, current)
    return out


__all__ = ["BULLET_RE", "LEADING_ATTRIBUTION_RE", "criteria_texts"]
