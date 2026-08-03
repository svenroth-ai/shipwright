"""The parked-entry lifecycle: when a park expires, and who may close one.

`triage_cli.py defer` records that a finding is real but deliberately not now.
Until iterate-2026-08-01-triage-defer-lifecycle almost nothing downstream
honoured that: the finding re-appeared as a NEW open entry on the next import,
never closed when the problem went away, and was invisible to every surface but
the terminal listing. This module holds the rules that fixed it.

**The park expires by DERIVATION, not by a writer.** A parked entry names the
day it should come back, and `read_all_items` resolves it as open from that day
on. Nothing appends a second event, because a park expiring is not a decision
anybody made and the append-only log records decisions. The alternative — a
sweep that materialises the expiry — was rejected in the mini-plan: it needs
something to run it, and every surface stays wrong until it does.

**Scope, deliberately narrow** (external plan review, round 4): this module
holds *lifecycle policy* — the status vocabularies, strict date parsing, the
expiry overlay, and the deferred ordering. It holds no formatting and no
escaping; terminal rendering lives in `lib/triage_render.py`, while Markdown-
specific escaping lives in `lib/triage_render_md.py`. It must not become a
"defer miscellany" module: a new policy value
belongs here, a new way of printing one does not.

**No import of `triage`.** `triage.py` reaches this module lazily through
`shared_lib_loader` (ADR-045), so importing back would be circular. That is why
`sort_deferred` takes the severity rank as an argument instead of reading
`triage.SEVERITY_RANK` — the caller already has it, and one shared sort helper
is what stops two independently-written renderers disagreeing at the cap.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

#: Wire key for the day a parked entry should return, on the `snoozed` status
#: event. Accepted ONLY on that status — `triage.mark_status` refuses it
#: elsewhere and the JSON schema encodes the same rule — so a malformed or
#: hostile status event cannot acquire park semantics (AC-19a).
REVISIT_FIELD = "revisitAt"

#: Resolved-view key: has this entry's park expired? Computed, never stored.
#: Present on EVERY item (defaulting False), like `statusBy` / `statusReason` /
#: `promotedTaskId` already are, so a typed consumer meets one shape. It exists
#: so no consumer has to parse a date to learn whether an entry is back.
DUE_FIELD = "revisitDue"

#: The statuses a background producer may close when its finding disappears.
#:
#: `snoozed` is in here because of the operator decision of 2026-07-27: "a
#: parked entry closes automatically when its underlying finding disappears,
#: exactly like an open one". Read together with `expected_status`, that has a
#: consequence worth stating plainly rather than leaving to be discovered: a
#: person who PARKS or RE-PARKS an entry in the window between a producer's
#: unlocked read and its write no longer stops the close. The producer knows
#: something the parker did not — the finding is gone. A person who DISMISSES
#: or PROMOTES in that window is still protected, because neither status is
#: here; that is the `trg-93ceb2b0` guarantee, and it is intact for every
#: decision that ends an entry's life.
AUTO_RESOLVABLE_STATUSES = ("triage", "snoozed")

#: What `defer` accepts. `snoozed` is present so an entry can be RE-parked with
#: a corrected date; without it a mistyped date could only be fixed by
#: un-parking first. `dismissed` and `promoted` are refused — reversing those
#: is not what parking is for.
DEFERRABLE_STATUSES = ("triage", "snoozed")

#: What `unpark` accepts. Judged on the EFFECTIVE status, so an entry whose
#: park already expired is refused as already open rather than being handed a
#: pointless second event.
UNPARKABLE_STATUSES = ("snoozed",)

#: How many parked entries the two HUMAN surfaces print before eliding the
#: rest. Smaller than `aggregate_triage.TOP_N` (50) on purpose: that cap
#: governs the primary open list, while this section is secondary and prints
#: after it. The machine contract (`list --json`) is NEVER capped — silently
#: dropping rows from a consumer that cannot tell it happened is the exact
#: failure this whole change exists to end.
DEFERRED_TOP_N = 20

_DATE_LEN = len("YYYY-MM-DD")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

#: Sorts after every known severity. A hand-edited severity must not jump the
#: queue ahead of a real critical just because the rank map has never heard of
#: it.
_UNKNOWN_SEVERITY_RANK = 1_000


def now_utc() -> datetime:
    """The one clock read in the lifecycle — aware, UTC.

    Called once at the store boundary and passed down, so every expiry question
    in a single read is decided by the SAME instant. Reading a clock per item
    would let one entry be due and its neighbour not, inside one operation,
    purely because the UTC day turned over mid-read.
    """
    return datetime.now(timezone.utc)


def utc_date(stamp: datetime) -> date:
    """Return the UTC calendar day for one aware instant.

    Public store callers may hold an aware instant in another timezone.  The
    lifecycle boundary is UTC, so using that instant's local ``date()`` would
    reopen a park early or late.  A naive datetime has no unambiguous instant
    and is refused rather than being guessed as local or UTC.
    """
    if not isinstance(stamp, datetime):
        raise TypeError("now must be a datetime")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return stamp.astimezone(timezone.utc).date()


def parse_revisit_date(raw: object) -> date | None:
    """Exactly `YYYY-MM-DD`, or ``None``.

    Strict on purpose. A permissive ISO parser accepts `2026-09-01T00:00:00Z`,
    surrounding whitespace and unpadded components, which would let the CLI's
    stated promise and the stored classification drift apart. Every rejection
    lands in the same place: `None`, meaning "no readable date", which
    :func:`is_due` treats as not due.
    """
    if (
        not isinstance(raw, str)
        or len(raw) != _DATE_LEN
        or _DATE_PATTERN.fullmatch(raw) is None
    ):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_due(raw: object, today: date) -> bool:
    """Has a park named for ``raw`` come due as of ``today``?

    **A park named for day D is due from 00:00:00 UTC on D** — `today >= D`, so
    the entry is open ON the named day, not the day after. An operator who says
    "bring this back on the first" means the first. The cost, accepted and
    documented rather than modelled: someone west of UTC sees the entry return
    up to ~14 hours before their local midnight. A backlog park has no sub-day
    meaning, so no timezone model is introduced.

    An unreadable or missing value is **not** due. That is the conservative
    direction: a damaged date must not silently re-open an entry, and must not
    silently bury one either — it stays parked, listed, and reversible.
    """
    parsed = parse_revisit_date(raw)
    return parsed is not None and today >= parsed


def is_auto_resolvable(status: object) -> bool:
    """May a producer close this status when its finding disappears?"""
    return status in AUTO_RESOLVABLE_STATUSES


def resolve_revisit(item: dict, *, today: date) -> dict:
    """Return one resolved-view copy with park expiry overlaid."""
    resolved = dict(item)
    parked = resolved.get("status") == "snoozed"
    raw = resolved.get(REVISIT_FIELD) if parked else None
    resolved[REVISIT_FIELD] = raw
    due = parked and is_due(raw, today)
    resolved[DUE_FIELD] = due
    if due:
        resolved["status"] = "triage"
    return resolved


def apply_revisit_expiry(items: list[dict], *, today: date) -> list[dict]:
    """Overlay the effective status on an already-resolved view.

    Every item gains :data:`REVISIT_FIELD` and :data:`DUE_FIELD`; a `snoozed`
    item whose date has come reads `triage`. Only `snoozed` is ever rewritten —
    a `dismissed` entry carrying a stale date is not dragged back open by it.

    Reading stays PURE: each result is a copy, and re-reading the file still
    finds the last event for an expired entry to be `snoozed`, which keeps
    stored and effective state distinguishable.

    An expired park keeps its revisit date, and an un-parked entry has none —
    so the two open-looking cases stay apart without a `storedStatus` field.
    """
    return [resolve_revisit(item, today=today) for item in items]


def suppresses_reimport(
    item: dict,
    *,
    source: str,
    dedup_key: str | None,
    commit: str | None,
    match_commit: bool,
    cutoff: float | None,
) -> bool:
    """Does one resolved item suppress this producer re-import?"""
    status = item.get("status")
    if not is_auto_resolvable(status):
        return False
    if item.get("source") != source or item.get("dedupKey") != dedup_key:
        return False
    if match_commit and item.get("commit") != commit:
        return False
    if status == "snoozed" or item.get(DUE_FIELD) is True:
        return True
    if cutoff is None:
        return True
    original_ts = item.get("originalTs") or item.get("ts") or ""
    if not isinstance(original_ts, str):
        return True
    try:
        stamp = datetime.fromisoformat(original_ts.replace("Z", "+00:00"))
        return stamp.timestamp() >= cutoff
    except (ValueError, TypeError, OverflowError):
        return True


def sort_deferred(items: list[dict], severity_rank: dict) -> list[dict]:
    """Order parked entries for display — a TOTAL order, so nothing can tie.

    Soonest return first, then entries with no readable date, then by severity
    (critical first, unknown last), then by id. The last key is what makes it
    total: without it, "the first N" is whatever order the union reader
    happened to produce, and an operator would see a different subset from one
    run to the next over unchanged data.

    Returns a new list; the caller's is untouched. The severity rank is passed
    in rather than imported — see the module header on the `triage` cycle.
    """
    def key(item: dict) -> tuple:
        parsed = parse_revisit_date(item.get(REVISIT_FIELD))
        severity = item.get("severity")
        rank = (
            severity_rank.get(severity, _UNKNOWN_SEVERITY_RANK)
            if isinstance(severity, str) else _UNKNOWN_SEVERITY_RANK
        )
        return (
            parsed is None,                     # dated entries first
            parsed or date.min,                 # then soonest
            rank,
            str(item.get("id") or ""),
        )

    return sorted(items, key=key)
