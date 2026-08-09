"""`mark_status(expected_status=…)` — refuse a flip the store no longer owns.

The store-level half of iterate-2026-07-31-it1-s2-expected-status (IT-1 / S2,
card `trg-93ceb2b0` + audit finding 19). Caller wiring lives in
`test_triage_precondition_callers.py`; the drift-hook interleaving in
`test_triage_operator_decision_integration.py`.

Each test names the production line it must execute, because a ledger row that
says "tested" while the cited test stubs the line it claims to cover is the
failure this run's brief calls out by name.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import (  # noqa: E402
    StatusPreconditionError,
    append_triage_item,
    mark_status,
    read_all_items,
)


def _seed(root: Path, *, to_outbox: bool = False) -> str:
    return append_triage_item(
        root, source="iterate", severity="low", kind="bug",
        title="t", detail="d", to_outbox=to_outbox,
    )


def _store_bytes(root: Path) -> dict[str, bytes]:
    """Both halves of the union, as raw bytes — the refusal probe's subject."""
    out = {}
    for name in ("triage.jsonl", "triage.outbox.jsonl"):
        p = root / ".shipwright" / name
        out[name] = p.read_bytes() if p.exists() else b""
    return out


def _status_of(root: Path, item_id: str) -> str | None:
    return next(
        (i.get("status") for i in read_all_items(root) if i.get("id") == item_id),
        None,
    )


# --------------------------------------------------------------------------
# AC-1 / AC-2 — the precondition refuses, inside the lock, without writing
# --------------------------------------------------------------------------

def test_precondition_refuses_a_decided_item(tmp_path: Path) -> None:
    """Executes the `raise StatusPreconditionError(...)` line in `mark_status`.

    The card's scenario: a person dismissed the entry with their reason, and a
    producer that read the store BEFORE that decision tries to close it.
    """
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="dismissed", by="operator",
                reason="not a real finding")

    with pytest.raises(StatusPreconditionError) as exc:
        mark_status(tmp_path, item_id, new_status="dismissed",
                    by="driftDetector", reason="driftResolved",
                    expected_status="triage")

    assert exc.value.item_id == item_id
    assert exc.value.actual == "dismissed"
    assert exc.value.expected == ("triage",)
    # The operator's decision and REASON both survive — the point of the card.
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "operator"
    assert item["statusReason"] == "not a real finding"


def test_precondition_allows_a_still_open_item(tmp_path: Path) -> None:
    """Executes the fall-through past the raise — a satisfied precondition
    must not become a new way for a legitimate write to fail."""
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="dismissed", by="driftDetector",
                reason="driftResolved", expected_status="triage")
    assert _status_of(tmp_path, item_id) == "dismissed"


def test_without_expected_status_prior_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Executes the `if expected is not None` guard on its False branch.

    Back-compat: every existing caller passes nothing and must keep flipping
    unconditionally, or this change silently breaks eleven call sites.
    """
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="dismissed", by="a")
    mark_status(tmp_path, item_id, new_status="promoted", by="b")
    assert _status_of(tmp_path, item_id) == "promoted"


# --------------------------------------------------------------------------
# AC-7 + external finding #11 — a refused write touches NEITHER store
# --------------------------------------------------------------------------

@pytest.mark.parametrize("to_outbox", [False, True], ids=["tracked", "outbox"])
def test_refused_write_leaves_both_stores_byte_identical(
    tmp_path: Path, to_outbox: bool
) -> None:
    """Executes the raise BEFORE `_append_line` — proven by byte identity.

    Run once per residence: `mark_status` derives its write target from where
    the item lives, so a regression could append to the wrong half of the union.
    """
    item_id = _seed(tmp_path, to_outbox=to_outbox)
    mark_status(tmp_path, item_id, new_status="snoozed", by="operator",
                reason="revisit in march")

    before = _store_bytes(tmp_path)
    with pytest.raises(StatusPreconditionError):
        mark_status(tmp_path, item_id, new_status="dismissed", by="auto",
                    expected_status="triage")
    assert _store_bytes(tmp_path) == before


def test_allowed_write_round_trips_through_the_reader(tmp_path: Path) -> None:
    """AC-7's positive half: what the writer wrote is what the reader resolves."""
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="manualDefer",
                reason="waiting on upstream", expected_status="triage")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert (item["status"], item["statusBy"], item["statusReason"]) == (
        "snoozed", "manualDefer", "waiting on upstream",
    )


# --------------------------------------------------------------------------
# AC-3 — the return value distinguishes a transition from a re-flip
# --------------------------------------------------------------------------

def test_mark_status_returns_the_status_it_replaced(tmp_path: Path) -> None:
    """Executes the `return previous` line. It returned None before, so a
    caller could not tell a real transition from a no-op re-flip."""
    item_id = _seed(tmp_path)
    assert mark_status(tmp_path, item_id, new_status="dismissed", by="a") == "triage"
    assert mark_status(tmp_path, item_id, new_status="dismissed", by="b") == "dismissed"


