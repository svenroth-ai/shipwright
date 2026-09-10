"""THE KEYSTONE GATE's post-merge DETECTIVE arm (ruling Q5) —
``_keystone_detective_core``, the greenness-recomputation half.

Design: ``.shipwright/planning/iterate/2026-09-10-keystone-detective-arm.md``.
Covers AC-D6, AC-D7, AC-D8, AC-D9, AC-D11 and the ``build_verified_manifest``
mutation contract — everything about substituting CI-verified per-link
status/executed into the committed manifest and recomputing the keystone
verdict from it. The classification/short-circuit half (AC-D1..D5, D10, D12,
D13) is in ``test_keystone_detective_core.py`` — split at 300 LOC, same
discipline `_keystone_ac_digest_never_silent.py` used to buy back headroom
from its sibling.

Both cross-commit resolvers (`resolve_ci_verification`,
`resolve_execution_evidence`) are MOCKED here for the same reason as the
sibling module: they are frozen, already-reviewed, with their own test
suites. Everything git-facing uses a REAL repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers import _keystone_detective_core as dc  # noqa: E402
from verifiers._keystone_base_manifest import ReadError  # noqa: E402

from _keystone_repo import (  # noqa: E402
    bound_manifest, make_evidence as _evidence, make_verification as _verification,
    repo_with_ac01_edit as _repo_with_ac01_edit,
)

import pytest  # noqa: E402

SHARED_LINK_ID = "tests/test_widget.py::test_fizz"


# --------------------------------------------------------------------------
# AC-D6 / AC-D7 — recomputed verdict drives the outcome, overriding the
# committed file's own self-report
# --------------------------------------------------------------------------

def test_confirmed_evidence_all_green_is_gate_confirmed_clean(tmp_path, monkeypatch):
    """AC-D6: verified evidence agreeing with the committed manifest ->
    `gate_confirmed_clean`."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(
        dc, "resolve_execution_evidence",
        lambda *a, **kw: _evidence(
            "confirmed", run_id=9,
            requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "status": "enabled", "executed": "pass"}]}}},
        ),
    )

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.GATE_CONFIRMED_CLEAN
    assert result.verdict is not None
    assert not result.verdict.any_hard


def test_verified_evidence_overrides_the_committed_files_own_self_report(tmp_path, monkeypatch):
    """AC-D7: the committed manifest self-reports the bound link as PASS,
    but the CI-verified evidence says it actually FAILED — the recomputed
    verdict must follow the verified evidence, not the committed bytes,
    which is the entire point of a detective control."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path, committed_executed="pass")
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(
        dc, "resolve_execution_evidence",
        lambda *a, **kw: _evidence(
            "confirmed", run_id=9,
            requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "status": "enabled", "executed": "fail"}]}}},
        ),
    )

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.GATE_VIOLATED
    assert result.verdict is not None
    assert result.verdict.any_hard


# --------------------------------------------------------------------------
# AC-D8 — a link with no matching verified evidence is fail-closed, not
# silently trusted from the committed file
# --------------------------------------------------------------------------

def test_a_link_absent_from_verified_evidence_is_fail_closed_not_run(tmp_path, monkeypatch):
    """AC-D8: verified evidence for the requirement exists but does not
    mention the bound link's id at all -> treated as `not_run`, not as the
    committed file's `pass`."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path, committed_executed="pass")
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(
        dc, "resolve_execution_evidence",
        lambda *a, **kw: _evidence(
            "confirmed", run_id=9,
            requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": "tests/test_other.py::test_unrelated", "status": "enabled", "executed": "pass"}]}}},
        ),
    )

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.GATE_VIOLATED
    assert result.verdict is not None
    assert result.verdict.any_hard


# --------------------------------------------------------------------------
# AC-D9 — matching is scoped per requirement key; the same link id under a
# different requirement does not cross-contaminate
# --------------------------------------------------------------------------

def test_the_same_link_id_under_two_requirements_resolves_independently():
    """AC-D9: `SHARED_LINK_ID` appears under both FR-01.01 and FR-01.02 in
    the committed manifest. Verified evidence reports it PASS under
    FR-01.01 but only reports FR-01.02 with a DIFFERENT id — so FR-01.02's
    copy of `SHARED_LINK_ID` must resolve to `not_run` (fail-closed,
    unmatched), not inherit FR-01.01's `pass` by id alone."""
    manifest = bound_manifest(executed="pass")
    manifest["requirements"]["ns::FR-01.02"]["acs"]["AC03"] = {"tests": {"unit": [
        {"id": SHARED_LINK_ID, "status": "enabled", "executed": "pass"}
    ]}}

    evidence = _evidence(
        "confirmed", run_id=9,
        requirements={
            "ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "status": "enabled", "executed": "pass"}]}},
            "ns::FR-01.02": {"tests": {"unit": [{"id": "tests/test_other.py::test_unrelated", "status": "enabled", "executed": "pass"}]}},
        },
    )

    verified = dc.build_verified_manifest(manifest, evidence)

    fr1_link = verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    fr2_link = verified["requirements"]["ns::FR-01.02"]["acs"]["AC03"]["tests"]["unit"][0]
    assert fr1_link["executed"] == "pass"
    assert fr2_link["executed"] == "not_run"


