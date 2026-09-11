"""Empirical dry-run for AC6 (trg-aedcfe7b): before/after hard-count delta of
the transition rule against a SYNTHETIC fixture modeling the actual measured
population (shipwright-webui's inferred_legacy -> explicit same-day
promotions), since this monorepo's own manifest is 100% inferred_legacy
(already fully covered by the pre-existing legacy valve) and would prove
nothing. Run with: `uv run .shipwright/planning/iterate/iterate-2026-09-11-binding-completeness-rollout-transition/dry_run_fixture.py`
from the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_binding import evaluate_binding_completeness  # noqa: E402


def _node(disp, *, layers, source, coverage, title=None):
    return {
        "id": disp, "spec_path": "", "title": title or f"t-{disp}", "priority": "Must",
        "status": "active", "required_layers": list(layers),
        "required_layers_source": source, "tests": {}, "coverage": coverage,
    }


def _manifest(nodes, *, spec_hash):
    return {
        "schema_version": 3, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


# The webui shape: an FR that was `inferred_legacy` with layers=(unit,) at the
# resolved rollout snapshot, promoted to `explicit` (value unchanged) the same
# day the gate merged, then touched again later (an unrelated AC edit,
# simulated here via a required_layers widening at base->head) once evidence
# at `integration` exists.
base = _manifest({
    "webui::FR-01.01": _node("FR-01.01", layers=(), source="explicit", coverage={}),
    "webui::FR-99.01": _node("FR-99.01", layers=(), source="explicit", coverage={}),
}, spec_hash="sha256:base")

head = _manifest({
    "webui::FR-01.01": _node(
        "FR-01.01", layers=("unit",), source="explicit",
        coverage={"unit": "ok", "integration": "ok"},
    ),
    "webui::FR-99.01": _node(
        "FR-99.01", layers=("unit",), source="explicit",
        coverage={"unit": "ok", "integration": "ok"},
    ),
}, spec_hash="sha256:head")

# Rollout snapshot: FR-01.01 already had layers=(unit,) here (still
# inferred_legacy at that point) -- the webui shape. FR-99.01 is a genuinely
# NEW FR minted after rollout (absent from the snapshot) -- the control.
rollout = _manifest({
    "webui::FR-01.01": _node("FR-01.01", layers=("unit",), source="inferred_legacy", coverage={}),
}, spec_hash="sha256:rollout")


def _hard_count(rollout_arg):
    verdict = evaluate_binding_completeness(base, head, rollout=rollout_arg)
    return len(verdict.hard), len(verdict.advisory), [g.reason for g in verdict.hard]


before_hard, before_advisory, before_reasons = _hard_count(None)
after_hard, after_advisory, after_reasons = _hard_count(rollout)

print(f"BEFORE (rollout=None, today's behaviour): hard={before_hard} advisory={before_advisory}")
print(f"AFTER  (transition rule applied):         hard={after_hard} advisory={after_advisory}")

assert before_hard == 2, before_reasons  # both FR-01.01 and FR-99.01 route HARD today
assert after_hard == 1, after_reasons    # only the genuinely-new control (FR-99.01) stays HARD
assert before_hard - after_hard == 1
print("Hard-count delta: 2 -> 1 (one gap graced; the genuinely-new control is unaffected). OK")
