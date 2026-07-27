"""The cross-layer VERDICT once folded criteria are visible
(iterate-2026-07-27-name-the-blocker).

The parser that turns a spec into per-requirement criteria digests is pinned in
`test_layer_coverage_criteria.py`. This is the other half: what the gate DOES
with those digests — the union of row-changed and criteria-changed requirements,
what stays undecidable, and the fail-closed wiring when a spec cannot be read.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers._layer_coverage_core import evaluate_cross_layer  # noqa: E402

# --- the verdict --------------------------------------------------------------

def _manifest(*, spec_hash: str, **layers) -> dict:
    return {
        "spec_hash": spec_hash,
        "requirements": {
            f"01::{fr}": {
                "id": fr, "status": "active", "title": f"title {fr}",
                "spec_path": "spec.md", "priority": "Must",
                "required_layers": ["unit"], "required_layers_source": "explicit",
                "coverage": {"unit": cov},
            }
            for fr, cov in layers.items()
        },
    }


def test_a_folded_criterion_resolves_to_its_named_requirement():
    """The headline fix: the fold is seen, and the requirement is named."""
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "MISSING"})

    verdict = evaluate_cross_layer(base, head, {"FR-01.01"})

    assert verdict.could_not_determine is False
    assert verdict.changed_keys == ["01::FR-01.01"]
    assert [g.display for g in verdict.hard] == ["FR-01.01"]


def test_a_folded_criterion_with_a_passing_test_is_green():
    base = _manifest(spec_hash="a", **{"FR-01.01": "ok"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "ok"})

    verdict = evaluate_cross_layer(base, head, {"FR-01.01"})

    assert verdict.hard == [] and verdict.advisory == []
    assert verdict.changed_keys == ["01::FR-01.01"]


def test_an_ac_only_change_alongside_a_row_change_is_no_longer_dropped():
    """The quieter half. `could_not_determine` was only reachable when NOTHING
    changed at row level, so when another requirement's row DID change, the
    AC-only-changed one vanished with no warning at all."""
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING", "FR-01.02": "MISSING"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "MISSING", "FR-01.02": "MISSING"})
    head["requirements"]["01::FR-01.02"]["title"] = "renamed"  # a row change

    verdict = evaluate_cross_layer(base, head, {"FR-01.01"})

    assert sorted(verdict.changed_keys) == ["01::FR-01.01", "01::FR-01.02"]


def test_criteria_change_on_an_inactive_requirement_is_not_invented():
    """A removed requirement's section disappearing is the removal gate's
    business, not this one's."""
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "MISSING"})
    head["requirements"]["01::FR-01.01"]["status"] = "removed"

    verdict = evaluate_cross_layer(base, head, {"FR-01.01"})

    assert verdict.changed_keys == []


def test_undecidable_stays_undecidable():
    """The posture that must survive: a spec edit touching no row and no
    criterion is still visibly could-not-determine, NOT a silent pass."""
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "MISSING"})

    verdict = evaluate_cross_layer(base, head, set())

    assert verdict.could_not_determine is True


def test_a_pure_refactor_is_still_green():
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    head = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})

    verdict = evaluate_cross_layer(base, head, set())

    assert verdict.could_not_determine is False and verdict.changed_keys == []


def test_omitting_the_argument_preserves_the_old_behaviour():
    """Back-compat: every existing caller and test passes two arguments."""
    base = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    head = _manifest(spec_hash="b", **{"FR-01.01": "MISSING"})

    assert evaluate_cross_layer(base, head).could_not_determine is True


# --- the gate's fail-closed wiring --------------------------------------------

def test_an_unreadable_spec_blocks_a_medium_iterate_rather_than_reading_as_unchanged(
    tmp_path, monkeypatch,
):
    """The fail-closed seam. If the criteria cannot be read, the gate must NOT
    fall through to "no criteria changed" — that would be a false green exactly
    when the gate is least able to see. At medium+ it is an error that blocks."""
    import verifiers.layer_coverage as lc

    manifest = _manifest(spec_hash="a", **{"FR-01.01": "MISSING"})
    monkeypatch.setattr(lc, "_complexity", lambda root, run_id: "medium")
    monkeypatch.setattr(lc, "_git_precheck", lambda name, root, cx: None)
    monkeypatch.setattr(lc, "regenerate_base_head", lambda *a, **k: (manifest, manifest, {}))
    monkeypatch.setattr(lc, "_merge_base", lambda root, commit: "basesha")
    monkeypatch.setattr(
        lc, "changed_criteria_ids",
        lambda *a, **k: (set(), "could not read spec.md at base commit"),
    )

    result = lc.check_cross_layer_coverage(tmp_path, "run-1", "headsha")

    assert result.ok is False
    assert result.severity != "warning"          # blocks, not advisory
    assert "could not read spec.md" in result.detail


def test_the_same_unreadable_spec_only_skips_below_medium(tmp_path, monkeypatch):
    """Below medium the gate does not run at all — an infra gap there is a skip,
    which is the pre-existing contract and is unchanged by this iterate."""
    import verifiers.layer_coverage as lc

    monkeypatch.setattr(lc, "_complexity", lambda root, run_id: "small")
    result = lc.check_cross_layer_coverage(tmp_path, "run-1", "headsha")
    assert result.severity == "skipped"
