"""Drift protection for runner-contract Step 3.5's second call — the external
architecture review, wired into the campaign sub-iterate-runner.

The pass shipped for standalone iterate + plan but not the runner; the runner
carried an inlined copy of Step 3.5 at its bloat cap and cannot ask an operator on
a `reject`. Two decisions are pinned here: (1) the copy was EXTRACTED to
`references/campaign-step-3-5-plan-review.md` rather than a new bloat exception
minted, (2) a `reject` HALTS the unit (`escalated` / `architecture_review_rejected`)
and the orchestrator surfaces it at campaign end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REFS = PLUGIN_ROOT / "skills" / "iterate" / "references"
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SCHEMA_FILE = PLUGIN_ROOT / "agents" / "sub_iterate_runner_contract.schema.json"
STEP_3_5 = REFS / "campaign-step-3-5-plan-review.md"
CAMPAIGN_MODE = REFS / "campaign-mode.md"
CODE = "architecture_review_rejected"


def _runner_step_3_5() -> str:
    text = RUNNER_DOC.read_text(encoding="utf-8")
    start = text.index("### Step 3.5")
    return text[start:text.index("### Step 3.6", start)]


def test_runner_step_3_5_points_at_the_extracted_reference():
    body = _runner_step_3_5()
    assert "references/campaign-step-3-5-plan-review.md" in body
    assert STEP_3_5.is_file()


def test_runner_no_longer_inlines_branch_a_commands():
    """The duplication is why the divergence happened — Step 3.5 must not grow
    its own `external_review.py --mode iterate|architecture` block again."""
    assert "external_review.py" not in _runner_step_3_5()


def test_runner_names_the_reject_halt_and_reason_code():
    body = _runner_step_3_5()
    assert "HALTS THE UNIT" in body
    assert CODE in body


def test_reference_carries_both_calls_and_a_self_resolving_driver():
    text = STEP_3_5.read_text(encoding="utf-8")
    assert "--mode iterate" in text and "--mode architecture" in text
    architecture_block = text.split("--mode architecture")[1].split("```")[0]
    assert "--brief-file" in architecture_block
    assert "--plan-file" not in architecture_block, "the CLI refuses a plan here"
    blocks = [b for b in text.split("```")[1::2] if "external_review.py" in b]
    assert len(blocks) == 2
    assert all("{driver}" not in b for b in blocks), "no caller substitutes a placeholder"
    assert text.count("CODEXTENDER_ACTIVE") >= 2


def test_reference_never_lets_the_runner_reconcile_a_reject_itself():
    text = STEP_3_5.read_text(encoding="utf-8")
    assert "Do NOT finalize" in text
    assert "recommended_alternative" in text


def test_reference_records_the_architecture_row_for_every_outcome():
    assert "Record `reviews.architecture` for every" in STEP_3_5.read_text(encoding="utf-8")


def test_schema_refuses_a_one_sided_or_findingless_reject():
    jsonschema = pytest.importorskip("jsonschema")
    one_sided = _escalation()
    one_sided["architecture_review"]["verdicts"] = {"glm": "reject"}
    no_findings = _escalation()
    no_findings["architecture_review"].pop("findings")
    for doc in (one_sided, no_findings):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, _schema())


def test_reference_says_non_reject_verdicts_proceed():
    text = " ".join(STEP_3_5.read_text(encoding="utf-8").split())
    rule = text[text.index("Any other value"):]
    rule = rule[:rule.index("`revise`")]
    assert "`unknown`" in rule and "`unavailable`" in rule
    assert "is NOT a reject" in rule and "proceed" in rule


def test_halt_steps_are_ordered_mkdir_patch_result_return():
    text = " ".join(STEP_3_5.read_text(encoding="utf-8").split())
    order = [text.index(k) for k in ("`mkdir -p`", "diff --binary HEAD", "`result.json`, `halted_patch` set", "return the same")]
    assert order == sorted(order)


def test_orchestrator_surfaces_halted_units_at_campaign_end():
    text = CAMPAIGN_MODE.read_text(encoding="utf-8")
    assert "Surface halted units" in text
    assert CODE in text
    assert "result_path" in text


def _schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _escalation() -> dict:
    return {
        "sub_iterate_id": "3.1", "status": "escalated", "reason": "rejected",
        "reason_code": CODE, "detected_complexity": "medium",
        "architecture_review": {
            "verdicts": {"glm": "reject", "openai": "approve"},
            "recommended_alternative": "reuse the existing resolver",
            "findings": ["adds a second writer"],
        },
    }


def test_schema_accepts_a_well_formed_reject_escalation():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(_escalation(), _schema())


def _drop_block(d):
    d.pop("architecture_review")


def _drop_alternative(d):
    d["architecture_review"].pop("recommended_alternative")


def _blank_alternative(d):
    d["architecture_review"]["recommended_alternative"] = ""


def _no_reject(d):
    d["architecture_review"]["verdicts"] = {"glm": "approve", "openai": "revise"}


def _no_verdicts(d):
    d["architecture_review"]["verdicts"] = {}


@pytest.mark.parametrize(
    "mutate",
    [_drop_block, _drop_alternative, _blank_alternative, _no_reject, _no_verdicts],
    ids=["missing-block", "no-alternative", "empty-alternative", "no-reject", "no-verdicts"],
)
def test_schema_refuses_a_non_actionable_reject_escalation(mutate):
    jsonschema = pytest.importorskip("jsonschema")
    doc = _escalation()
    mutate(doc)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())


def test_opus_leg_under_driver_codex_also_counts():
    jsonschema = pytest.importorskip("jsonschema")
    doc = _escalation()
    doc["architecture_review"]["verdicts"] = {"glm": "approve", "opus": "reject"}
    jsonschema.validate(doc, _schema())


# --- review-driven contract points (internal plan + architecture reviews) ---------


def test_runner_writes_result_json_before_returning_a_halt():
    """3e reads result.json from disk; a runner that only RETURNS the escalation
    lands in 3e's synthetic `failed` branch and the payload is lost."""
    assert "result.json" in _runner_step_3_5() and "FIRST" in _runner_step_3_5()
    ref = STEP_3_5.read_text(encoding="utf-8")
    assert "BEFORE" in ref
    assert "halted.patch" in ref


