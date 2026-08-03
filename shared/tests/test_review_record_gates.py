"""How the RETIRED `gates` sibling is validated in records that still carry it.

`spec` lived here while the cross-repo consumer rejected any `reviews` key
outside its own five. That pin is gone (`shipwright-webui` `ce21323e`) and
`spec` is now an ordinary review type — see
`test_review_record_spec_promotion.py`, which owns the promotion itself and the
back-compat READ path.

What is left for this file is the object's own validation semantics, which
outlive the seam because 12 git-tracked, never-evicted records carry
`gates.spec` and are immutable by design. Nothing writes `gates` any more; these
tests pin how it is READ.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    LEGACY_GATE_TYPES,
    REVIEW_TYPES,
    STATUS_COMPLETED,
    make_entry,
    new_record,
    validate_record,
)

RUN = "iterate-2026-07-28-gates"

#: The five the consumer requires to be PRESENT. Hard-coded, NOT derived from
#: REVIEW_TYPES — a test that reads the constant it pins cannot catch it
#: changing, and this list must NOT follow `spec` into the tuple.
PINNED_CONSUMER_TYPES = ["self", "plan", "code", "doubt", "external_code"]


def _legacy_with_gates(**gate_entries) -> dict:
    """A record in the shape the 12 gates-era runs actually wrote."""
    return {
        "schema_version": 1,
        "run_id": RUN,
        "reviews": {t: make_entry(t, STATUS_COMPLETED) for t in PINNED_CONSUMER_TYPES},
        "gates": dict(gate_entries),
    }


def test_the_seam_is_retired_as_a_write_destination():
    """Chesterton: the fence existed to hold passes the pinned `reviews`
    contract had no slot for. The pin is gone, so a future gate stage goes
    straight into REVIEW_TYPES and nothing writes here again."""
    assert "gates" not in new_record(RUN)
    assert "spec" in REVIEW_TYPES
    # ...but the read vocabulary survives, because the old records do.
    assert "spec" in LEGACY_GATE_TYPES


def test_an_unknown_gate_key_is_tolerated_not_rejected():
    """Asymmetric with `reviews` on purpose. That one mirrors a cross-repo
    contract whose consumer used to reject strangers, so strictness protected
    the mirror. `gates` has no mirror, and rejecting a stranger here would mean
    a record from a newer writer reads as schema-INVALID to every reader still
    on the old constant — and the F11 gate, which fails CLOSED, tells the
    operator to "repair or delete" an immutable history that is perfectly fine.
    """
    record = _legacy_with_gates(
        spec=make_entry("spec", STATUS_COMPLETED),
        a_future_stage=make_entry("spec", STATUS_COMPLETED),
    )
    ok, err = validate_record(record, expected_run_id=RUN)
    assert ok, err


def test_a_malformed_known_gate_entry_is_still_rejected():
    """Tolerating strangers must not tolerate a broken row we DO know."""
    record = _legacy_with_gates(spec=make_entry("spec", STATUS_COMPLETED))
    record["gates"]["spec"]["findings_count"] = 99
    ok, err = validate_record(record, expected_run_id=RUN)
    assert not ok and "gates.spec" in err


def test_a_non_object_gates_value_is_rejected():
    record = _legacy_with_gates()
    record["gates"] = "not an object"
    ok, err = validate_record(record, expected_run_id=RUN)
    assert not ok and "gates" in err
