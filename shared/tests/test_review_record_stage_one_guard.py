"""The Stage-1-precedes-Stage-2 rule must not die when the `gates` seam retires.

`stage_one_precedes_stage_two` opened with `if "gates" not in record: return
None`, which encoded "a record written before `gates` existed cannot answer this
question". That was true while `gates` was the ONLY place `spec` was ever
written.

Retire the `gates` write path — which promoting `spec` into `REVIEW_TYPES` does —
and every NEW record also has no `gates` key. The guard would then return `None`
for every run from that day on: the rule that a completed internal `code` pass
implies a completed `spec` pass would stop firing, with every existing test
still green and no message anywhere. A HARD-GATE that silently stops gating is
worse than one that was never built, because the record keeps asserting the
cascade ran in order.

The guard has to ask the real question instead: *can this record answer at all* —
i.e. is `spec` absent from BOTH sections.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.review_record_core import make_entry  # noqa: E402
from tools.verifiers.review_record_floor import (  # noqa: E402
    stage_one_precedes_stage_two,
)

RUN = "iterate-2026-07-31-stage-one-guard"
PINNED = ("self", "plan", "code", "doubt", "external_code")

#: `recorded_by` naming a real adapter is what `carries_evidence` accepts as
#: proof a pass happened; without it a `completed` row fails for a DIFFERENT
#: reason and the test would pass by accident.
EVIDENCE = {"recorded_by": "code-reviewer"}


def _base(code_status: str = "completed") -> dict:
    reviews = {t: make_entry(t, "completed", **EVIDENCE) for t in PINNED}
    reviews["code"] = make_entry("code", code_status, **(
        EVIDENCE if code_status == "completed" else
        {"disposition": "external route carried this pass"}))
    return {"schema_version": 1, "run_id": RUN, "reviews": reviews}


# --- AC5: the regression this change would otherwise introduce ---------------

def test_it_fires_for_a_new_shape_record_with_no_gates_key():
    """The new shape has `spec` under `reviews` and NO `gates` key. A guard
    keyed on `"gates" not in record` waves it through."""
    record = _base()
    record["reviews"]["spec"] = make_entry(
        "spec", "not_run", disposition="nobody ran the Stage-1 spec reviewer")

    result = stage_one_precedes_stage_two(record, RUN)

    assert result is not None, (
        "a completed `code` with a not_run `spec` describes a cascade that "
        "skipped its own HARD-GATE — the rule must still fire without `gates`"
    )
    assert result.ok is False


def test_it_accepts_a_new_shape_record_whose_spec_is_completed():
    record = _base()
    record["reviews"]["spec"] = make_entry("spec", "completed", **EVIDENCE)
    assert stage_one_precedes_stage_two(record, RUN) is None


def test_a_completed_spec_still_needs_evidence():
    """The Stage-1 row is held to the same bar as the code review it precedes;
    `--status completed` with `--from` omitted produces the empty shape."""
    record = _base()
    record["reviews"]["spec"] = make_entry("spec", "completed")
    result = stage_one_precedes_stage_two(record, RUN)
    assert result is not None and result.ok is False


# --- AC6: records that genuinely cannot answer are still skipped -------------

def test_it_skips_a_pre_gates_record():
    """53 records have no `spec` anywhere. Their `code` row is already terminal
    and immutable, so every exit available to them is bad — the rule applies to
    cascades that COULD have recorded Stage 1."""
    assert stage_one_precedes_stage_two(_base(), RUN) is None


def test_it_skips_when_the_code_pass_did_not_run():
    record = _base(code_status="not_run")
    record["reviews"]["spec"] = make_entry(
        "spec", "not_run", disposition="external route carried this pass")
    assert stage_one_precedes_stage_two(record, RUN) is None


# --- AC4 at the gate: a legacy `gates.spec` still answers --------------------

def test_a_gates_era_spec_still_satisfies_the_rule():
    record = _base()
    record["gates"] = {"spec": make_entry("spec", "completed", **EVIDENCE)}
    assert stage_one_precedes_stage_two(record, RUN) is None


def test_a_gates_era_spec_that_did_not_run_still_fires():
    record = _base()
    record["gates"] = {"spec": make_entry(
        "spec", "not_run", disposition="nobody ran the Stage-1 spec reviewer")}
    result = stage_one_precedes_stage_two(record, RUN)
    assert result is not None and result.ok is False
