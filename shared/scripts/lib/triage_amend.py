"""The `amend` event: vocabulary, validation, event-building, and the pass-2
overlay applied to a resolved triage item.

iterate-2026-08-08-triage-amend-event (trg-b310add8 / P2.46). A card's
`title`/`detail`/`severity`/`kind` can be corrected in place — id stable —
instead of dismiss-and-refile. NOT amendable: `source`, `dedupKey`, `runId`,
`evidencePath`, `commit`, `launchPayload`, `frId`, `suiteId`, `eventId`,
`status` (status stays exclusively a `status` event). See the iterate spec's
Decision 1 for the reasoning, including why `kind` does NOT recompute
`suggestedDomain` (that derives from `source`, which is not amendable).

**Deliberately a PURE leaf: stdlib only, no intra-package imports** — same
reasoning as `lib.triage_delivery`. `severities`/`kinds`/`priority_from_severity`
are passed in by the caller (which already has them via `lib.triage_fields`)
rather than imported here, so this module needs neither `triage` nor
`triage_fields` and stays trivially loadable by `shared_lib_loader`'s path
fallback (ADR-045).

**Whole-event validation, never partial application.** `validate_amend_event`
checks every field PRESENT on a raw event; if any present field is invalid,
the caller skips the WHOLE event (mirrors the existing convention for a
damaged `status` event — see `triage.read_all_items` pass 2). A field ABSENT
from an amend is simply not applied, leaving the target unchanged — the two
are different questions and must not be conflated.
"""

from __future__ import annotations

#: Fields an `amend` event may correct. `read_all_items` pass 1 initializes
#: none of these specially — they already exist as append fields; this
#: module only says which of them a LATER amend may overwrite.
AMENDABLE_FIELDS = ("title", "detail", "severity", "kind")

#: Resolved-item keys carrying who/when the item was last amended, mirroring
#: `statusBy`/`statusReason` for `status` events.
AMENDED_BY_FIELD = "amendedBy"
AMENDED_AT_FIELD = "amendedAt"


def has_amend_content(raw: dict) -> bool:
    """True iff `raw` carries at least one amendable field.

    The schema's own `anyOf` encodes this on the wire; this is the same rule
    checked in Python, by both the writer (refuses to emit a contentless
    amend) and the corruption boundary (refuses to recover one during
    resync — a key-complete-but-contentless amend is otherwise
    indistinguishable from a valid, minimal one, which is exactly the kind
    of forged-record gap `triage_integrity.is_triage_record`'s v1-v3
    hardening history exists to close).
    """
    return any(k in raw for k in AMENDABLE_FIELDS)


def check_amend_vocab(*, severity: str | None, kind: str | None, severities, kinds) -> None:
    """Raise ValueError if a PRESENT `severity`/`kind` is outside the caller's
    current vocabulary. `None` (absent) never raises — mirrors `build_amend_event`'s
    own optional-field convention. Called by the writer before any I/O.
    """
    if severity is not None and severity not in severities:
        raise ValueError(f"unknown severity {severity!r}; expected one of {severities}")
    if kind is not None and kind not in kinds:
        raise ValueError(f"unknown kind {kind!r}; expected one of {kinds}")


def check_amend_title(title: str | None) -> None:
    """Raise ValueError if a PRESENT `title` is not a non-blank string. `None`
    (absent) never raises. Mirrors `append_triage_item`'s own "title must be a
    non-empty string" guard — without this, the writer could emit a blank or
    non-string title that either fails the wire schema outright, or
    (whitespace-only) passes the writer and the schema but is then rejected by
    :func:`validate_amend_event`, so the CLI reports success while the
    correction is silently inert forever.
    """
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ValueError("title must be a non-empty string")


def check_amend_detail(detail: str | None) -> None:
    """Raise ValueError if a PRESENT `detail` is not a string. `None` (absent)
    never raises. Without this, a non-str `detail` writes past the wire
    schema and is then rejected WHOLE by :func:`validate_amend_event` on
    every future read — silently discarding any co-submitted, otherwise-valid
    `title`/`severity`/`kind` too. Same hazard `check_amend_title` closes for
    `title`.
    """
    if detail is not None and not isinstance(detail, str):
        raise ValueError("detail must be a string")


def check_amend_fields(*, title: str | None, detail: str | None, severity: str | None,
                        kind: str | None, severities, kinds) -> None:
    """Single writer-side precondition check for all four amendable fields —
    vocab, type, and contentless-call — run BEFORE any I/O (mirrors
    `mark_status`'s "argument validation before any I/O" rule, so a bad
    argument fails the same way whether or not the store happens to exist).
    """
    check_amend_vocab(severity=severity, kind=kind, severities=severities, kinds=kinds)
    check_amend_title(title)
    check_amend_detail(detail)
    if title is None and detail is None and severity is None and kind is None:
        raise ValueError(
            "amend must set at least one of: "
            f"{', '.join(AMENDABLE_FIELDS)}"
        )


