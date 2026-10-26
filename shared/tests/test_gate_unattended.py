"""Unattended-answer rules of the phase-gate catalog (B5, brief D5).

Pins the allowlist and the denylist per gate id, the validator checks, and the
resolver's autonomy input (it reports the answer; ``should_stop`` never changes).
"""
from __future__ import annotations

import pytest

from lib.gate_policy import (
    COVERED_PHASES,
    SINGLE_SESSION,
    load_catalog,
    resolve_gate_policy,
    validate_catalog,
)
from lib.gate_unattended import UNATTENDED_DENYLIST, is_denylisted

pytestmark = pytest.mark.covers("FR-01.01")

ALLOWLIST = {
    "design.preview-approval",
    "design.review-loop-finalize",
    "design.upload-screen-mapping",
}

# Pinned literally (not imported) so editing the set in the module fails this test.
DENYLIST = {
    "build.migration-preflight-fail", "build.migration-apply-fail",
    "build.env-validation-missing-vars", "deploy.missing-env-vars",
    "deploy.post-migration-manual-steps", "project.supabase-project-ref",
    "build.browser-verify-prereq-unresolved", "build.browser-verify-fix-exhausted",
    "plan.validate-input", "build.section-file-required", "project.session-conflict",
}


def _gate(**over):
    g = {
        "id": "design.x", "phase": "design", "policy": "orchestrator-approve",
        "default_answer": None, "constitution": False, "fires": "always",
        "summary": "a gate", "unattended_answer": "Approve.",
    }
    g.update(over)
    return g


def _errors(gate):
    return validate_catalog(
        {"schemaVersion": 1, "covered_phases": list(COVERED_PHASES), "gates": [gate]}
    )


def test_shipped_allowlist_is_exactly_the_three_design_gates():
    carriers = {gid for gid, g in load_catalog()["gates"].items() if "unattended_answer" in g}
    assert carriers == ALLOWLIST


def test_denylist_is_pinned_and_every_id_exists_in_the_catalog():
    assert set(UNATTENDED_DENYLIST) == DENYLIST
    assert DENYLIST <= set(load_catalog()["gates"])


def test_denylist_families_cover_every_shipped_gate_of_those_names():
    for gid in load_catalog()["gates"]:
        if gid.endswith(("out-of-sequence-continue", "prereqs-missing")):
            assert is_denylisted(gid), gid
    # one per phase that has the sequencing gate (project..deploy, incl. test/changelog)
    seq = [g for g in load_catalog()["gates"] if g.endswith("out-of-sequence-continue")]
    assert len(seq) == 7


def test_no_shipped_denylisted_locked_or_hard_stop_gate_carries_an_answer():
    for gid, g in load_catalog()["gates"].items():
        if is_denylisted(gid) or g["constitution"] or g["policy"] == "hard-stop":
            assert "unattended_answer" not in g, gid


def test_deploy_test_gate_failed_stays_constitution_locked():
    # "Skipping test layers" (constitution ASK FIRST) is carried by this locked gate.
    assert load_catalog()["gates"]["deploy.test-gate-failed"]["constitution"] is True
    assert load_catalog()["gates"]["test.fix-attempts-exhausted"]["constitution"] is True


def test_validator_accepts_an_eligible_gate():
    assert _errors(_gate()) == []


@pytest.mark.parametrize("over", [
    {"constitution": True},
    {"policy": "hard-stop", "constitution": True},
    {"policy": "auto-default", "default_answer": "go"},
    {"id": "build.migration-apply-fail", "phase": "build"},
    {"id": "design.out-of-sequence-continue"},
    {"id": "deploy.migration-prereqs-missing", "phase": "deploy"},
    {"unattended_answer": ""},
    {"unattended_answer": None},
    {"unattended_answer": 3},
])
def test_validator_rejects_an_ineligible_unattended_answer(over):
    errs = _errors(_gate(**over))
    assert any("unattended_answer" in e for e in errs), errs


@pytest.mark.parametrize("gid", sorted(ALLOWLIST))
def test_resolver_reports_the_answer_only_under_unattended(gid):
    cat = load_catalog()
    on = resolve_gate_policy(gid, mode=SINGLE_SESSION, catalog=cat, autonomy="unattended")
    assert on["unattended_answer"] == cat["gates"][gid]["unattended_answer"]
    assert on["should_stop"] is True  # the master/CLI applies it, not the resolver
    for autonomy in (None, "guided", "autonomous"):
        off = resolve_gate_policy(gid, mode=SINGLE_SESSION, catalog=cat, autonomy=autonomy)
        assert off["unattended_answer"] is None


def test_resolver_gives_no_answer_for_a_gate_without_one_or_outside_a_run():
    cat = load_catalog()
    r = resolve_gate_policy("build.migration-apply-fail", mode=SINGLE_SESSION, catalog=cat,
                            autonomy="unattended")
    assert r["unattended_answer"] is None
    inert = resolve_gate_policy("design.preview-approval", mode="standalone", catalog=cat,
                                autonomy="unattended")
    assert inert["unattended_answer"] is None and inert["effective_policy"] == "interactive"


def test_resolver_fails_closed_on_an_unvalidated_ineligible_answer():
    cat = load_catalog()
    cat["gates"]["build.migration-apply-fail"] = {
        **cat["gates"]["build.migration-apply-fail"], "unattended_answer": "Continue."}
    r = resolve_gate_policy("build.migration-apply-fail", mode=SINGLE_SESSION, catalog=cat,
                            autonomy="unattended")
    assert r["unattended_answer"] is None



def test_resolver_denylist_keys_on_the_gate_id_not_an_inner_id():
    cat = load_catalog()
    gate = {**cat["gates"]["build.env-validation-missing-vars"], "unattended_answer": "Continue."}
    gate.pop("id")  # a catalog dict without an inner id must still be denied by the resolver's id
    cat["gates"]["build.env-validation-missing-vars"] = gate
    r = resolve_gate_policy("build.env-validation-missing-vars", mode=SINGLE_SESSION, catalog=cat,
                            autonomy="unattended")
    assert r["unattended_answer"] is None
