"""Does one acceptance criterion match the prescribed shape? (Group I — I7)

``shared/fr-authoring.md`` §3b (added iterate-2026-09-06-fr-hygiene-touched-rows)
prescribes ``- (E) Given ... when ... then ...`` for a testable criterion —
already the house style used correctly throughout `shared/glossary.md` and
`shared/requirement-elicitation.md`, and already what
``references/path-a-feature.md``'s own MODIFY step asks authors to write. Until
now nothing checked it: ``lib.fr_criteria`` (I6's reader) verifies a criterion
EXISTS and is not a bare placeholder, never that it is in shape — a full prose
paragraph describing test status, exactly the leadwright failure mode this
check exists for, counted as "has criteria" with nothing to say it read wrong.

**Deliberately its own module, not a growth of ``fr_criteria.py``.** That
module is the single shared reader three other gates depend on (S5's
FR-coherence check, the cross-layer hard gate, I6) and sits at its own 300-line
budget; shape-judging one already-extracted criterion string is a narrower,
independent question that never needs to touch how criteria are FOUND. Kept
separate on purpose (Stage-1 spec review) so tightening the shape rule can
never accidentally touch ``criteria_texts``/``has_criteria``, which those three
other gates depend on staying exactly as permissive as they are today.

Pure: no I/O. Takes an already-extracted criterion string (e.g. from
``fr_criteria.criteria_for``), never a document.
"""

from __future__ import annotations

import re

#: The prescribed shape: ``Given ... when ... then ...``, case-insensitive, the
#: three keywords in order, each a whole word (so "whenever" / "thenceforth"
#: never match). The leading ``(E)`` marker is ALREADY stripped by
#: ``fr_criteria.criteria_texts`` before a caller ever sees the text — a
#: well-formed criterion is judged on the sentence, not the marker.
_GIVEN_WHEN_THEN_RE = re.compile(
    r"\bgiven\b.*?\bwhen\b.*?\bthen\b", re.IGNORECASE | re.DOTALL,
)


def is_well_formed_criterion(text: str) -> bool:
    """True when ``text`` (one already-extracted criterion) is in the
    prescribed ``Given ... when ... then ...`` shape.

    Empty/whitespace-only text is never well-formed — it is not a placeholder
    a caller need special-case (``fr_criteria`` already drops those before a
    criterion reaches this function), but a defensive default is still
    correct for any other empty input.
    """
    return bool(text and _GIVEN_WHEN_THEN_RE.search(text))


__all__ = ["is_well_formed_criterion"]
