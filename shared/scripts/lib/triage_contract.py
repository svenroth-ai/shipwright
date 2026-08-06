"""The shape of `triage_cli.py list --json` — the cross-repo output contract.

Its own module for the same reason rendering got one: `triage_cli.py` keeps
argument parsing and dispatch, and everything about *what a consumer receives*
lives beside the version number that describes it. A reviewer asking "what does
the Command Center consume?" should have one file to read.

**Not the same contract as the stored wire format.** `triage.jsonl` is
versioned by its own header (`v`) and codified in
`shared/schemas/triage_item.schema.json`; that one did not break here. This is
the CLI's *output*, which did.

**Version 2** (iterate-2026-08-01-triage-defer-lifecycle) replaced a bare JSON
array of open entries with an envelope carrying `open` and `deferred`
separately. A parked entry had to become visible on this surface — the operator
decision of 2026-07-27 — and a flat array has no sections to put one in. The
break was taken deliberately with that cost accepted; the matching consumer
change in the Command Center repository is `trg-f2214310` in that repository's
triage store.

**One import edge accepted deliberately** (Stage-2 code review): this module now
imports `basename` from `lib.triage_integrity`, so the arrow points from the
contract layer into the store-reader layer. It buys one shared spelling for
"basename of a fragment path", which the JSON block and the stderr notice
previously computed two different ways — and they disagreed on a cross-platform
path. The tidier home is a `name` property on `CorruptFragment` itself, which
would need no edge at all; `jsonl_records.py` sits at exactly its 300-line limit,
so that is recorded as the next-touch move rather than done here.

**What v2's payload gained on 2026-08-06** (iterate-2026-08-06-p2-19c-corruption-absence),
recorded here because this file is meant to be the one file a reviewer reads:
every row gains `pendingStatusDelivery`, and the envelope gains two top-level
blocks, `corruption` and `undeliveredDecisions`.

`CONTRACT_VERSION` deliberately did NOT move, and the argument against that is
real enough to write down (Stage-3 doubt): the rule above exempts an *item*
gaining a field, while `corruption` is a new *envelope* key, and the envelope's
key set is exactly what v2 was minted to describe. **The decisive consequence a
consumer must know: `corruption.count > 0` means `open` and `deferred` may be
INCOMPLETE.** A v2-pinned consumer that ignores unknown keys will therefore render
an incomplete board as a complete one — this repo's own defect, relocated into the
Command Center. It stayed at 2 because bumping breaks that consumer immediately
and unconditionally for a field it does not yet read, which trades a silent risk
for a certain outage; the honest mitigation is this paragraph plus the operator
note in the run's F12 summary, not silence.

A consumer pinned to version 1 cannot read `contractVersion` before failing,
because it fails on the top-level type first. That is inherent to the shape
change and is why the break is announced in the changelog and the PR rather
than left to be discovered by a parse error. Inside this repository the only
executable consumers were this contract's own tests.
"""

from __future__ import annotations

from .triage_defer import sort_deferred
from .triage_integrity import basename, span_bytes

#: Bump when the SHAPE changes — not when an item gains a field.
CONTRACT_VERSION = 2

#: Corruption spans reported in the envelope. A deliberately malformed log must not
#: be able to inflate the response without bound; `truncated` reports the capping so
#: a bounded list can never be read as a complete one.
_CORRUPTION_CAP = 20

#: Undelivered-decision ids reported in the envelope. Same bounding rule; `count` is
#: always the true total, so a capped list can never read as a complete one.
_UNDELIVERED_CAP = 50


def _pending_delivery(item: dict, tracked_ids: set, outbox_ids: set) -> bool:
    """TRACKED-PREFERRED residence: an entry present in BOTH files is not
    pending (the tracked copy ships in the PR; the outbox copy is GC'd after
    delivery). Parallels `triage.mark_status`'s residence rule.

    Both id sets hold **append** events only, which is why this cannot answer the
    question `pendingStatusDelivery` answers — see `build_listing`.
    """
    item_id = item.get("id")
    return item_id in outbox_ids and item_id not in tracked_ids


