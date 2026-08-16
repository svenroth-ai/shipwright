"""S0: the FR-gate rejects requirement ids that exist in no spec.

Before this, the gate checked only that the declared list was non-empty, so
``--affected-frs FR-99.99`` passed. Existence was verified only by detective
check D2 — MEDIUM, non-blocking, post-merge — which is why dangling references
are present in the repo today.

Graduated by design (campaign SPEC §4 S0, AC5): unknown-while-known-set-exists
is a HARD failure, but an absent planning directory or a spec set that parses to
zero requirements must NOT block — a customer repo is never bricked by a gate it
cannot satisfy. Fail-open on *unavailable* is not fail-open on *unknown*.

Own file, not appended to the baseline-capped gate/classification tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "scripts" / "tools", _ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.fr_classification import unknown_fr_ids  # noqa: E402
from record_event import (  # noqa: E402
    _fr_existence_gate_error,
    collect_known_fr_ids,
)

_SPEC = """# Specification — demo / 01-adopted

## Functional Requirements

| ID | Name | Priority | Description | Source |
|----|------|----------|-------------|--------|
| FR-01.01 | Does a thing | Must | It does the thing. | `x.py` |
| FR-01.02 | Does another | Must | It does the other thing. | `y.py` |
"""


def _make_project(tmp_path, *, spec: str | None = _SPEC):
    """A project tree with (or deliberately without) a parseable spec."""
    if spec is not None:
        split = tmp_path / ".shipwright" / "planning" / "01-adopted"
        split.mkdir(parents=True)
        (split / "spec.md").write_text(spec, encoding="utf-8")
    return tmp_path


# trg-8db840a6: a quality requirement adopt detects (CI/lint enforcement, in
# this shape) folds into an ordinary FR row (`spec_document.fold_features`),
# in the 7-column shape `fr_table_shape`/`spec_table` actually emit — not the
# simplified 5-column fixture above. FR-01.03 is the folded QR row: no
# source/url (`Basis: assumed`), no surface signal (`Layers: unit (inferred)`).
_QR_FOLDED_SPEC = """# Specification — demo / 01-adopted

## Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Adopted | Dashboard | Must | User views active projects | code | unit, e2e (inferred) |
| FR-01.02 | Adopted | Login | Must | User logs in | code | unit, e2e (inferred) |
| FR-01.03 | Adopted | CI pipeline (github-actions) must pass on pull requests. | Must | CI pipeline (github-actions) must pass on pull requests. | assumed | unit (inferred) |
"""


class TestUnknownFrIdsPredicate:
    """Pure, stdlib-only. Takes the known set as a parameter — it must never
    reach for the filesystem (fr_classification.py:17-19 keeps that module
    loadable pollution-free by the compliance plugin)."""

    def test_all_known_returns_empty(self):
        assert unknown_fr_ids(["FR-01.01", "FR-01.02"], {"FR-01.01", "FR-01.02"}) == []

    def test_single_unknown_is_reported(self):
        assert unknown_fr_ids(["FR-99.99"], {"FR-01.01"}) == ["FR-99.99"]

    def test_multiple_unknown_preserve_declared_order(self):
        out = unknown_fr_ids(["FR-09.09", "FR-01.01", "FR-03.01"], {"FR-01.01"})
        assert out == ["FR-09.09", "FR-03.01"]

    def test_empty_declared_returns_empty(self):
        assert unknown_fr_ids([], {"FR-01.01"}) == []
        assert unknown_fr_ids(None, {"FR-01.01"}) == []

    def test_whitespace_is_trimmed_before_comparison(self):
        assert unknown_fr_ids([" FR-01.01 "], {"FR-01.01"}) == []

    def test_blank_and_non_string_entries_are_ignored(self):
        # A present-but-empty tag is the no-FR case, not an unknown id.
        assert unknown_fr_ids(["", "   ", None, 7], {"FR-01.01"}) == []

    def test_empty_known_set_reports_everything(self):
        # The predicate reports; the CALLER decides this is the warn case.
        assert unknown_fr_ids(["FR-01.01"], set()) == ["FR-01.01"]

    def test_duplicates_reported_once(self):
        assert unknown_fr_ids(["FR-99.99", "FR-99.99"], {"FR-01.01"}) == ["FR-99.99"]


class TestExistenceGate:
    def _event(self, **overrides) -> dict:
        event = {"type": "work_completed", "source": "iterate", "intent": "change"}
        event.update(overrides)
        return event

    KNOWN = frozenset({"FR-01.01", "FR-01.02"})

    # --- AC1 / AC2: the hard failures -------------------------------------

    def test_unknown_affected_fr_is_blocked(self):
        err = _fr_existence_gate_error(
            self._event(affected_frs=["FR-99.99"]), self.KNOWN, specs_found=True)
        assert err is not None
        assert err["error"] == "fr_gate_unknown_fr"
        assert "FR-99.99" in err["detail"]

    def test_unknown_new_fr_is_blocked(self):
        # A minted requirement that never reached a spec exists only in the
        # event log — the exact drift this campaign exists to end.
        err = _fr_existence_gate_error(
            self._event(new_frs=["FR-42.01"]), self.KNOWN, specs_found=True)
        assert err is not None
        assert err["error"] == "fr_gate_unknown_fr"
        assert "FR-42.01" in err["detail"]

    def test_error_names_every_offending_id(self):
        err = _fr_existence_gate_error(
            self._event(affected_frs=["FR-99.99", "FR-01.01"], new_frs=["FR-42.01"]),
            self.KNOWN, specs_found=True)
        assert err is not None
        assert "FR-99.99" in err["detail"] and "FR-42.01" in err["detail"]
        assert "FR-01.01" not in err["detail"]  # the known one is not blamed

    # --- AC3: nothing else changes ----------------------------------------

    def test_known_ids_pass(self):
        assert _fr_existence_gate_error(
            self._event(affected_frs=["FR-01.01"]), self.KNOWN, specs_found=True) is None

    def test_no_fr_change_type_branch_untouched(self):
        # No FRs declared at all — this gate has nothing to say; the existing
        # change_type gate owns that decision.
        assert _fr_existence_gate_error(
            self._event(change_type="docs", none_reason="readme typo"),
            self.KNOWN, specs_found=True) is None

    def test_non_iterate_event_bypasses(self):
        assert _fr_existence_gate_error(
            {"type": "work_completed", "source": "build", "affected_frs": ["FR-99.99"]},
            self.KNOWN, specs_found=True) is None

    def test_non_work_completed_event_bypasses(self):
        assert _fr_existence_gate_error(
            {"type": "phase_started", "source": "iterate", "affected_frs": ["FR-99.99"]},
            self.KNOWN, specs_found=True) is None

    def test_non_dict_bypasses_without_crashing(self):
        assert _fr_existence_gate_error(None, self.KNOWN, specs_found=True) is None

    # --- AC5: graduated, so a customer repo is never bricked ---------------

    def test_absent_planning_dir_does_not_block(self):
        # Nothing to check against. Blocking here would make the gate
        # un-adoptable for a repo that has not been onboarded.
        assert _fr_existence_gate_error(
            self._event(affected_frs=["FR-99.99"]), frozenset(), specs_found=False) is None

    def test_zero_parsed_requirements_does_not_block(self):
        # The dangerous "blind scanner" case: specs exist but parse to nothing.
        # It must not pass silently — the caller warns — but it must not block.
        assert _fr_existence_gate_error(
            self._event(affected_frs=["FR-99.99"]), frozenset(), specs_found=True) is None


class TestCollectorDistinguishesTheThreeCases:
    """AC5 lives or dies here. `collect_requirements_from_planning` returns []
    for BOTH "no planning dir" and "specs parse to nothing", so the collector
    must probe presence separately or the gate silently stops enforcing."""

    def test_real_spec_yields_its_ids(self, tmp_path):
        ids, found = collect_known_fr_ids(_make_project(tmp_path))
        assert found is True
        assert ids == frozenset({"FR-01.01", "FR-01.02"})

    def test_absent_planning_dir_is_not_found(self, tmp_path):
        ids, found = collect_known_fr_ids(_make_project(tmp_path, spec=None))
        assert found is False and ids == frozenset()

    def test_spec_present_but_unparseable_is_found_with_no_ids(self, tmp_path):
        # This is the case that must WARN rather than pass silently.
        root = _make_project(tmp_path, spec="# Spec\n\nNo table here.\n")
        ids, found = collect_known_fr_ids(root)
        assert found is True and ids == frozenset()

    def test_collector_never_raises_on_a_broken_root(self):
        ids, found = collect_known_fr_ids("\x00 not a path")
        assert found is False and ids == frozenset()


class TestWiringActuallyEnforces:
    """The gate must not be dead capital. These drive the real write paths."""

    def _iterate_event(self, **overrides) -> dict:
        event = {"type": "work_completed", "source": "iterate", "intent": "change"}
        event.update(overrides)
        return event

    def test_end_to_end_unknown_fr_blocked_against_a_real_spec(self, tmp_path):
        root = _make_project(tmp_path)
        known, found = collect_known_fr_ids(root)
        err = _fr_existence_gate_error(
            self._iterate_event(affected_frs=["FR-99.99"]), known, specs_found=found)
        assert err is not None and err["error"] == "fr_gate_unknown_fr"

    def test_end_to_end_known_fr_passes_against_a_real_spec(self, tmp_path):
        root = _make_project(tmp_path)
        known, found = collect_known_fr_ids(root)
        assert _fr_existence_gate_error(
            self._iterate_event(affected_frs=["FR-01.02"]), known, specs_found=found) is None

    def test_a_folded_quality_requirement_row_passes_the_existence_gate(self, tmp_path):
        """trg-8db840a6: before the fold, a quality requirement rendered as a
        prose `QR-02` bullet naming nothing this collector could ever find, so
        `--affected-frs QR-02` was rejected by this exact gate on every
        iterate that implemented one. Folded into an ordinary FR row
        (`spec_document.fold_features`), its id is a real requirement id."""
        root = _make_project(tmp_path, spec=_QR_FOLDED_SPEC)
        known, found = collect_known_fr_ids(root)
        assert found is True
        assert "FR-01.03" in known
        assert _fr_existence_gate_error(
            self._iterate_event(affected_frs=["FR-01.03"]), known, specs_found=found) is None

    def test_finalize_path_runs_both_gates(self):
        # AC4: the finalize write path must actually invoke the gates, or it
        # silently keeps the old (unverified) behaviour.
        src = (_ROOT / "scripts" / "tools" / "finalize_iterate.py").read_text(encoding="utf-8")
        assert "run_fr_gates(event, project_root" in src

    def test_cli_path_runs_the_existence_gate(self):
        # main() no longer calls check_fr_existence directly — it calls the
        # combined run_fr_gates() wrapper, which includes it (see
        # test_combined_entry_point_applies_both_gates for that guarantee).
        src = (_ROOT / "scripts" / "tools" / "record_event.py").read_text(encoding="utf-8")
        assert "run_fr_gates(event, project_root" in src

    def test_combined_entry_point_applies_both_gates(self):
        # run_fr_gates exists precisely so a write path cannot wire one gate and
        # forget the other. Unclassified must fail even when ids would be fine.
        from lib.fr_gates import run_fr_gates
        unclassified = {"type": "work_completed", "source": "iterate", "intent": "change"}
        err = run_fr_gates(unclassified, "/nonexistent", "test")
        assert err is not None and err["error"] == "fr_gate_unclassified"

    def test_run_fr_gates_reaches_the_existence_arm(self, tmp_path):
        # A classified (spec_impact=none, has_frs) event needs no test evidence
        # (AC-3), so it must fall through the classification gate and reach
        # check_fr_existence — pinning that the second arm of run_fr_gates is
        # actually wired, not just present in the `or` chain unreachably.
        from lib.fr_gates import run_fr_gates
        root = _make_project(tmp_path)
        event = self._iterate_event(spec_impact="none", affected_frs=["FR-99.99"])
        err = run_fr_gates(event, root, "test")
        assert err is not None and err["error"] == "fr_gate_unknown_fr"

    def test_run_fr_gates_reports_unknown_fr_before_missing_test_evidence(self, tmp_path):
        # Doubt-review (iterate-2026-08-16-fr-gate-test-evidence): a classified,
        # behaviour-affecting, UNEVIDENCED event naming an FR id that exists in
        # no spec must be told about the typo first — "prove you tested
        # FR-99.99" would be nonsensical, since FR-99.99 denotes nothing.
        from lib.fr_gates import run_fr_gates
        root = _make_project(tmp_path)
        event = self._iterate_event(spec_impact="modify", affected_frs=["FR-99.99"])
        err = run_fr_gates(event, root, "test")
        assert err is not None and err["error"] == "fr_gate_unknown_fr"
