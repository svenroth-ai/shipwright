"""CheckResult-wrapper cases for the binding-completeness F11 gate (P3.3):
``_binding_result``'s message-shaping branches, ``check_binding_completeness``'s
fail-closed infra paths, and its wiring into ``run_all_checks``. Split from
``test_layer_coverage_binding.py`` (that module's own docstring explains why —
same 300-LOC precedent p3.2 already set for ``test_traceability_contract*.py``);
the pure evaluator's own cases stay there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import tools.verifiers.layer_coverage as _lc  # noqa: E402
import tools.verifiers.layer_coverage_binding as _lcb_wrapper  # noqa: E402
from tools.verifiers._layer_coverage_core import CrossLayerVerdict, LayerGap  # noqa: E402
from tools.verifiers.layer_coverage_binding import _binding_result, check_binding_completeness  # noqa: E402


def _seed_medium(root: Path, run_id: str) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": run_id, "complexity": "medium", "type": "change"}],
    }), encoding="utf-8")


def _node(disp, *, status="active", layers=("unit",), source="explicit",
          coverage=None, priority="Must"):
    return {
        "id": disp, "spec_path": "", "title": f"t-{disp}", "priority": priority,
        "status": status, "required_layers": list(layers),
        "required_layers_source": source, "tests": {}, "coverage": coverage or {},
    }


def _manifest(nodes: dict, *, spec_hash="sha256:x"):
    return {
        "schema_version": 3, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


def test_registered_in_run_all_checks(tmp_path):
    from tools.verifiers.iterate_checks import run_all_checks

    names = [r.name for r in run_all_checks(tmp_path, "r1", commit_hash="abc1234")]
    assert any("binding completeness" in n for n in names), names


def test_wrapper_skips_below_medium(tmp_path):
    r = check_binding_completeness(tmp_path, "r-missing", "abc1234")
    assert r.ok is True and r.is_skipped


# --- _binding_result: the CheckResult-shaping branches -----------------------


def test_binding_result_no_changed_keys_is_clean_pass():
    r = _binding_result("n", CrossLayerVerdict(changed_keys=[]))
    assert r.ok is True and not r.is_skipped
    assert "no behaviour-changed FR" in r.detail


def test_binding_result_hard_fail_message():
    gap = LayerGap("FR-09.09", "a::FR-09.09", "integration", "Must", "explicit", "BINDING_INCOMPLETE")
    verdict = CrossLayerVerdict(changed_keys=["a::FR-09.09"], hard=[gap])
    r = _binding_result("n", verdict)
    assert r.ok is False and not r.is_skipped
    assert "FR-09.09: omits integration" in r.detail
    assert "widen the FR's Layers cell" in r.detail


def test_binding_result_advisory_message():
    gap = LayerGap("FR-09.10", "a::FR-09.10", "e2e", "Must", "inferred_legacy", "BINDING_INCOMPLETE")
    verdict = CrossLayerVerdict(changed_keys=["a::FR-09.10"], advisory=[gap])
    r = _binding_result("n", verdict)
    assert r.ok is False and not r.is_skipped
    assert r.severity == "warning" and r.strict_exempt is True
    assert "legacy/collision/pre-rollout (advisory)" in r.detail


def test_binding_result_transition_grace_message_distinguishes_from_legacy():
    # trg-aedcfe7b: an `explicit`-sourced gap downgraded via the transition rule
    # must not read as if the FR were legacy-sourced (g.source is still "explicit").
    gap = LayerGap("FR-09.17", "a::FR-09.17", "integration", "Must", "explicit",
                   "BINDING_INCOMPLETE_TRANSITION")
    verdict = CrossLayerVerdict(changed_keys=["a::FR-09.17"], advisory=[gap])
    r = _binding_result("n", verdict)
    assert r.severity == "warning" and r.strict_exempt is True
    assert "FR-09.17: omits integration (pre-rollout transition grace)" in r.detail
    assert "(explicit)" not in r.detail


def test_binding_result_clean_pass_with_changed_keys():
    verdict = CrossLayerVerdict(changed_keys=["a::FR-09.11"])
    r = _binding_result("n", verdict)
    assert r.ok is True and not r.is_skipped
    assert "binding is complete" in r.detail


def test_binding_result_hard_fail_truncates_with_more_count():
    # External code review (P3.3, glm): a truncated gap list must say how many more
    # there are, not just a count in the header that can exceed what is printed.
    gaps = [LayerGap(f"FR-09.{n}", f"a::FR-09.{n}", "integration", "Must",
                      "explicit", "BINDING_INCOMPLETE") for n in range(20, 28)]
    verdict = CrossLayerVerdict(changed_keys=[g.key for g in gaps], hard=gaps)
    r = _binding_result("n", verdict)
    assert r.ok is False
    assert "(+2 more)" in r.detail


def test_binding_result_advisory_truncates_with_more_count():
    gaps = [LayerGap(f"FR-09.{n}", f"a::FR-09.{n}", "e2e", "Must",
                      "inferred_legacy", "BINDING_INCOMPLETE") for n in range(30, 39)]
    verdict = CrossLayerVerdict(changed_keys=[g.key for g in gaps], advisory=gaps)
    r = _binding_result("n", verdict)
    assert r.severity == "warning"
    assert "(+3 more)" in r.detail


# --- check_binding_completeness: the real-path / infra-error branches --------


def test_wrapper_no_commit_is_infra_error(tmp_path):
    _seed_medium(tmp_path, "r")
    r = check_binding_completeness(tmp_path, "r", "")
    assert r.ok is False and not r.is_skipped
    assert "no --commit" in r.detail


def test_wrapper_regen_none_is_infra_error(tmp_path, monkeypatch):
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head", lambda *a, **k: None)
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is False and not r.is_skipped
    assert "git unavailable" in r.detail


def test_wrapper_ac_error_is_infra_error(tmp_path, monkeypatch):
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head",
                         lambda *a, **k: (_manifest({}), _manifest({}), {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (None, "boom"))
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is False and not r.is_skipped
    assert r.detail.endswith("boom")


def test_wrapper_non_git_precheck_short_circuits(tmp_path):
    # No monkeypatch: a bare (non-git) tmp_path drives the REAL `_git_precheck`, which
    # returns a skip CheckResult the wrapper must return verbatim (the `precheck is not
    # None` branch) without ever reaching the regen try-block.
    _seed_medium(tmp_path, "r")
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.is_skipped
    assert "not a git work tree" in r.detail


def test_wrapper_regen_exception_is_infra_error(tmp_path, monkeypatch):
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head", _boom)
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is False and not r.is_skipped
    assert "regeneration error: RuntimeError" in r.detail


def test_wrapper_full_success_path_clean(tmp_path, monkeypatch):
    # Drives the wrapper all the way through a real evaluate_binding_completeness()
    # call (no row/AC delta between base and head) and back out through _binding_result.
    node = _node("FR-09.12", coverage={"unit": "ok"})
    manifest = _manifest({"a::FR-09.12": node})
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head",
                         lambda *a, **k: (manifest, manifest, {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (set(), None))
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is True and not r.is_skipped
    assert "no behaviour-changed FR" in r.detail


def test_wrapper_clean_path_never_calls_rollout_manifest(tmp_path, monkeypatch):
    # Performance contract (internal plan review): the rollout snapshot must be
    # LAZY — never built when there is no candidate HARD gap to downgrade.
    node = _node("FR-09.15", coverage={"unit": "ok"})
    manifest = _manifest({"a::FR-09.15": node})
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head",
                         lambda *a, **k: (manifest, manifest, {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (set(), None))

    def _boom(*a, **k):
        raise AssertionError("rollout_manifest must not be called on a clean run")

    monkeypatch.setattr(_lcb_wrapper, "rollout_manifest", _boom)
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is True and not r.is_skipped


def test_wrapper_full_path_hard_gap_propagates(tmp_path, monkeypatch):
    # External code review (P3.3, openai): the prior full-path test only exercised a
    # clean manifest, so a wrapper regression that drops the evaluator's verdict, or
    # supplies the wrong base/head, would still pass. This drives the SAME real
    # evaluate_binding_completeness() call with an actual unit-only-binding /
    # integration-passing gap and asserts the wrapper propagates a hard failure.
    base = _manifest({"a::FR-09.13": _node("FR-09.13", layers=("unit",))})
    head = _manifest({
        "a::FR-09.13": _node("FR-09.13", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:changed")
    head["requirements"]["a::FR-09.13"]["title"] = "changed"
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head", lambda *a, **k: (base, head, {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (set(), None))
    monkeypatch.setattr(_lcb_wrapper, "rollout_manifest", lambda *a, **k: None)
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is False and not r.is_skipped
    assert "FR-09.13: omits integration" in r.detail


def test_wrapper_transition_grace_downgrades_hard_gap_to_advisory(tmp_path, monkeypatch):
    # trg-aedcfe7b: an otherwise-HARD gap whose required_layers value already
    # existed at the resolved rollout snapshot is downgraded end-to-end through
    # the wrapper, not just in the pure evaluator. The change trigger is base's
    # required_layers differing from head's (NOT a forced title edit — the
    # rollout snapshot's title must match head's for grace to apply at all, so
    # forcing only head's title would deny grace via title-mismatch instead of
    # exercising the value-match path this test is actually about; external
    # code review, P3.3 follow-up, glm, HIGH).
    base = _manifest({"a::FR-09.16": _node("FR-09.16", layers=())})
    head = _manifest({
        "a::FR-09.16": _node("FR-09.16", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:changed")
    rollout = _manifest({"a::FR-09.16": _node("FR-09.16", layers=("unit",))})
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head", lambda *a, **k: (base, head, {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (set(), None))
    monkeypatch.setattr(_lcb_wrapper, "rollout_manifest", lambda *a, **k: rollout)
    r = check_binding_completeness(tmp_path, "r", "abc1234")
    assert r.ok is False and r.severity == "warning" and r.strict_exempt is True
    assert "FR-09.16: omits integration (pre-rollout transition grace)" in r.detail


def test_run_all_checks_binding_gap_propagates_to_failure(tmp_path, monkeypatch):
    # External code review (P3.3, glm): pin that the check is wired with the RIGHT
    # arguments into run_all_checks, not merely present by name — a real gap must
    # surface as a failure in the aggregate result list, not just in isolation.
    from tools.verifiers.iterate_checks import run_all_checks

    base = _manifest({"a::FR-09.14": _node("FR-09.14", layers=("unit",))})
    head = _manifest({
        "a::FR-09.14": _node("FR-09.14", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:changed")
    head["requirements"]["a::FR-09.14"]["title"] = "changed"
    _seed_medium(tmp_path, "r")
    monkeypatch.setattr(_lc, "_git_precheck", lambda *a, **k: None)
    monkeypatch.setattr(_lcb_wrapper, "regenerate_base_head", lambda *a, **k: (base, head, {}))
    monkeypatch.setattr(_lcb_wrapper, "changed_criteria_ids", lambda *a, **k: (set(), None))
    monkeypatch.setattr(_lcb_wrapper, "rollout_manifest", lambda *a, **k: None)
    results = run_all_checks(tmp_path, "r", commit_hash="abc1234")
    binding = next(r for r in results if "binding completeness" in r.name)
    assert binding.ok is False and not binding.is_skipped
    assert "FR-09.14" in binding.detail