def build_listing(
    open_items: list[dict],
    deferred_items: list[dict],
    *,
    tracked_ids: set,
    outbox_ids: set,
    severity_rank: dict,
    undelivered_status_ids: set,
    corruption: list,
) -> dict:
    """The full `list --json` payload.

    Both sections are COMPLETE. The display cap that the terminal listing and
    `triage_inbox.md` apply is deliberately NOT applied here: silently dropping
    rows from a consumer that has no way to know it happened is the exact
    failure this change exists to end.

    `deferred` is ordered by the same shared key the human surfaces sort by, so
    a consumer that chooses to show only the first few shows the same few.

    **Two independent delivery facts, deliberately not merged** (IT-1 audit
    finding 28, iterate-2026-08-06-p2-19c-corruption-absence):

    * `pendingDelivery` — the item's own APPEND has not reached the tracked store.
    * `pendingStatusDelivery` — the item's deciding STATUS event has not. This is
      the one that says *"your dismiss has not been committed"*. Nothing said it
      before: both id sets above contain only `append` events, so a buffered
      status flip was structurally invisible and the board rendered a decision
      still sitting in a gitignored file exactly like one that had shipped.
      Measured on the live store on 2026-08-06: 12 buffered flips, 11 invisible.

    **A per-row flag alone would have shipped AC5 half-built** (Stage-3 doubt, high).
    The dominant case is an item dismissed or promoted while its flip sat in the
    outbox: it resolves to a terminal status and leaves BOTH sections, so no row
    exists to carry the flag, and a consumer reading rows only would see "everything
    delivered" on a store with 12 buffered decisions. The human listing already had
    a store-level summary for exactly this reason; the machine contract now has the
    same fact as `undeliveredDecisions` — the envelope-level count, capped `ids`,
    and `truncated`. Without it the Command Center, the one consumer this field was
    built for, got the surface that structurally cannot show the defect.

    **`corruption` is the third fact, and it is about the STORE, not a row** (IT-1
    audit finding 22). A span the reader could not decode is not attached to any
    item — that is exactly what makes it dangerous, because an item that cannot be
    read is indistinguishable from an item that is not there. It therefore rides at
    the top level, carrying shape only (`path` basename, `line`, `bytes`) and never
    the undecodable text, which may hold arbitrary bytes. `truncated` says whether
    the list was capped, so a consumer can never mistake a bounded list for a
    complete one.

    **It is an advisory display, computed from a re-read.** `corruption` and
    `undelivered_status_ids` come from ONE pass (`triage_integrity.store_facts`), so
    they agree with each other — but that pass is still separate from the one
    `read_all_items` used for the rows, so on a store being written concurrently the
    spans and the rows can come from different snapshots. Threading a single
    `RecordRead` through the whole listing path was rejected because it would grow
    `triage.py`, which is pinned at its bloat baseline and cannot take a line.
    Recorded rather than left for a reader to discover (external plan review round 2;
    Stage-1 and Stage-2 reviews).

    `undelivered_status_ids` and `corruption` are REQUIRED keywords, not defaulted
    ones: an empty set and an empty list both read as reassuring, so a caller that
    forgot either would silently reinstate the defect it closes. `CONTRACT_VERSION`
    does NOT move — the rule for this file is that a bump signals a SHAPE change,
    and both sections keep their shape; rows gain one always-present boolean and
    the envelope gains one always-present list.
    """
    def enrich(seq: list[dict]) -> list[dict]:
        return [
            {**it,
             "pendingDelivery": _pending_delivery(it, tracked_ids, outbox_ids),
             "pendingStatusDelivery": it.get("id") in undelivered_status_ids}
            for it in seq
        ]

    shown = corruption[:_CORRUPTION_CAP]
    pending_ids = sorted(undelivered_status_ids)[:_UNDELIVERED_CAP]
    return {
        "contractVersion": CONTRACT_VERSION,
        "open": enrich(open_items),
        "deferred": enrich(sort_deferred(deferred_items, severity_rank)),
        "corruption": {
            "count": len(corruption),
            "truncated": len(corruption) > len(shown),
            "spans": [
                {"path": basename(f.path), "line": f.line_no, "bytes": span_bytes(f)}
                for f in shown
            ],
        },
        "undeliveredDecisions": {
            "count": len(undelivered_status_ids),
            "truncated": len(undelivered_status_ids) > len(pending_ids),
            "ids": pending_ids,
        },
    }
