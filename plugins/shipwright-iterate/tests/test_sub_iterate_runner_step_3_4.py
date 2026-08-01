"""Drift protection for runner-contract Step 3.4 — Diff-Driven Risk Re-Check
(iterate-2026-08-01-campaign-diff-driven-risk-recheck).

Kept separate from `test_sub_iterate_runner_contract.py` deliberately: that file
is pinned at 421 lines in `shipwright_bloat_baseline.json`, and growing it would
be an Anti-Ratchet violation (audit H3, HIGH) — the baseline records
grandfathered crossings, not a sliding ceiling.

What these guard: a campaign unit classifies complexity ONCE, at Step 2, from the
sub-iterate spec TEXT before any code exists, so every diff-driven detector
(`cross_component`, `touches_ci_supplychain`, and the file-pattern halves of
`touches_io_boundary` / `touches_build`) is structurally unable to fire. Step 3.4
is the runner's Stage-2 equivalent. Each assertion below pins a fact that, if
edited away, makes the mechanism silently inert rather than loudly broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SCHEMA_FILE = PLUGIN_ROOT / "agents" / "sub_iterate_runner_contract.schema.json"
CAMPAIGN_MODE = PLUGIN_ROOT / "skills" / "iterate" / "references" / "campaign-mode.md"

#: The bloat baseline pins the runner contract here (state: exception, ADR-119).
RUNNER_DOC_LINE_CEILING = 497


def _runner() -> str:
    return RUNNER_DOC.read_text(encoding="utf-8")


def _step_3_4() -> str:
    """ONLY the Step 3.4 section.

    Whole-document greps are how a drift test quietly stops working: the earlier
    version of `test_step_3_4_tells_the_runner_what_to_do_on_an_operational_failure`
    searched the whole file for `status:"failed"`, which the pre-existing Browser
    Verify bullet already satisfies — deleting Step 3.4's failure branch outright
    would have left it green.
    """
    text = _runner()
    start = text.index("### Step 3.4")
    return text[start:text.index("### Step 3.5", start)]


def _schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The step itself
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_step_3_4_heading_present():
    assert "Step 3.4" in _runner(), (
        "Step 3.4 heading missing — without it the runner classifies once from "
        "the sub-iterate spec TEXT and every diff-driven detector stays silent."
    )


@pytest.mark.covers("FR-01.11")
def test_step_3_4_invokes_the_recheck_cli():
    assert "diff_risk_recheck.py" in _step_3_4()


@pytest.mark.covers("FR-01.11")
def test_step_3_4_runs_before_the_review_gates():
    """3.4 must precede 3.5/3.7/3.8 — they gate on the flags it produces."""
    text = _runner()
    assert text.index("Step 3.4") < text.index("### Step 3.5")


@pytest.mark.covers("FR-01.11")
def test_step_3_4_documents_working_tree_change_set():
    """The runner commits at F6, so a committed-range diff is EMPTY here and the
    re-check would silently pass — the exact blindness it exists to remove."""
    assert "working tree" in _step_3_4().lower(), (
        "Step 3.4 must state the change set is base -> WORKING TREE"
    )


@pytest.mark.covers("FR-01.11")
def test_step_3_4_documents_ci_escalation_and_forbids_self_ack():
    text = _step_3_4()
    assert "ci_supplychain_requires_operator" in text
    assert "ci_paths" in text
    # Strip markdown emphasis before matching: the contract bolds the negation
    # ("Do **not** write ..."), and asserting on one exact spelling would make
    # this guard fail on a purely cosmetic edit while still passing if the whole
    # sentence were deleted — the opposite of what a drift test is for.
    plain = text.replace("*", "").replace("`", "").lower()
    assert "do not write the ci acknowledgement yourself" in plain, (
        "Step 3.4 must forbid the runner writing its own CI acknowledgement — "
        "the ack certifies a human reasoned about a trust-boundary change."
    )


@pytest.mark.covers("FR-01.11")
def test_step_3_4_requires_f5c_to_record_effective_complexity():
    """`check_integration_coverage` reads complexity from the F5c entry and
    green-SKIPs below medium, so recording Step 2's stale estimate leaves the
    gate reporting green without ever evaluating."""
    text = _step_3_4()
    assert "effective_complexity" in text
    assert "F5c MUST record this value" in text


@pytest.mark.covers("FR-01.11")
def test_step_3_4_tells_the_runner_what_to_do_on_an_operational_failure():
    """Exit 2 is neither 0 nor 3. Without an explicit instruction a runner can
    read "not 3, so not an escalation" and carry on with Step 2's stale
    complexity — the silent stand-down this iterate removes."""
    section = _step_3_4()
    assert "Any other non-zero" in section, (
        "Step 3.4 must name the non-0/non-3 branch explicitly"
    )
    assert 'status:"failed"' in section or 'status: "failed"' in section, (
        "Step 3.4 must tell the runner to FAIL the unit on any other non-zero "
        "exit, never to continue on Stage 1's estimate"
    )


@pytest.mark.covers("FR-01.11")
def test_step_3_4_passes_stage1_flags_forward():
    """Seven canonical flags have no diff-driven detector; if Step 3.4 replaced
    Stage 1's flag set instead of unioning it, Step 3.5 would SKIP cases the
    pre-Step-3.4 rule ran — narrowing the gate this change widens."""
    assert "--stage1-flags" in _step_3_4()


@pytest.mark.covers("FR-01.11")
def test_step_3_5_trigger_mirrors_step_3_7():
    """AC5. Step 3.5 fired on `medium+ OR risk flag` while 3.7 also had an
    `OR diff > 100 LOC` arm — and campaign flag-blindness made 3.5 a GUARANTEED
    skip for a unit landing at `small`."""
    heading = next(
        ln for ln in _runner().splitlines() if ln.startswith("### Step 3.5")
    )
    assert "100 LOC" in heading or "100 lines" in heading, (
        f"Step 3.5's heading must carry the diff-size arm; got: {heading}"
    )


@pytest.mark.covers("FR-01.11")
def test_campaign_mode_documents_step_3_4_and_the_escalated_unit_path():
    """The contract delegates Step 3.4's rationale to campaign-mode.md to stay
    under its line ceiling, which makes that prose load-bearing: it is the only
    place the orchestrator's handling of a CI-escalated unit is written down."""
    text = CAMPAIGN_MODE.read_text(encoding="utf-8")
    assert "Step 3.4" in text
    assert "ci_supplychain_requires_operator" in text
    for expected in ("STRICT-STOP", "record_ci_supplychain_ack.py"):
        assert expected in text, (
            f"campaign-mode.md must document {expected!r} — how the campaign "
            "halts, and how the operator resolves the handback"
        )


