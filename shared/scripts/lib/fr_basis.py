"""``Basis`` — the closed provenance vocabulary that replaces ``Source``.

Campaign "Requirements Catalog", sub-iterate S5, implementing decision D3 and
SPEC §3.2. ``Source`` held a file path: it answered *where we looked*, which is
implementation detail, and it could not be checked because any string was a legal
path. ``Basis`` answers *how we know this*, from a fixed set, so it can be.

| Value       | Meaning                                    |
|-------------|--------------------------------------------|
| `interview` | a human told us                            |
| `code`      | read from source                           |
| `observed`  | seen in the running application            |
| `tests`     | derived from existing tests                |
| `assumed`   | **nobody confirmed this — needs checking** |
| `other`     | special case; free-text reason requested   |

``assumed`` is the load-bearing value. Its whole job is to stop a guess from
later reading as established fact — the §6.5 laundering risk — which is also why
the layers convergence in this same sub-iterate marks inferred cells rather than
writing bare values.

**Severity is deliberately asymmetric** (SPEC §3.2):

* a value outside the vocabulary is a **hard** error — that is a typo, and a typo
  is not a special case;
* ``other`` is **advisory and never blocks** — it is the escape hatch for a real
  special case, and an escape hatch that fails closed is not one;
* ``other`` with no reason is still only advisory. §3.2 defines the hard class as
  "neither in the vocabulary nor ``other``", and a missing reason does not move a
  value out of the vocabulary. It is reported in the advisory detail instead, so
  the nag is visible without being a gate.

Pure: no I/O, no globals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The concrete values. ``other`` is handled apart — it is the escape hatch, not
#: a peer, and folding it in here would let a caller treat the two as one class.
BASIS_VALUES: tuple[str, ...] = ("interview", "code", "observed", "tests", "assumed")
BASIS_OTHER = "other"

#: The full vocabulary, for messages and for producers.
BASIS_VOCABULARY: tuple[str, ...] = (*BASIS_VALUES, BASIS_OTHER)

#: ``other`` optionally followed by its reason: ``other — legacy import``,
#: ``other - x``, ``other: x``, ``other (x)``. The separator is generous on
#: purpose: rejecting a well-meant reason over a dash-vs-colon choice would push
#: authors back to the bare form, losing the very text we are asking for.
#:
#: The reason group is GREEDY and trimmed in Python rather than by a lazy
#: ``.*?`` between two ``\s*`` runs. That pairing is ambiguous — every space can
#: be claimed by either side — which is the shape that turns a long
#: whitespace-heavy cell into superlinear backtracking. One unambiguous match
#: plus a ``strip()`` is the same result with no such edge.
_OTHER_RE = re.compile(r"^other\b[\s—–\-:(]*(?P<reason>.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class BasisVerdict:
    """How one ``Basis`` cell scored.

    ``kind`` is one of ``known`` / ``other`` / ``malformed`` / ``empty``.
    ``blocking`` is the single fact callers act on, so the severity rule lives
    here once instead of being re-decided at each gate.
    """

    kind: str
    value: str
    reason: str = ""
    note: str = ""

    @property
    def blocking(self) -> bool:
        return self.kind == "malformed"


def classify(cell: str) -> BasisVerdict:
    """Score one raw ``Basis`` cell against the vocabulary.

    An empty cell is ``empty``, which this module reports as non-blocking —
    **but that verdict is contextual and the caller owns the context.** As a
    matter of vocabulary an absent value is not a typo. As a matter of a spec
    that has *declared* a ``Basis`` column, a blank cell is a row that declined
    to answer a required question, and ``assumed`` is always available as the
    honest answer, so Group I escalates it (see ``group_i._basis_finding``).
    Only the consumer knows whether the column was declared, which is why the
    rule lives there and not here.
    """
    raw = cell.strip().strip("`*_")
    if not raw:
        return BasisVerdict("empty", "")

    low = raw.lower()
    if low in BASIS_VALUES:
        return BasisVerdict("known", low)

    if (match := _OTHER_RE.match(raw)) is not None:
        reason = (match.group("reason") or "").strip().rstrip(")").strip()
        return BasisVerdict(
            "other", BASIS_OTHER, reason,
            "" if reason else "no reason given",
        )

    # A known value carrying a qualifier — `code (enrichment.json)`,
    # `observed - staging`. Still malformed: only `other` takes a reason, and
    # letting `code (…)` through re-opens the door D3 closed, because the
    # qualifier authors reach for first is the file path `Basis` replaced. But
    # "not in the vocabulary" is a useless thing to tell someone who used a
    # vocabulary word, so this case names what is actually wrong.
    head = re.split(r"[\s—–\-:(]", low, maxsplit=1)[0]
    if head in BASIS_VALUES:
        return BasisVerdict(
            "malformed", raw, "",
            f"`{head}` takes no qualifier — write a bare `{head}`, or use "
            f"`other: <reason>` if the detail is essential",
        )

    return BasisVerdict(
        "malformed", raw, "",
        f"not in the vocabulary ({', '.join(BASIS_VOCABULARY)})",
    )


__all__ = [
    "BASIS_OTHER",
    "BASIS_VALUES",
    "BASIS_VOCABULARY",
    "BasisVerdict",
    "classify",
]