def test_halt_is_scoped_to_the_two_architecture_verdicts():
    assert "ARCHITECTURE reviewer" in _runner_step_3_5()
    assert "carries no halt" in STEP_3_5.read_text(encoding="utf-8")


def test_reference_defines_the_no_alternative_fallback_and_the_call_2_failure_branch():
    text = STEP_3_5.read_text(encoding="utf-8")
    assert "none named by the reviewers" in text
    assert '`reviews.architecture.status: "unavailable"`' in text


def test_orchestrator_reads_the_persisted_result_not_the_row_and_avoids_shell_quoting():
    text = CAMPAIGN_MODE.read_text(encoding="utf-8")
    step_5 = text[text.index("Surface halted units"):]
    step_5 = step_5[:step_5.index("6. **Release prompt")]
    assert "`failed`" in step_5 and "result_path" in step_5, "the ROW collapses escalated"
    assert "quoted data" in step_5
    assert "--result '{json}'" not in text, "reviewer prose must not cross single quotes"
    assert '--result "$(cat ' in text


def test_campaign_reference_does_not_drift_from_the_interactive_step():
    """The duplication was the cause of the original divergence, so the two
    accounts of the architecture call are pinned to each other."""
    interactive = (REFS / "iteration-planning.md").read_text(encoding="utf-8")
    campaign = STEP_3_5.read_text(encoding="utf-8")

    def arch_block(text: str) -> str:
        return text.split("--mode architecture")[1].split("```")[0]

    for flag in ("--spec-file", "--brief-file", "--plugin-root", "--project-root", "--run-id", "--driver"):
        assert flag in arch_block(interactive), flag
        assert flag in arch_block(campaign), flag
    assert "--plan-file" not in arch_block(interactive)
    assert "--plan-file" not in arch_block(campaign)
    for phrase in ("`revise`", "`reject`"):
        assert phrase in interactive and phrase in campaign


def test_schema_lets_a_reject_carry_the_halted_patch_and_refuses_a_blank_alternative():
    jsonschema = pytest.importorskip("jsonschema")
    doc = _escalation()
    doc["halted_patch"] = "runs/loop-1/3.1/a0/halted.patch"
    jsonschema.validate(doc, _schema())
    doc["architecture_review"]["recommended_alternative"] = "   "
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema())
