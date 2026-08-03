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

A consumer pinned to version 1 cannot read `contractVersion` before failing,
because it fails on the top-level type first. That is inherent to the shape
change and is why the break is announced in the changelog and the PR rather
than left to be discovered by a parse error. Inside this repository the only
executable consumers were this contract's own tests.
"""

from __future__ import annotations

from .triage_defer import sort_deferred

#: Bump when the SHAPE changes — not when an item gains a field.
CONTRACT_VERSION = 2


def _pending_delivery(item: dict, tracked_ids: set, outbox_ids: set) -> bool:
    """TRACKED-PREFERRED residence: an entry present in BOTH files is not
    pending (the tracked copy ships in the PR; the outbox copy is GC'd after
    delivery). Parallels `triage.mark_status`'s residence rule.
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
) -> dict:
    """The full `list --json` payload.

    Both sections are COMPLETE. The display cap that the terminal listing and
    `triage_inbox.md` apply is deliberately NOT applied here: silently dropping
    rows from a consumer that has no way to know it happened is the exact
    failure this change exists to end.

    `deferred` is ordered by the same shared key the human surfaces sort by, so
    a consumer that chooses to show only the first few shows the same few.
    """
    def enrich(seq: list[dict]) -> list[dict]:
        return [
            {**it, "pendingDelivery": _pending_delivery(
                it, tracked_ids, outbox_ids)}
            for it in seq
        ]

    return {
        "contractVersion": CONTRACT_VERSION,
        "open": enrich(open_items),
        "deferred": enrich(sort_deferred(deferred_items, severity_rank)),
    }
