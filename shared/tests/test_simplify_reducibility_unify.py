"""Cross-surface parity for the simplify <-> reducibility-gate unification
(iterate-2026-06-13-unify-simplify-reducibility).

The OS1 simplify gate and the PR #219 reducibility/bloat gate were two parallel
artifacts sharing the same Osmani lineage. This iterate joins them around ONE
shared tool + ONE shared catalog. These tests pin the join so the two sides
cannot drift back apart:

- the gate tool is SHARED (relocated out of the iterate plugin);
- the catalog cites it as the mechanical "keeps tests green" (G3) proof, scoped
  to executable surfaces (the no-exec CI Tier-3 reviewer is exempt);
- the local diff reviewer cites it too;
- F-simplify.md adopts the catalog's closed vocabulary + guardrails.

Companion to test_reducibility_gate.py (the catalog-shape guard) — kept separate
so neither file grows past the 300-LOC guideline.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CATALOG = REPO_ROOT / "shared" / "reducibility-catalog.md"
CODE_REVIEWER = REPO_ROOT / "plugins" / "shipwright-build" / "agents" / "code-reviewer.md"
BEHAVIOR_SNAPSHOT = REPO_ROOT / "shared" / "scripts" / "tools" / "behavior_snapshot.py"
F_SIMPLIFY = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "F-simplify.md"
)


def test_behavior_snapshot_gate_is_shared_ssot():
    """The gate is shared (relocated out of the iterate plugin) so the catalog
    can cite it without an inverted plugin->shared dependency (MU-PL2)."""
    assert BEHAVIOR_SNAPSHOT.is_file(), f"missing shared gate: {BEHAVIOR_SNAPSHOT}"


def test_catalog_cites_behavior_snapshot_as_mechanical_g3_proof():
    body = CATALOG.read_text(encoding="utf-8")
    low = body.lower()
    assert "behavior_snapshot.py" in body, (
        "catalog must cite behavior_snapshot.py as the mechanical keeps-tests-green proof"
    )
    assert "mechanical" in low and "snapshot" in low and "verify" in low, (
        "catalog must describe the snapshot/verify mechanical proof"
    )
    # The no-exec CI Tier-3 reviewer must be scoped OUT of the mechanical proof.
    assert "tier-3" in low or "self-contained" in low, (
        "catalog must scope the mechanical proof out of the no-exec CI reviewer"
    )


def test_code_reviewer_cites_behavior_snapshot():
    body = CODE_REVIEWER.read_text(encoding="utf-8")
    assert "behavior_snapshot.py" in body, (
        "local diff reviewer must cite behavior_snapshot.py as the G3 mechanical proof"
    )


def test_f_simplify_adopts_the_shared_catalog():
    """The simplify side uses the SAME closed catalog vocabulary + guardrails."""
    assert F_SIMPLIFY.is_file(), f"missing F-simplify.md: {F_SIMPLIFY}"
    body = F_SIMPLIFY.read_text(encoding="utf-8").lower()
    assert "reducibility-catalog.md" in body, (
        "F-simplify.md must cite the shared reducibility catalog as its what-vocabulary"
    )
    # Keyword adjacency (not bare single letters) confirms the vocabulary import.
    for keyword in ("duplication", "dead code", "abstraction", "g1", "g3"):
        assert keyword in body, f"F-simplify.md must name catalog concept {keyword!r}"


def test_guide_documents_the_unification():
    """AC6 — docs/guide.md notes the unified gate (shared tool + shared vocabulary)."""
    guide = REPO_ROOT / "docs" / "guide.md"
    body = guide.read_text(encoding="utf-8").lower()
    assert "behavior_snapshot.py" in body and "reducibility" in body, (
        "guide.md must document the simplify <-> reducibility unification"
    )
