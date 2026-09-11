"""AC20 (folded acceptance criterion): ``evaluate_cross_layer``'s ``ac_changed_ids``
resolution path, split into its own file so ``test_layer_coverage_core.py`` stays at
its ≤300 LOC cap.

FR-01.11/AC20: "a change that appends an acceptance criterion to an existing
requirement — the pattern ``shared/fr-authoring.md`` §3 recommends — is resolved to
that named requirement and checked at the layers that requirement requires, instead
of being reported as undeterminable." The docstring of
:func:`evaluate_cross_layer` names this exact rule
(``iterate-2026-07-27-name-the-blocker``) — "the row alone was not enough ... a
correctly folded change left the row identical and the gate saw nothing" — but no
existing test drove the ``ac_changed_ids`` parameter before this one: every case in
``test_layer_coverage_core.py`` passes ``ac_changed_ids=None`` (the default) and
either changes the FR's row or asserts the true could-not-determine case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_core import evaluate_cross_layer  # noqa: E402


def _node(disp, *, layers=("e2e",), source="explicit", coverage=None):
    return {
        "id": disp, "spec_path": "", "title": f"t-{disp}", "priority": "Must",
        "status": "active", "required_layers": list(layers),
        "required_layers_source": source, "tests": {}, "coverage": coverage or {},
    }


def _manifest(nodes: dict, *, spec_hash="sha256:x"):
    return {
        "schema_version": 3, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


@pytest.mark.covers("FR-01.11/AC20")
def test_an_ac_only_change_resolves_to_its_requirement_not_could_not_determine():
    """The FR's row (title / required_layers) is byte-identical between base and
    head — only its acceptance criteria changed (the FOLD pattern). Without
    ``ac_changed_ids`` this would fall through to ``could_not_determine``; with it,
    the requirement is resolved and checked at its required layers."""
    base = _manifest({"a::FR-01.01": _node("FR-01.01")}, spec_hash="sha256:x")
    head = _manifest({
        "a::FR-01.01": _node("FR-01.01", coverage={"e2e": "MISSING"}),
    }, spec_hash="sha256:CHANGED")

    v = evaluate_cross_layer(base, head, ac_changed_ids={"FR-01.01"})

    assert not v.could_not_determine
    assert "a::FR-01.01" in v.changed_keys
    assert any(gap.display == "FR-01.01" for gap in v.hard)


@pytest.mark.covers("FR-01.11/AC20")
def test_an_ac_only_change_alongside_a_row_changed_fr_is_not_dropped():
    """Regression this AC also names: an AC-only-changed FR sitting alongside a
    row-changed one must not be silently dropped just because SOME FR's row
    changed (the could-not-determine branch only fires when nothing changed at
    all). FR-01.02's node is BYTE-IDENTICAL between base and head (no title,
    layers, or coverage delta) — external code review, glm, low: the previous
    version gave it a coverage delta too, so it would have entered
    `changed_keys` even with `ac_changed_ids` ignored entirely, proving
    nothing about the parameter under test. Here FR-01.02 can only appear via
    `ac_changed_ids`."""
    base = _manifest({
        "a::FR-01.01": _node("FR-01.01"),
        "a::FR-01.02": _node("FR-01.02"),
    }, spec_hash="sha256:x")
    head = _manifest({
        "a::FR-01.01": _node("FR-01.01", coverage={"e2e": "MISSING"}),
        "a::FR-01.02": _node("FR-01.02"),  # untouched — proves the AC alone
    }, spec_hash="sha256:CHANGED")
    head["requirements"]["a::FR-01.01"]["title"] = "row changed"  # row delta

    v = evaluate_cross_layer(base, head, ac_changed_ids={"FR-01.02"})

    assert not v.could_not_determine
    assert {"a::FR-01.01", "a::FR-01.02"} <= set(v.changed_keys)

    # Mutation-check named by review: WITHOUT ac_changed_ids, FR-01.02 must
    # NOT appear — it has no row delta of its own, so only the parameter
    # under test can put it in changed_keys.
    v_without = evaluate_cross_layer(base, head, ac_changed_ids=None)
    assert "a::FR-01.02" not in v_without.changed_keys
