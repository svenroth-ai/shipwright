"""Reading the converged shape: which scan state, and how the Basis cells score.

Two pure readers Group I delegates to, both added by campaign S5, both about
INTERPRETING what the shared reader returned rather than building findings. The
findings themselves stay in ``group_i`` — this module never constructs one.

Part one, the scan states, is below. Part two is ``basis_tally``.

---

**Why Group I found no rows — the SIX states that used to be one silent `skip`.**

Campaign "Requirements Catalog", sub-iterate S5. Group I reported a single
`skip` ("no FR rows found") for every reason it might have found none, and that
conflation is the shape of FV-2: zero rows read as green, so a spec the reader
could not understand was indistinguishable from a repo that has no spec yet.

S5's acceptance criterion, as amended by S4, requires three states. There are
six, and none is padding — each names a materially different repair, and every
one of them was at some point reported as one of the others:

======================  =====================================================
``no_spec``             no ``spec.md`` on disk. The only benign state.
``no_fr_rows``          a spec exists, but nothing in it is FR-shaped.
``no_governing_header`` FR ids are present, but no header names a Priority
                        column, so the reader has no table to read them under.
``no_canonical_ids``    a header WAS recognised — the table is well-formed —
                        but no row id is canonical ``FR-XX.YY``.
``rows_too_narrow``     header recognised AND ids canonical, but no row is
                        wide enough to reach its header's Priority column.
``all_rows_retired``    rows exist and parse, but every one sits under
                        ``### Removed Requirements``. Nothing is broken.
======================  =====================================================

**Two of the six were added after this module first shipped, and both for the
same reason: it reported the wrong cause.** An early cut branched on
``header_seen`` alone, but TWO reject reasons carry ``header_seen=True`` — so a
narrow row was reported as ``no_canonical_ids``, telling the operator to "fix the
ids (two digits either side)" about a row whose id was already canonical. And a
spec whose requirements are all retired reported ``no_fr_rows`` — "contains no
FR-shaped rows" — about a file that plainly contains them. A skip that names the
wrong cause is the same defect class as a skip that names none, which is what
this module exists to remove.

**The last state is the one that mattered.** S4's strict id rule (its rule 1)
creates it, and ADR-107, S4's own mini-plan and ``frozen_bugs.py`` FV-1 each
cited this acceptance criterion as the mitigation for it. It was not: in that
route the spec IS on disk and the header IS recognised, and only the ids fail,
so a two-state check ("no spec" vs "no header") reports the benign answer for
the dangerous case. A repo emitting ``FR-01.100`` — which
``generate_adoption_artifacts`` will do above 99 detected routes — audits as
though it had no requirements at all.

**Precedence is decided from raw parse facts, not from outcomes**, so one input
cannot classify two ways depending on evaluation order:

1. no spec file discovered                        → ``no_spec``
2. any ACTIVE row accepted                        → ``rows`` (the normal path)
3. a ``non_canonical_id`` reject under a header   → ``no_canonical_ids``
4. a ``row_narrower_than_header`` reject          → ``rows_too_narrow``
5. anything else rejected                         → ``no_governing_header``
6. rows parsed, but all retired                   → ``all_rows_retired``
7. nothing rejected either                        → ``no_fr_rows``

Rule 3 outranks the rest deliberately: when a repo shows several, the
well-formed table with unusable ids is the most specific and most actionable
finding, and it is the one that would otherwise stay hidden. Rules 3–5 (a
BROKEN table) outrank rule 6 (an intact but fully-retired one) because a parse
failure is a repair and a retirement is not.

``non_canonical_id`` is checked together with ``header_seen`` because that
reason alone is decided BEFORE the column map is consulted, so it occurs under
both a present and an absent header; the other two reasons each imply their own
header state and need no such pairing.

Nothing here is a *verdict*. Every state still reports ``skip`` — Group I is
detective-only and a repo without requirements must not redden CI. What changes
is that the ``detail`` now names which one happened, **and quotes only the ids
belonging to the reason that decided it** — pooling every declined id was itself
a way of naming the wrong cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The six no-rows states, plus the normal one.
STATE_ROWS = "rows"
STATE_NO_SPEC = "no_spec"
STATE_NO_FR_ROWS = "no_fr_rows"
STATE_NO_GOVERNING_HEADER = "no_governing_header"
STATE_NO_CANONICAL_IDS = "no_canonical_ids"
STATE_ROWS_TOO_NARROW = "rows_too_narrow"
STATE_ALL_ROWS_RETIRED = "all_rows_retired"

_DETAIL: dict[str, str] = {
    STATE_NO_SPEC:
        "no spec.md found under .shipwright/planning/<split>/ — nothing to audit",
    STATE_NO_FR_ROWS:
        "spec.md found, but it contains no FR-shaped rows — nothing to audit",
    STATE_NO_GOVERNING_HEADER:
        "spec.md contains FR ids but no table header naming a Priority column, "
        "so no row could be read as a requirement — fix the table header",
    STATE_NO_CANONICAL_IDS:
        "spec.md has a readable FR table, but no row id is canonical FR-XX.YY, "
        "so every row was declined — fix the ids (two digits either side)",
    STATE_ROWS_TOO_NARROW:
        "spec.md has a readable FR table with canonical ids, but no row is wide "
        "enough to reach the Priority column its own header declares — add the "
        "missing cells, or fix the header to match the rows",
    STATE_ALL_ROWS_RETIRED:
        "spec.md parses, but every FR row sits under '### Removed Requirements' "
        "— nothing is broken and nothing is left to lint",
}

#: Wording for when OTHER reject reasons are present too. The entries in
#: ``_DETAIL`` make a universal claim ("no row id is canonical", "no row is wide
#: enough") that is simply false once some rows failed differently, so the mixed
#: case gets its own sentence rather than a substring surgically removed from the
#: sole-cause one. A ``.replace()`` on that literal also silently no-ops the
#: moment anyone edits it, which makes the correction invisible rather than wrong.
_DETAIL_MIXED: dict[str, str] = {
    STATE_NO_CANONICAL_IDS:
        "spec.md has a readable FR table; some row ids are not canonical "
        "FR-XX.YY — fix the ids (two digits either side)",
    STATE_ROWS_TOO_NARROW:
        "spec.md has a readable FR table with canonical ids; some rows are not "
        "wide enough to reach the Priority column their header declares — add "
        "the missing cells, or fix the header to match the rows",
}

#: Which reject reasons justify each state, so the ``declined:`` list quotes only
#: the ids that actually caused it. Pooling every declined id told the operator to
#: "fix the ids" about a row whose problem was width.
#:
#: ``None`` means "every reject counts". ``no_governing_header`` is the rule-5
#: CATCH-ALL — it is reached by any leftover reject, including a
#: ``non_canonical_id`` one whose ``header_seen`` was False — so filtering it to
#: the single like-named reason matched nothing and the state stopped naming any
#: id at all. Narrowing attribution must not cost attribution.
_STATE_REASON: dict[str, frozenset[str] | None] = {
    STATE_NO_CANONICAL_IDS: frozenset({"non_canonical_id"}),
    STATE_ROWS_TOO_NARROW: frozenset({"row_narrower_than_header"}),
    STATE_NO_GOVERNING_HEADER: None,
}


@dataclass(frozen=True)
class SpecScan:
    """Rows read across every discovered spec, plus WHY there were none."""

    rows: list = field(default_factory=list)
    #: Rows the reader declined, with reasons — S4's accumulator, read here
    #: rather than re-derived. This is the same data the traceability manifest
    #: publishes as ``invalid_ids``; Group I reads it one hop earlier, straight
    #: from the reader, so there is no second interpretation to drift.
    rejects: list = field(default_factory=list)
    #: True when at least one spec.md was discovered on disk.
    any_spec: bool = False
    #: How many rows parsed but sit under ``### Removed Requirements``. Needed
    #: because ``rows`` is filtered to LIVE requirements, so an all-retired spec
    #: is indistinguishable from an empty one without it.
    retired_count: int = 0

    @property
    def state(self) -> str:
        if self.rows:
            return STATE_ROWS
        if not self.any_spec:
            return STATE_NO_SPEC
        # Branch on the REASON, not on `header_seen` alone. Two reasons carry
        # `header_seen=True`, so a `header_seen` test alone told the operator
        # "fix the ids (two digits either side)" for a row whose id is already
        # canonical and whose actual problem is width — a skip that names the
        # WRONG cause, in the machinery built to stop exactly that.
        if any(r.get("reason") == "non_canonical_id" and r.get("header_seen")
               for r in self.rejects):
            return STATE_NO_CANONICAL_IDS
        if any(r.get("reason") == "row_narrower_than_header" for r in self.rejects):
            return STATE_ROWS_TOO_NARROW
        if self.rejects:
            return STATE_NO_GOVERNING_HEADER
        # Rows parsed cleanly but every one is retired. Reported apart from
        # `no_fr_rows` because "contains no FR-shaped rows" is simply false
        # about a file that plainly contains them, and because the repair is
        # different: nothing is broken here.
        if self.retired_count:
            return STATE_ALL_ROWS_RETIRED
        return STATE_NO_FR_ROWS

    @property
    def detail(self) -> str:
        """A one-line explanation naming what was actually found."""
        if self.state not in _STATE_REASON:
            return _DETAIL.get(self.state, "")

        mixed = len({r.get("reason") for r in self.rejects}) > 1
        base = (_DETAIL_MIXED.get(self.state) if mixed else None) \
            or _DETAIL.get(self.state, "")

        # Only the ids declined for the reason(s) that DECIDED this state. A spec
        # can carry several at once, and quoting all of them under one
        # explanation is the wrong-cause defect again: "fix the ids … declined:
        # FR-01.01" about a canonical id whose problem was width. `None` means
        # the state is the catch-all, where every reject genuinely is a cause —
        # narrowing attribution must not cost attribution.
        reasons = _STATE_REASON[self.state]
        ids = sorted({str(r.get("id", "")) for r in self.rejects
                      if r.get("id") and (reasons is None or r.get("reason") in reasons)})
        if not ids:
            return base
        shown = ", ".join(ids[:5])
        more = f" (+{len(ids) - 5} more)" if len(ids) > 5 else ""
        # "other rows were declined for other reasons" is only true when the id
        # list is PARTIAL. For the catch-all state `reasons is None`, so the list
        # is already complete and the suffix would promise rows that do not
        # exist — the wrong-cause defect once more, this time by claiming an
        # omission rather than a cause.
        partial = mixed and reasons is not None
        suffix = "; other rows were declined for other reasons" if partial else ""
        return f"{base}; declined: {shown}{more}{suffix}"


def basis_tally(rows, classify) -> tuple[list[str], list[str]]:
    """Score declared ``Basis`` cells → ``(blocking, advisory)`` description lists.

    Severity is asymmetric by design (SPEC §3.2):

    * a value outside the vocabulary BLOCKS — a typo is not a special case;
    * ``other`` never blocks — an escape hatch that blocks is not one;
    * a **blank** cell blocks. ``fr_basis`` reports it as non-blocking because,
      as a matter of vocabulary, an absent value is not a typo — but a spec that
      DECLARED the column and left a cell empty is a row that declined to answer
      a required question, and ``assumed`` is always available as the honest
      answer. Only this side knows the column was declared, which is why the
      escalation lives here rather than in the vocabulary module.

    Rows are assumed pre-filtered to those under a declared ``Basis`` column.
    """
    blocking: list[str] = []
    advisory: list[str] = []
    for row in rows:
        verdict = classify(row.basis)
        if verdict.blocking:
            blocking.append(f"{row.id} ({row.basis!r}: {verdict.note})")
        elif verdict.kind == "empty":
            blocking.append(
                f"{row.id} (empty — write `assumed` if nobody has confirmed it)"
            )
        elif verdict.kind == "other":
            advisory.append(
                f"{row.id}{' — ' + verdict.note if verdict.note else ''}"
            )
    return blocking, advisory


__all__ = [
    "STATE_ALL_ROWS_RETIRED",
    "STATE_NO_CANONICAL_IDS",
    "STATE_NO_FR_ROWS",
    "STATE_NO_GOVERNING_HEADER",
    "STATE_NO_SPEC",
    "STATE_ROWS",
    "STATE_ROWS_TOO_NARROW",
    "SpecScan",
    "basis_tally",
]
