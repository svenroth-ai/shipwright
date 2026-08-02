"""`spec` is a first-class review type — and 65 older records stay readable.

The producer's own source named the release condition: promotion becomes safe
once the webui ships a reader that tolerates unknown review types. It shipped
(`shipwright-webui` `ce21323e`, PR #339): the version check became a FLOOR and
unrecognised `reviews` keys are rendered as rows instead of rejected.

What the comment got wrong is that this is one line. `validate_record` requires
every `REVIEW_TYPES` member to be PRESENT in `reviews`, and no record ever
written carries `spec` there — 12 keep it under the `gates` sibling, 53 predate
the concept entirely. Promoting without a transitional READ path makes this
repo's own fail-closed F11 gate report all 65 as corrupt.

These tests pin both directions: the new shape is produced, and every old shape
is still read.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    RECORDABLE_TYPES,
    REVIEW_TYPES,
    SCHEMA_VERSION,
    STATUS_COMPLETED,
    STATUS_NOT_RUN,
    ImmutableReviewError,
    entry_for,
    make_entry,
    new_record,
    pending_types,
    read_record,
    upsert_review,
    validate_record,
    write_record,
)

RUN = "iterate-2026-07-31-review-record-spec-promotion"
REASON = "external route carried the pass; Stage 1 is not cascaded to providers"

#: The five keys the cross-repo consumer requires to be PRESENT. Hard-coded, not
#: derived — a test that reads the constant it pins cannot catch it changing.
#: The new reader tolerates keys OUTSIDE this list; it still calls a record
#: unreadable when one of these five is missing (`review-record.ts`, "the pinned
#: five are FROZEN").
PINNED_CONSUMER_TYPES = ["self", "plan", "code", "doubt", "external_code"]

#: `REVIEW_KEY` in the consumer: a stranger key must still be an identifier.
CONSUMER_KEY_RE = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"

#: The consumer's aggregate bound on how many passes one record may carry.
CONSUMER_MAX_REVIEW_TYPES = 32


# --- AC1 / AC8: the new shape ------------------------------------------------

def test_spec_is_a_first_class_review_type():
    assert "spec" in REVIEW_TYPES
    assert "spec" in RECORDABLE_TYPES


def test_a_new_record_carries_spec_under_reviews_and_no_gates_key():
    record = new_record(RUN)
    assert record["reviews"]["spec"]["status"] == "pending"
    # AC8 — the retired seam is not emitted as an empty object. The consumer
    # counts passes under record keys it does not read and appends a caveat; an
    # always-empty `gates` would be a permanent invitation to that code path.
    assert "gates" not in record


def test_schema_version_is_not_bumped():
    """AC2. The consumer reads `>=` now, so a bump buys it nothing — while
    `validate_record` rejects a version newer than its own constant, making
    casualties of every old plugin cache, and the new reader appends a
    'written by a newer Shipwright' caveat for a record that is not."""
    assert SCHEMA_VERSION == 1
    assert new_record(RUN)["schema_version"] == 1


def test_the_new_shape_satisfies_the_new_consumer_contract(tmp_path):
    """Mirrors the merged reader; it does not execute it (a cross-repo suite
    cannot run from this commit's CI). Drift is the stated residual risk."""
    import re

    record = upsert_review(new_record(RUN), make_entry(
        "spec", STATUS_COMPLETED, recorded_by="code-reviewer"))
    path = write_record(tmp_path, RUN, record)
    on_disk = json.loads(path.read_text(encoding="utf-8"))

    # the version is a FLOOR (>= 1), not a pin
    assert on_disk["schema_version"] >= 1
    # the pinned five must all still be PRESENT — tolerance is additive only
    for review_type in PINNED_CONSUMER_TYPES:
        assert review_type in on_disk["reviews"]
    # `spec` rides along as a stranger key: rendered, not rejected
    strangers = [k for k in on_disk["reviews"] if k not in PINNED_CONSUMER_TYPES]
    assert strangers == ["spec"]
    for key in strangers:
        assert re.match(CONSUMER_KEY_RE, key), f"{key!r} is corruption, not evolution"
    assert len(on_disk["reviews"]) <= CONSUMER_MAX_REVIEW_TYPES


# --- AC3 / AC4: every older shape is still read ------------------------------

def _legacy_pre_gates() -> dict:
    """The 53-record shape: five reviews, no `gates`, no `spec` anywhere."""
    return {
        "schema_version": 1, "run_id": RUN,
        "reviews": {t: make_entry(t, STATUS_COMPLETED) for t in PINNED_CONSUMER_TYPES},
    }


def _legacy_gates_era(spec_status: str = STATUS_COMPLETED) -> dict:
    """The 12-record shape: `spec` recorded under the `gates` sibling.

    A non-`completed` status needs a disposition at CONSTRUCTION time —
    `make_entry` refuses to build the entry otherwise, so it cannot be patched
    on afterwards.
    """
    record = _legacy_pre_gates()
    extra = {} if spec_status == STATUS_COMPLETED else {"disposition": REASON}
    record["gates"] = {"spec": make_entry(
        "spec", spec_status, recorded_by="code-reviewer", **extra)}
    return record


def test_a_pre_gates_record_still_validates():
    ok, err = validate_record(_legacy_pre_gates(), expected_run_id=RUN)
    assert ok, err


def test_a_gates_era_record_still_validates():
    ok, err = validate_record(_legacy_gates_era(), expected_run_id=RUN)
    assert ok, err


def test_a_gates_era_spec_row_is_still_found():
    """AC4 — the row did not move on disk, so the reader must go and get it."""
    record = _legacy_gates_era()
    assert entry_for(record, "spec")["status"] == STATUS_COMPLETED
    assert "spec" not in pending_types(record)


def test_a_pre_gates_record_reports_spec_unanswered():
    """Back-compat is about READING history. A record that never answered for
    `spec` still reports it unanswered, so a live run cannot inherit the
    tolerance and dodge the row."""
    assert pending_types(_legacy_pre_gates()) == ["spec"]


def test_every_record_on_disk_still_validates():
    """AC3 — the corpus itself, not a reconstruction of it. This is the
    assertion the whole transitional read path exists to keep true: the F11
    gate fails CLOSED, so a single regression here tells an operator to repair
    or delete an immutable, git-tracked review history that is perfectly fine.
    """
    root = Path(__file__).resolve().parents[2]
    records = sorted((root / ".shipwright" / "planning" / "iterate").rglob("reviews.json"))
    assert records, "corpus not found — this test would silently pass on nothing"

    broken = []
    for path in records:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ok, err = validate_record(payload, expected_run_id=path.parent.name)
        if not ok:
            broken.append(f"{path.parent.name}: {err}")
    assert not broken, "records that stopped validating:\n" + "\n".join(broken)


# --- AC7: immutability survives the section move -----------------------------

def test_a_terminal_gates_era_spec_cannot_be_silently_rewritten():
    """The write path now targets `reviews`, so an immutability check that only
    looked there would happily shadow a completed legacy row with a new one —
    two answers for one pass, and the newer one wins by accident."""
    record = _legacy_gates_era()
    try:
        upsert_review(record, make_entry("spec", STATUS_NOT_RUN, disposition=REASON))
    except ImmutableReviewError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a terminal legacy spec row must not be shadowed")


def test_a_reviews_row_wins_over_a_legacy_gates_row():
    """Which section is authoritative when BOTH carry the type.

    `_read_sections` answers that in one ordered tuple, and without this test
    the answer is unpinned: every other fixture puts `spec` in exactly one
    section, so flipping the order to `("gates", "reviews")` would keep the
    whole suite green (Stage-2 code review).

    Both-present is reachable two ways — `--force` on a gates-era record writes
    into `reviews` and leaves the terminal legacy row behind, and a record
    in flight at rollout carries `gates.spec: pending` from the old writer.
    """
    record = _legacy_gates_era(spec_status=STATUS_NOT_RUN)
    # Built through the REAL route the docstring names rather than by hand: this
    # exercises `--force` on a terminal legacy row, and with it the
    # `dict(record)`-preserves-`gates` behaviour that makes the shadow possible.
    record = upsert_review(record, make_entry(
        "spec", STATUS_COMPLETED, recorded_by="spec-reviewer"), force=True)
    assert record["gates"]["spec"]["status"] == STATUS_NOT_RUN, (
        "the legacy row must survive the write — the point is that two answers "
        "coexist and precedence decides, not that one is deleted"
    )

    # This assertion carries the test on its own: `pending_types` below does NOT
    # discriminate, because `not_run` is terminal either way (Stage-2 re-review).
    assert entry_for(record, "spec")["status"] == STATUS_COMPLETED
    assert "spec" not in pending_types(record)
    ok, err = validate_record(record, expected_run_id=RUN)
    assert ok, err


def test_writing_the_answer_drops_a_still_pending_legacy_row():
    """The in-flight rollout shape: a record `init`ed by the OLD writer carries
    `gates: {spec: pending}`, and the answer is then written by the new one.

    Leaving the pending row behind would make the consumer contradict itself: it
    counts unread passes BY SHAPE, so it would render the `spec` row AND append
    "this run also recorded 1 review pass somewhere this version does not read"
    (Stage-3 doubt). Dropping it destroys nothing — `pending` is the absence of
    an answer, not an answer.
    """
    record = _legacy_pre_gates()
    record["gates"] = {"spec": make_entry("spec", "pending")}

    record = upsert_review(record, make_entry(
        "spec", STATUS_COMPLETED, recorded_by="spec-reviewer"))

    assert record["reviews"]["spec"]["status"] == STATUS_COMPLETED
    assert "gates" not in record, "an emptied legacy section is dropped outright"
    ok, err = validate_record(record, expected_run_id=RUN)
    assert ok, err


def test_a_terminal_legacy_row_is_never_dropped():
    """The other side of the same rule. A recorded ANSWER is history and stays,
    even when a forced write supersedes it — tidying a shape must never delete
    a finding."""
    record = _legacy_gates_era()          # gates.spec = completed
    record = upsert_review(record, make_entry(
        "spec", STATUS_NOT_RUN, disposition=REASON), force=True)

    assert record["gates"]["spec"]["status"] == STATUS_COMPLETED
    assert record["reviews"]["spec"]["status"] == STATUS_NOT_RUN


def test_a_terminal_reviews_spec_is_immutable_on_the_ordinary_path():
    """The legacy path has its own test above; this is the NEW normal path —
    a terminal `reviews.spec` written the ordinary way. Splitting the old
    combined test dropped this half (Stage-2 code review), and it composes
    badly with the precedence test: were the order flipped, the legacy-path
    test alone would still pass."""
    record = upsert_review(new_record(RUN), make_entry(
        "spec", STATUS_COMPLETED, recorded_by="spec-reviewer"))
    try:
        upsert_review(record, make_entry(
            "spec", STATUS_NOT_RUN, disposition=REASON))
    except ImmutableReviewError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a terminal reviews.spec must not be rewritable")


def test_round_trips_through_disk_unchanged(tmp_path):
    """The record is a serialization boundary read by another repo; a shape that
    does not survive its own write/read cycle cannot be a contract."""
    record = upsert_review(new_record(RUN), make_entry(
        "spec", STATUS_NOT_RUN, disposition=REASON, recorded_by="close-missing"))
    write_record(tmp_path, RUN, record)
    assert read_record(tmp_path, RUN) == record