# --------------------------------------------------------------------------
# External finding #1 — a bare `str` must not be compared character-wise
# --------------------------------------------------------------------------

def test_a_single_string_is_normalized_not_iterated(tmp_path: Path) -> None:
    """Executes `_normalize_expected`'s `isinstance(..., str)` branch.

    `previous not in "triage"` would be a SUBSTRING test — raised independently
    by both reviewers. Proof: the normalized value is the whole word in a
    one-element tuple, never its characters.
    """
    assert triage._normalize_expected("triage") == ("triage",)
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="promoted", by="op")
    with pytest.raises(StatusPreconditionError) as exc:
        mark_status(tmp_path, item_id, new_status="dismissed", by="auto",
                    expected_status="triage")
    assert exc.value.expected == ("triage",)


def test_several_expected_statuses_are_accepted(tmp_path: Path) -> None:
    """Executes the non-str branch of `_normalize_expected` — the shape S3's
    un-park command needs (`expected_status=("snoozed",)`)."""
    item_id = _seed(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="op", reason="later")
    assert mark_status(tmp_path, item_id, new_status="triage", by="op",
                       expected_status=("snoozed", "dismissed")) == "snoozed"
    assert _status_of(tmp_path, item_id) == "triage"


@pytest.mark.parametrize(
    "bad", [(), [], "nonesuch", ("triage", "nonesuch"), 7],
    ids=["empty-tuple", "empty-list", "unknown-str", "unknown-member", "not-iterable"],
)
def test_invalid_expected_status_is_rejected(tmp_path: Path, bad: object) -> None:
    """Executes `_normalize_expected`'s two `raise ValueError` lines.

    Argument validation happens BEFORE any I/O, so an unwritable store is not
    needed to reach it — asserted by using a root that has no store at all.
    """
    with pytest.raises(ValueError):
        mark_status(tmp_path, "trg-deadbeef", new_status="dismissed", by="x",
                    expected_status=bad)  # type: ignore[arg-type]


def test_expected_by_requires_a_string(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="expected_by must be a string"):
        mark_status(tmp_path, item_id, new_status="dismissed", by="auto",
                    expected_status="triage", expected_by=1)  # type: ignore[arg-type]

def test_extended_preconditions_require_expected_status(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="expected_status is required"):
        mark_status(tmp_path, item_id, new_status="dismissed", by="auto", expected_by="auto")


@pytest.mark.parametrize("bad", [("source",), "source"])
def test_block_matching_terminal_requires_a_pair(tmp_path: Path, bad: object) -> None:
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="source, dedup_key"):
        mark_status(tmp_path, item_id, new_status="dismissed", by="auto",
                    expected_status="triage", block_matching_terminal=bad)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# External finding #5 — an item that resolves to NO status
# --------------------------------------------------------------------------

def test_item_without_a_status_field_is_refused_not_written(tmp_path: Path) -> None:
    """Executes the raise with `actual=None`.

    A legacy / hand-written append line carrying no `status` key resolves to
    None. `None not in ("triage",)` must refuse rather than write, and the
    exception must format without blowing up on the None.
    """
    _seed(tmp_path)  # creates the header
    path = tmp_path / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8", newline="") as fp:
        fp.write(json.dumps({
            "event": "append", "id": "trg-legacy01",
            "ts": "2026-01-01T00:00:00Z", "source": "manual",
            "severity": "low", "kind": "bug", "title": "t", "detail": "d",
        }) + "\n")

    before = _store_bytes(tmp_path)
    with pytest.raises(StatusPreconditionError) as exc:
        mark_status(tmp_path, "trg-legacy01", new_status="dismissed",
                    by="auto", expected_status="triage")
    assert exc.value.actual is None
    assert "trg-legacy01" in str(exc.value)
    assert _store_bytes(tmp_path) == before


# --------------------------------------------------------------------------
# Validation order — an unknown status still loses to the existing guard
# --------------------------------------------------------------------------

def test_unknown_new_status_still_raises_before_the_precondition(
    tmp_path: Path,
) -> None:
    """The pre-existing `new_status` guard keeps precedence, so its error
    message does not change shape for callers that also pass a precondition."""
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="unknown status"):
        mark_status(tmp_path, item_id, new_status="bogus", by="x",
                    expected_status="triage")


def test_unknown_id_still_raises_keyerror(tmp_path: Path) -> None:
    """A precondition must not mask the existing not-found contract."""
    _seed(tmp_path)
    with pytest.raises(KeyError):
        mark_status(tmp_path, "trg-nosuchid", new_status="dismissed", by="x",
                    expected_status="triage")


def test_status_precondition_error_is_a_valueerror() -> None:
    """Pinned on purpose: the background producers catch broad `Exception` and
    the promote CLI maps `ValueError` to exit 2 — both keep working only while
    this holds."""
    assert issubclass(StatusPreconditionError, ValueError)