@pytest.mark.covers("FR-01.11")
def test_runner_doc_within_bloat_ceiling():
    """Anti-Ratchet: the baseline records grandfathered crossings, not a sliding
    ceiling, so a new step has to pay for itself."""
    lines = len(_runner().splitlines())
    assert lines <= RUNNER_DOC_LINE_CEILING, (
        f"sub-iterate-runner.md is {lines} lines; the baseline pins it at "
        f"{RUNNER_DOC_LINE_CEILING} and raising `current` is an Anti-Ratchet "
        "violation (audit H3, HIGH)."
    )


# ---------------------------------------------------------------------------
# Result-contract schema: risk_recheck + the Step 3.4 escalation variant
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_schema_has_risk_recheck_property():
    props = _schema()["$defs"]["success"]["properties"]
    assert "risk_recheck" in props, (
        "success schema must declare 'risk_recheck' — `additionalProperties` is "
        "false, so an unregistered field makes the whole result INVALID."
    )


@pytest.mark.covers("FR-01.11")
def test_schema_risk_recheck_optional_for_backwards_compat():
    """Same rule `reviews` and `finalization` follow: the schema must still
    validate result.json artifacts written before this mechanism existed."""
    assert "risk_recheck" not in _schema()["$defs"]["success"]["required"]


@pytest.mark.covers("FR-01.11")
def test_schema_escalated_declares_ci_vocabulary():
    props = _schema()["$defs"]["escalated"]["properties"]
    assert "ci_supplychain_requires_operator" in props["reason_code"]["enum"]
    assert "ci_paths" in props


@pytest.mark.covers("FR-01.11")
def test_schema_escalated_detected_complexity_widened():
    """It was `large`-only; a Step 3.4 CI escalation can occur at any complexity."""
    enum = _schema()["$defs"]["escalated"]["properties"]["detected_complexity"]["enum"]
    assert {"trivial", "small", "medium", "large"} <= set(enum)
    assert "large" in enum  # historical results stay valid


def _ci_escalation(**over) -> dict:
    sample = {
        "sub_iterate_id": "3.1",
        "status": "escalated",
        "reason": "Diff touches the CI trust boundary",
        "reason_code": "ci_supplychain_requires_operator",
        "detected_complexity": "medium",
        "ci_paths": [".github/workflows/ci.yml"],
    }
    sample.update(over)
    return sample


@pytest.mark.covers("FR-01.11")
def test_schema_validates_ci_escalation():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(_ci_escalation(), _schema())


@pytest.mark.covers("FR-01.11")
def test_schema_rejects_ci_escalation_without_paths():
    """An escalation naming no path is not actionable — the operator is told to
    go look at CI files without being told WHICH."""
    jsonschema = pytest.importorskip("jsonschema")
    sample = _ci_escalation()
    del sample["ci_paths"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(sample, _schema())


@pytest.mark.covers("FR-01.11")
def test_schema_rejects_ci_escalation_with_empty_paths():
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_ci_escalation(ci_paths=[]), _schema())


@pytest.mark.covers("FR-01.11")
def test_schema_still_accepts_legacy_large_escalation():
    """The original Step 2 escalation carried no reason_code and no ci_paths."""
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(
        {
            "sub_iterate_id": "A",
            "status": "escalated",
            "reason": "Complexity classified as large",
            "detected_complexity": "large",
        },
        _schema(),
    )