# --------------------------------------------------------------------------
# AC-D11 — duplicate verified link ids within one requirement fail closed
# --------------------------------------------------------------------------

def test_duplicate_verified_link_ids_within_one_requirement_fail_closed():
    """AC-D11: two links sharing an `id` within the SAME requirement's
    verified evidence is an ambiguous, hand-editable shape — raise rather
    than silently picking one via last-write-wins."""
    manifest = bound_manifest(executed="pass")
    evidence = _evidence(
        "confirmed", run_id=9,
        requirements={
            "ns::FR-01.01": {"tests": {"unit": [
                {"id": SHARED_LINK_ID, "status": "enabled", "executed": "pass"},
                {"id": SHARED_LINK_ID, "status": "enabled", "executed": "fail"},
            ]}},
        },
    )

    with pytest.raises(ReadError):
        dc.build_verified_manifest(manifest, evidence)


def test_a_verified_link_missing_status_or_executed_is_treated_as_absent():
    """AC-D11 (adjacent): a verified link whose OWN `status`/`executed`
    fields are missing or non-string must not write `None` into the
    manifest — it is treated as if the id were absent entirely, falling
    through to the same fail-closed `not_run` an unmatched link gets
    (external code review round 2, glm, low)."""
    manifest = bound_manifest(executed="pass")
    evidence = _evidence(
        "confirmed", run_id=9,
        requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "status": "enabled"}]}}},
    )

    verified = dc.build_verified_manifest(manifest, evidence)

    link = verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    assert link["executed"] == "not_run"
    assert link["status"] == "enabled"


def test_a_verified_link_missing_status_specifically_is_treated_as_absent():
    """AC-D11 (adjacent, PR review Tier-3, comment): the sibling case of the
    test above — missing/non-string `status` specifically (not `executed`) —
    gets its own case rather than relying on the other field's coverage to
    imply it."""
    manifest = bound_manifest(executed="pass")
    evidence = _evidence(
        "confirmed", run_id=9,
        requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "executed": "pass"}]}}},
    )

    verified = dc.build_verified_manifest(manifest, evidence)

    link = verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    assert link["executed"] == "not_run"
    assert link["status"] == "enabled"


def test_a_non_mapping_requirement_node_is_treated_as_no_verified_evidence():
    """A malformed requirement node in the verified evidence (not a mapping at
    all) must not raise `AttributeError` from `.get`/`.items()` -- it is
    treated the same as the requirement being absent, so every link under it
    falls through to the fail-closed `not_run` an unmatched id already gets
    (PR review, Tier-3, blocking)."""
    manifest = bound_manifest(executed="pass")
    evidence = _evidence("confirmed", run_id=9, requirements={"ns::FR-01.01": ["not", "a", "mapping"]})

    verified = dc.build_verified_manifest(manifest, evidence)

    link = verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    assert link["executed"] == "not_run"
    assert link["status"] == "enabled"


def test_a_non_mapping_tests_value_is_treated_as_no_verified_evidence():
    """Same as above, one level deeper: the requirement node IS a mapping but
    its `tests` value is not (PR review, Tier-3, blocking)."""
    manifest = bound_manifest(executed="pass")
    evidence = _evidence("confirmed", run_id=9, requirements={"ns::FR-01.01": {"tests": ["not", "a", "mapping"]}})

    verified = dc.build_verified_manifest(manifest, evidence)

    link = verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    assert link["executed"] == "not_run"
    assert link["status"] == "enabled"


# --------------------------------------------------------------------------
# Mutation contract — build_verified_manifest must not share mutable state
# with its input
# --------------------------------------------------------------------------

def test_build_verified_manifest_does_not_mutate_or_share_state_with_the_input():
    """No aliasing ANYWHERE in the returned tree (external code review round
    2, both reviewers, medium — the first fix only deep-copied the two
    explicit pass-through branches; a top-level sibling key, and a sibling
    key WITHIN a substituted requirement/AC node, both still aliased the
    input). Covers: a top-level key outside `requirements`; a sibling key on
    a requirement node that WAS substituted (FR-01.01, alongside its
    substituted link); and the untouched pass-through requirement FR-01.02
    (`bound_manifest`'s own `acs: {}`)."""
    manifest = bound_manifest(executed="pass")
    manifest["schema_version"] = 4
    evidence = _evidence(
        "confirmed", run_id=9,
        requirements={"ns::FR-01.01": {"tests": {"unit": [{"id": SHARED_LINK_ID, "status": "enabled", "executed": "fail"}]}}},
    )

    verified = dc.build_verified_manifest(manifest, evidence)
    verified["schema_version"] = "mutated"
    verified["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]["executed"] = "mutated"
    verified["requirements"]["ns::FR-01.01"]["required_layers_source"] = "mutated"
    verified["requirements"]["ns::FR-01.02"]["status"] = "mutated"

    assert manifest["schema_version"] == 4
    original_link = manifest["requirements"]["ns::FR-01.01"]["acs"]["AC01"]["tests"]["unit"][0]
    assert original_link["executed"] == "pass"
    assert manifest["requirements"]["ns::FR-01.01"]["required_layers_source"] == "inferred_legacy"
    assert manifest["requirements"]["ns::FR-01.02"]["status"] == "active"
