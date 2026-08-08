"""Disposition rules for `amend` events in the outbox sweep (AC12).

iterate-2026-08-08-triage-amend-event. `decide()` must classify an orphan or
protected `amend` line the same way it already classifies an orphan or
protected `status` line — held when its append is real but only reachable via
main's tracked log, quarantined when genuinely unreachable — without changing
any existing status-path behavior or its pinned `protected_status_unplaceable`
token. Mirrors `test_sweep_quarantine_dispositions.py`'s status-side pins.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.sweep_quarantine import decide  # noqa: E402

MAIN_ONLY = "trg-in-main"
GHOST = "trg-ghost"
PENDING = "trg-pending"
KNOWN = frozenset({MAIN_ONLY})


def _tracked() -> list[str]:
    return [h.HEADER, h.item("trg-other")]


def test_a_valid_amend_in_the_outbox_is_clean_and_delivers() -> None:
    """The plain happy case: an amend for an id whose append is already
    tracked validates with no errors at all — `clean`, delivered as-is, never
    routed through hold/quarantine/block."""
    correction = h.amend("trg-other")  # "trg-other" is in `_tracked()`'s append

    d = decide(_tracked(), [correction], "\n", known_append_ids=KNOWN)

    assert d.action == "clean", d
    assert correction in d.deduped_text
    assert d.candidates == [] and d.held_lines == []


def test_protected_amend_is_held_not_blocked() -> None:
    """The correction is legitimate — its append is real, just not reachable
    from this branch yet. Must never be quarantined (destroys the operator's
    correction) and must not block (that stranded everything else)."""
    correction = h.amend(MAIN_ONLY)

    d = decide(_tracked(), [correction], "\n", known_append_ids=KNOWN)

    assert d.action == "hold", d
    assert d.held_lines == [correction]
    assert correction not in d.candidates


def test_hold_delivers_the_rest_of_the_outbox_alongside_an_amend() -> None:
    correction = h.amend(MAIN_ONLY)
    pending = h.item(PENDING)

    d = decide(_tracked(), [correction, pending], "\n", known_append_ids=KNOWN)

    assert d.action == "hold"
    assert d.held_lines == [correction]
    assert d.materialized_outbox == [pending]
    assert pending in d.deduped_text and correction not in d.deduped_text


def test_genuine_orphan_amend_is_quarantined() -> None:
    orphan = h.amend(GHOST)

    d = decide(_tracked(), [orphan], "\n", known_append_ids=KNOWN)

    assert d.action == "quarantine" and d.candidates == [orphan]


def test_status_and_amend_orphans_co_occur_without_cross_contamination() -> None:
    """A status orphan for one id and an amend orphan for a DIFFERENT id must
    both be classified correctly — this pins that the per-kind orphan check
    (AC12's `this_orphans` dispatch) never lets one kind's orphan set leak into
    the other's classification."""
    status_orphan = h.status(GHOST, "dismissed")
    amend_orphan = h.amend("trg-other-ghost")
    dismiss_held = h.amend(MAIN_ONLY)
    pending = h.item(PENDING)

    d = decide(
        _tracked(), [status_orphan, amend_orphan, dismiss_held, pending],
        "\n", known_append_ids=KNOWN,
    )

    assert set(d.candidates) == {status_orphan, amend_orphan}
    assert d.held_lines == [dismiss_held]
    assert d.materialized_outbox == [pending]


def test_protected_amend_uses_its_own_unplaceable_token_when_blocked() -> None:
    """A block co-occurring with a protected amend must still explain it — via a
    NEW, distinct `protected_amend_unplaceable` token, never the status path's
    pinned `protected_status_unplaceable` (AC12/M5: a new sibling token, not a
    rename or a reuse — naming the wrong event kind is its own misdirection)."""
    protected_amend = h.amend(MAIN_ONLY)
    unsplittable = '{"event":"status"}{"newStatus":"dismissed"}'  # two records glued: unsplittable

    d = decide(_tracked(), [protected_amend, unsplittable], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert any("protected_amend_unplaceable" in e for e in d.errors), d.errors
    assert not any("protected_status_unplaceable" in e for e in d.errors), d.errors


def test_protected_status_still_uses_the_pinned_status_unplaceable_token() -> None:
    """The status path's existing token is untouched by the amend addition."""
    protected_status = h.status(MAIN_ONLY, "dismissed")
    unsplittable = '{"event":"status"}{"newStatus":"dismissed"}'  # two records glued: unsplittable

    d = decide(_tracked(), [protected_status, unsplittable], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert any("protected_status_unplaceable" in e for e in d.errors), d.errors
    assert not any("protected_amend_unplaceable" in e for e in d.errors), d.errors