def resolve_amend_residence(item_id: str, *, tracked_ids, outbox_ids, idle_main_routes_to_outbox: bool) -> bool:
    """KeyError if `item_id` is in neither set; else the `to_outbox` bool for
    the write. Mirrors `triage.mark_status`'s inline residence derivation —
    TRACKED-PREFERRED unless idle-main routing or the id is outbox-only.

    The rule is kind-independent (Stage-2 code review finding 5), so this and
    `mark_status`'s inline expression are the SAME logic in two places today —
    a deliberately deferred dedup, not an oversight: `mark_status` lives in
    `triage.py`, which is pinned at its exact bloat-baseline size, so folding
    the two together needs its own line-budget pass rather than riding this
    fix round. Keep both in sync by hand until then.
    """
    if item_id not in tracked_ids and item_id not in outbox_ids:
        raise KeyError(item_id)
    return idle_main_routes_to_outbox or (item_id in outbox_ids and item_id not in tracked_ids)


def build_amend_event(item_id: str, ts: str, by: str, *,
                       title: str | None = None, detail: str | None = None,
                       severity: str | None = None, kind: str | None = None) -> dict:
    """Build a well-formed `amend` event dict, omitting every absent field.

    Raises `ValueError` on a contentless call (no amendable field given) —
    the writer-side half of the `anyOf` rule; the reader-side half is
    :func:`has_amend_content` used by the corruption boundary.
    """
    event: dict = {"event": "amend", "id": item_id, "ts": ts, "by": by}
    if title is not None:
        event["title"] = title
    if detail is not None:
        event["detail"] = detail
    if severity is not None:
        event["severity"] = severity
    if kind is not None:
        event["kind"] = kind
    if not has_amend_content(event):
        raise ValueError(
            "amend must set at least one of: "
            f"{', '.join(AMENDABLE_FIELDS)}"
        )
    return event


def validate_amend_event(raw: dict, *, severities, kinds) -> bool:
    """True iff every field PRESENT on `raw` is well-typed and, for the two
    closed-vocabulary fields, a member of the caller's current vocabulary.

    Does NOT check :func:`has_amend_content` — a stored line already on disk
    is a resolver's input, not a writer's; a contentless amend is refused
    before it can be written (the writer) or recovered (the corruption
    boundary), so by the time `read_all_items` sees a line here, only its
    field VALIDITY is still in question.
    """
    if "title" in raw and (
        not isinstance(raw["title"], str) or not raw["title"].strip()
    ):
        return False
    if "detail" in raw and not isinstance(raw["detail"], str):
        return False
    if "severity" in raw and raw["severity"] not in severities:
        return False
    if "kind" in raw and raw["kind"] not in kinds:
        return False
    return True


def try_apply_amend(item: dict, raw: dict, *, severities, kinds, priority_from_severity) -> None:
    """Validate-then-overlay in one call for the `read_all_items` Pass 2 dispatch:
    an invalid `raw` is skipped WHOLE (no-op on `item`), never partially applied.
    """
    if validate_amend_event(raw, severities=severities, kinds=kinds):
        apply_amend(item, raw, priority_from_severity=priority_from_severity)


def apply_amend(item: dict, raw: dict, *, priority_from_severity) -> None:
    """Overlay a VALIDATED amend event onto a resolved item, in place.

    Caller must have already confirmed :func:`validate_amend_event` is True
    for `raw` — an invalid amend is the caller's responsibility to skip in
    its entirety, never partially applied here.

    A `severity` amend recomputes `suggestedPriority` via the caller-supplied
    derivation (mirrors `append`'s own — a derived field can never
    independently drift from its source). `kind` changes only `kind`; there
    is no `kind`-derived field (`suggestedDomain` derives from `source`,
    which is not amendable).

    `item["ts"]` is deliberately NOT overlaid — it keeps meaning "time of the
    last STATUS decision", exactly as before this event type existed.
    """
    if "title" in raw:
        item["title"] = raw["title"]
    if "detail" in raw:
        item["detail"] = raw["detail"]
    if "severity" in raw:
        item["severity"] = raw["severity"]
        item["suggestedPriority"] = priority_from_severity(item["severity"])
    if "kind" in raw:
        item["kind"] = raw["kind"]
    # A forged or hand-edited line can carry a non-str `by`/`ts` (validation only
    # checks the four AMENDABLE_FIELDS). Collapsing to None here mirrors
    # `mark_status`'s own non-str-`status` guard (`triage.py`) — keeps these two
    # fields `str | None` for every consumer (Stage-3 doubt review, finding 7).
    raw_by, raw_ts = raw.get("by"), raw.get("ts")
    item[AMENDED_BY_FIELD] = raw_by if isinstance(raw_by, str) else None
    item[AMENDED_AT_FIELD] = raw_ts if isinstance(raw_ts, str) else None
