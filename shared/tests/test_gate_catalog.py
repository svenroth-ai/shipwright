"""Catalog-integrity + validator tests for the phase-gate mechanism (SS2).

The committed catalog (shared/config/gate_catalog.json) must load, pass every
invariant, and pin Sven's 2026-07-07 sensitive-gate decisions. ``validate_catalog``
must reject each class of corrupt data. See ``test_gate_policy.py`` for the
resolver/mode/dry-run coverage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.gate_policy import (
    COVERED_PHASES,
    FIRES,
    POLICIES,
    GateCatalogError,
    load_catalog,
    validate_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _REPO_ROOT / "shared" / "config" / "gate_catalog.json"


# --------------------------------------------------------------------------- #
# Committed-catalog integrity
# --------------------------------------------------------------------------- #

def test_shipped_catalog_loads_and_validates():
    catalog = load_catalog()
    assert catalog["schemaVersion"] == 1
    assert len(catalog["gates"]) >= 40  # ~47 gates across 5 phases


def test_every_covered_phase_has_gates():
    catalog = load_catalog()
    phases_present = {g["phase"] for g in catalog["gates"].values()}
    for phase in COVERED_PHASES:
        assert phase in phases_present, f"no gates cataloged for phase {phase!r}"


def test_gate_ids_are_unique_and_phase_prefixed():
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    ids = [g["id"] for g in raw["gates"]]
    assert len(ids) == len(set(ids)), "duplicate gate ids"
    for g in raw["gates"]:
        assert g["id"].startswith(g["phase"] + "."), (
            f"gate id {g['id']!r} not prefixed by its phase {g['phase']!r}"
        )


def test_every_gate_has_valid_fields():
    catalog = load_catalog()
    for gid, g in catalog["gates"].items():
        assert g["policy"] in POLICIES
        assert g["fires"] in FIRES
        assert g["phase"] in COVERED_PHASES
        assert isinstance(g["constitution"], bool)
        assert isinstance(g["summary"], str) and g["summary"].strip()


# --------------------------------------------------------------------------- #
# Safety invariants (constitution AskUserQuestion discipline, in data)
# --------------------------------------------------------------------------- #

def test_no_constitution_gate_is_auto_default():
    catalog = load_catalog()
    for gid, g in catalog["gates"].items():
        if g["constitution"]:
            assert g["policy"] != "auto-default", (
                f"{gid} is constitution-locked but marked auto-default"
            )


def test_auto_default_gates_carry_a_default_answer():
    catalog = load_catalog()
    for gid, g in catalog["gates"].items():
        if g["policy"] == "auto-default":
            assert isinstance(g["default_answer"], str) and g["default_answer"].strip(), (
                f"{gid} is auto-default but has no default_answer"
            )
        else:
            assert g["default_answer"] is None, (
                f"{gid} is {g['policy']} but carries a default_answer"
            )


# Terms that mark a genuinely dangerous operation. A gate mentioning one MUST be
# constitution-locked (never auto-default) unless it is an explicitly reviewed
# exception — a defense-in-depth net so a NEW dangerous gate can't slip in as
# auto-default even if the manual census misclassifies it (external-review #9).
_DANGER_TERMS = ("destructive", "rollback", "truncate", "drop table", "apply fail")
# deploy.smoke-fail-auto-rollback is the documented automatic recovery: it is NOT
# an AskUserQuestion gate, it restores last-known-good and announces itself
# (rollback-discipline Pattern 3). Reviewed + intentionally auto-default.
_REVIEWED_AUTO_EXCEPTIONS = {"deploy.smoke-fail-auto-rollback"}


def test_danger_keyword_gates_are_constitution_locked():
    for gid, g in load_catalog()["gates"].items():
        hay = (gid + " " + g["summary"]).lower()
        looks_dangerous = "prod-" in gid or any(t in hay for t in _DANGER_TERMS)
        if not looks_dangerous or gid in _REVIEWED_AUTO_EXCEPTIONS:
            continue
        assert g["constitution"] is True and g["policy"] != "auto-default", (
            f"{gid} reads as a dangerous operation but is not constitution-locked "
            f"(policy={g['policy']}, constitution={g['constitution']}). Mark it "
            f"constitution:true (hard-stop/orchestrator-approve) or add it to "
            f"_REVIEWED_AUTO_EXCEPTIONS with a rationale."
        )


def test_known_sensitive_gates_have_confirmed_policies():
    """Pin Sven's 2026-07-07 sensitive-gate decisions against silent drift."""
    gates = load_catalog()["gates"]
    assert gates["design.preview-approval"]["policy"] == "orchestrator-approve"
    assert gates["design.review-loop-finalize"]["policy"] == "orchestrator-approve"
    for gid in (
        "deploy.prod-deploy-confirm",
        "deploy.prod-migration-apply",
        "deploy.destructive-migration-confirm",
        "deploy.migration-verify-failed",
        "deploy.manual-rollback-select-confirm",
        "build.destructive-sql-confirm",
        "build.migration-apply-fail",
    ):
        assert gates[gid]["policy"] == "hard-stop", f"{gid} must be hard-stop"
        assert gates[gid]["constitution"] is True


# --------------------------------------------------------------------------- #
# validate_catalog — rejects each class of corrupt data (non-raising helper)
# --------------------------------------------------------------------------- #

def _minimal_gate(**over):
    g = {
        "id": "project.x",
        "phase": "project",
        "policy": "auto-default",
        "default_answer": "do the thing",
        "constitution": False,
        "fires": "always",
        "summary": "a gate",
    }
    g.update(over)
    return g


def _wrap(gates):
    return {"schemaVersion": 1, "covered_phases": list(COVERED_PHASES), "gates": gates}


def test_validate_rejects_constitution_auto_default():
    errs = validate_catalog(_wrap([_minimal_gate(constitution=True)]))
    assert any("constitution" in e.lower() for e in errs)


def test_validate_rejects_auto_default_without_answer():
    errs = validate_catalog(_wrap([_minimal_gate(default_answer=None)]))
    assert any("default_answer" in e for e in errs)


def test_validate_rejects_non_auto_default_with_answer():
    errs = validate_catalog(
        _wrap([_minimal_gate(policy="hard-stop", constitution=True, default_answer="oops")])
    )
    assert any("default_answer" in e for e in errs)


def test_validate_rejects_unknown_policy_phase_fires():
    assert validate_catalog(_wrap([_minimal_gate(policy="nope")]))
    assert validate_catalog(_wrap([_minimal_gate(phase="nope")]))
    assert validate_catalog(_wrap([_minimal_gate(fires="sometimes")]))


def test_validate_rejects_duplicate_ids():
    errs = validate_catalog(_wrap([_minimal_gate(), _minimal_gate()]))
    assert any("duplicate" in e.lower() for e in errs)


def test_validate_accepts_a_wellformed_catalog():
    assert validate_catalog(_wrap([_minimal_gate()])) == []


def test_load_raises_on_corrupt_catalog(tmp_path):
    bad = tmp_path / "gate_catalog.json"
    bad.write_text(json.dumps(_wrap([_minimal_gate(constitution=True)])), encoding="utf-8")
    with pytest.raises(GateCatalogError):
        load_catalog(bad)
