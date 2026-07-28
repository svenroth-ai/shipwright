"""AC-4 — Stage 1 (spec-reviewer) can prove it ran, without breaking the consumer.

`reviews` is a CROSS-REPO contract. The webui reader
(`shipwright-webui` `server/src/core/mission-context/review-record.ts`) rejects a
record whose `schema_version` differs by strict `!==` (:261) or whose `reviews`
carries a key outside its own five (:276), and `review-state.ts:240` does **not**
fall back to the marker view on an invalid record — it renders all five rows as a
data-integrity fault. So the naive "sixth REVIEW_TYPES entry + schema bump" would
report every healthy record as corrupt.

The gate stages therefore live in a sibling `gates` object. The tests below pin
BOTH halves: that `spec` is really enforceable, and that the consumer's two
guards still pass.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    GATE_TYPES,
    RECORDABLE_TYPES,
    REVIEW_TYPES,
    SCHEMA_VERSION,
    STATUS_COMPLETED,
    STATUS_NOT_RUN,
    make_entry,
    new_record,
    pending_types,
    read_record,
    record_path,
    upsert_review,
    validate_record,
    write_record,
)

RUN = "iterate-2026-07-28-gates"
REASON = "external route carried the pass; Stage 1 is not cascaded to providers"

#: The five keys the cross-repo consumer knows. Hard-coded, NOT derived from
#: REVIEW_TYPES — a test that reads the constant it is pinning cannot catch the
#: constant changing.
PINNED_CONSUMER_TYPES = ["self", "plan", "code", "doubt", "external_code"]


def test_spec_is_recordable_but_not_a_review_type():
    assert "spec" in GATE_TYPES
    assert "spec" in RECORDABLE_TYPES
    assert "spec" not in REVIEW_TYPES


# --- the consumer's two guards, mirrored as executable assertions -----------
# These MIRROR the TypeScript reader; they do not execute it (a cross-repo suite
# cannot run from this commit's CI). Drift between mirror and consumer is the
# stated residual risk — see the iterate spec §2b, openai #3.

def test_the_record_still_passes_the_pinned_consumers_guards(tmp_path):
    record = new_record(RUN)
    record = upsert_review(record, make_entry("spec", STATUS_COMPLETED))
    write_record(tmp_path, RUN, record)

    on_disk = json.loads(record_path(tmp_path, RUN).read_text(encoding="utf-8"))

    # review-record.ts:261 — strict `!==` against its own constant of 1.
    assert on_disk["schema_version"] == 1 == SCHEMA_VERSION
    # review-record.ts:276 — any key outside its five makes the record invalid.
    assert list(on_disk["reviews"]) == PINNED_CONSUMER_TYPES
    # ...and the gate row is nowhere the consumer looks.
    assert on_disk["gates"]["spec"]["status"] == STATUS_COMPLETED


def test_a_legacy_record_without_gates_is_still_valid():
    """64 merged runs wrote records with no `gates`. Invalidating them would make
    the F11 gate report an integrity fault on every one."""
    legacy = {
        "schema_version": 1, "run_id": RUN,
        "reviews": {t: make_entry(t, STATUS_COMPLETED) for t in REVIEW_TYPES},
    }
    ok, err = validate_record(legacy, expected_run_id=RUN)
    assert ok, err


# --- a live run cannot dodge the row by omitting the section ----------------

def test_a_new_record_materialises_spec_as_pending():
    assert "spec" in pending_types(new_record(RUN))


def test_an_absent_gates_section_reads_as_unanswered(tmp_path):
    """openai #1 — optionality must buy back-compat for old records and nothing
    at all for a live gate."""
    legacy = {
        "schema_version": 1, "run_id": RUN,
        "reviews": {t: make_entry(t, STATUS_COMPLETED) for t in REVIEW_TYPES},
    }
    assert pending_types(legacy) == ["spec"]


def test_spec_round_trips_and_is_immutable(tmp_path):
    record = upsert_review(new_record(RUN), make_entry(
        "spec", STATUS_NOT_RUN, disposition=REASON, recorded_by="close-missing"))
    write_record(tmp_path, RUN, record)

    read_back = read_record(tmp_path, RUN)
    assert read_back == record
    assert pending_types(read_back) == [t for t in REVIEW_TYPES]

    try:
        upsert_review(read_back, make_entry("spec", STATUS_COMPLETED))
    except Exception as exc:  # noqa: BLE001 — the type is asserted below
        assert type(exc).__name__ == "ImmutableReviewError"
    else:  # pragma: no cover
        raise AssertionError("a terminal gate row must not be silently rewritable")


def test_an_unknown_gate_key_is_tolerated_not_rejected():
    """Stage-3 doubt: `schema_version` is frozen at 1 BY DESIGN, and GATE_TYPES
    is documented as where future stages go. Rejecting an unknown gate key would
    mean the day it gains a second member, records from the new writer read as
    schema-INVALID to every reader still on the old constant — and the gate tells
    the operator to "repair or delete" an immutable, git-tracked, never-evicted
    history that is perfectly fine. That is §1.3's failure reproduced internally,
    and the plugin cache makes old-and-new readers routine.

    The asymmetry with `reviews` is deliberate: that one mirrors a cross-repo
    contract whose consumer rejects strangers, so strictness protects the mirror.
    `gates` has no mirror.
    """
    record = new_record(RUN)
    record["gates"]["a_future_stage"] = make_entry("spec", STATUS_COMPLETED)
    ok, err = validate_record(record, expected_run_id=RUN)
    assert ok, err


def test_a_malformed_known_gate_entry_is_still_rejected():
    """Tolerating strangers must not tolerate a broken row we DO know."""
    record = new_record(RUN)
    record["gates"]["spec"]["findings_count"] = 99
    ok, err = validate_record(record, expected_run_id=RUN)
    assert not ok and "gates.spec" in err
