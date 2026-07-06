"""Layer-A fixtures — the projector grades synthetic repos correctly & stably.

well-run (CI + tests + linked commits) > no-tests (linked, but 0 coverage) >
messy (unlinked, plain commits). Asserts the projected GradeInputs, the grade
letter per fixture, the relative ordering, and determinism.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from engine_bridge import load_engine
from grade_inputs_projector import (
    _is_self_referential,
    grade_context,
    project_inputs,
)
from network_policy import NetworkPolicy
from provenance_signal import ProvenanceSignal
from repo_context import RepoContext
from resolve_target import resolve_target
from signal_bundle import compute_signals


def _context(repo: Path) -> RepoContext:
    return RepoContext(resolve_target(str(repo)))


def _local_only() -> NetworkPolicy:
    return NetworkPolicy(enabled=False, requested=False, owner=None, repo=None,
                         visibility="local-only", note="local-only")


def _inputs(repo: Path):
    ctx = _context(repo)
    # Local-only policy → compute_signals never touches the network (gh unused).
    bundle = compute_signals(ctx, _local_only(), lambda *a, **k: None)
    inputs, extras = project_inputs(ctx, load_engine(), bundle, network_enabled=False)
    return inputs, extras, ctx


class TestWellRun:
    def test_projects_full_traceability(self, well_run_repo: Path):
        inputs, extras, ctx = _inputs(well_run_repo)
        assert inputs.frs_total == 2
        assert inputs.frs_covered == 2
        assert inputs.events_total == 4
        assert inputs.events_fr_tagged == 4
        assert inputs.events_with_provenance == 4
        assert ctx.has_ci is True
        assert extras.static_test_inventory  # surfaced

    def test_heuristic_grade_caps_at_b_not_a(self, well_run_repo: Path):
        # A cold (heuristic) grade can never read A: change-reconciliation is a
        # load-bearing control a cold repo can't demonstrate, so the honesty gate
        # caps the headline at B ("full control" would be a lie). A is
        # authoritative-only. The raw weighted average is still A-level (every
        # measurable dim ~1.0) — only the headline letter is gated honestly.
        model = grade_context(_context(well_run_repo))
        assert model.grade == "B"
        assert model.score == 89.0  # NON_A_CEILING — top of B
        assert model.mode == "heuristic"
        assert "reconciliation" in model.verdict.lower()  # factual cap reason

    def test_cold_projection_declares_reconciliation_expected(self, well_run_repo: Path):
        # The cap mechanism: the COLD projection marks change-reconciliation as the
        # one expected-but-dark control, so the honesty gate (unchanged) caps at B.
        # Heuristic-only — the authoritative path builds its own GradeInputs (guarded
        # by test_authoritative.py::test_authoritative_grade_never_runs_the_projection).
        inputs, _extras, _ctx = _inputs(well_run_repo)
        assert inputs.expected_dimensions == ("change_reconciliation",)

    def test_test_health_is_na_but_inventory_surfaced(self, well_run_repo: Path):
        model = grade_context(_context(well_run_repo))
        th = [d for d in model.dimensions if d.key == "test_health"][0]
        assert th.status == "n/a"          # not fabricated from static presence
        assert "present, not executed" in th.detail
        assert "Test health" in model.controls_shipwright_would_light


class TestSelfReferentialFeatures:
    def test_framework_own_source_is_self_referential(self):
        # flask's real false-positive shape: a route in the flask package's OWN source.
        assert _is_self_referential(
            {"route": "/", "framework": "flask", "source_file": "src/flask/ctx.py"})
        assert _is_self_referential(
            {"route": "/stream", "framework": "flask",
             "source_file": "src/flask/helpers.py"})

    def test_application_route_is_genuine(self):
        # An app that USES fastapi keeps routes in its own module → not self-referential.
        assert not _is_self_referential(
            {"route": "/users", "framework": "fastapi", "source_file": "app/api.py"})
        # A backslash path (Windows) is normalized before segment matching.
        assert not _is_self_referential(
            {"route": "/x", "framework": "flask", "source_file": "app\\views.py"})

    def test_no_framework_is_not_self_referential(self):
        assert not _is_self_referential({"route": "/x", "source_file": "a/b.py"})

    def test_mislabelled_framework_still_suppressed_by_path_package(self):
        # flask's @app.get(...) shortcut is matched by the FastAPI regex → the
        # detector labels a route in flask's OWN src/flask/app.py as "fastapi".
        # The path-package check must still suppress it (root cause 4 stays closed).
        assert _is_self_referential(
            {"route": "/", "framework": "fastapi", "source_file": "src/flask/app.py"})
        # ...but a genuine fastapi app under app/ is still genuine.
        assert not _is_self_referential(
            {"route": "/", "framework": "fastapi", "source_file": "app/main.py"})

    def test_well_run_app_requirement_surface_survives_filter(self, well_run_repo: Path):
        # The synthetic app's routes live in app/api.py (framework=fastapi), so the
        # self-referential filter must NOT suppress them — req stays measurable.
        inputs, _extras, _ctx = _inputs(well_run_repo)
        assert inputs.frs_total == 2
        assert inputs.frs_covered == 2


class TestNetworkProvenanceOverride:
    def test_pr_association_ratio_overrides_git_log_count(self, well_run_repo: Path):
        # well_run_repo has 4 events, all git-log-provenanced (count 4). A network
        # PR-association ratio of 0.5 must scale onto the count → round(0.5*4)=2,
        # so the faithful network signal wins over the git-log fallback.
        ctx = _context(well_run_repo)
        bundle = compute_signals(ctx, _local_only(), lambda *a, **k: None)
        networked = dataclasses.replace(
            bundle, change_provenance=ProvenanceSignal(
                True, 0.5, "pr-association", "50% of recent commits reviewed"))
        inputs, _extras = project_inputs(
            ctx, load_engine(), networked, network_enabled=True)
        assert inputs.events_with_provenance == 2

    def test_git_log_count_kept_when_network_absent(self, well_run_repo: Path):
        inputs, _extras, _ctx = _inputs(well_run_repo)  # local-only → git-log count
        assert inputs.events_with_provenance == 4

    def test_provenance_count_rounds_half_up_and_clamps(self):
        from provenance_signal import provenance_event_count
        # An exact-half count whose integer part is EVEN is where banker's round and
        # half-up diverge: round(2.5)=2 (0.4 -> CAPPED), half-up=3 (0.6). Odd totals
        # at 50% provenance must NOT flip C->F on the count's parity.
        assert provenance_event_count(0.5, 5) == 3      # banker's would give 2
        assert provenance_event_count(0.5, 317) == 159  # banker's would give 158
        assert provenance_event_count(0.5, 4) == 2
        assert 159 / 317 >= 0.5
        # Clamp defensively so a malformed ratio can't feed the scorer an impossible
        # count (the ratio is always [0,1] today, but this future-proofs the seam).
        assert provenance_event_count(1.5, 10) == 10
        assert provenance_event_count(-0.2, 10) == 0

    def test_projector_uses_half_up_count(self, well_run_repo: Path):
        # The projector routes the override through provenance_event_count.
        ctx = _context(well_run_repo)
        bundle = compute_signals(ctx, _local_only(), lambda *a, **k: None)
        half = dataclasses.replace(
            bundle, change_provenance=ProvenanceSignal(
                True, 0.5, "pr-association", "50% reviewed"))
        inputs, _extras = project_inputs(ctx, load_engine(), half, network_enabled=True)
        assert inputs.events_with_provenance / inputs.events_total >= 0.5


class TestNoTests:
    def test_zero_coverage_but_classified(self, no_tests_repo: Path):
        inputs, _extras, _ctx = _inputs(no_tests_repo)
        assert inputs.frs_total == 2
        assert inputs.frs_covered == 0
        assert inputs.events_fr_tagged == 2

    def test_grades_c_maintainability_lit(self, no_tests_repo: Path):
        # G2: the local oversize-file ratio now lights maintainability (small,
        # tidy files score ~1.0), lifting the no-tests repo D -> C. Test health,
        # security + deps stay n/a (local-only), so the funnel story is intact.
        model = grade_context(_context(no_tests_repo))
        assert model.grade == "C"
        maint = [d for d in model.dimensions if d.key == "maintainability"][0]
        assert maint.status == "ok"
        assert "source files over 300 LOC" in maint.detail


class TestMessy:
    def test_unlinked_plain_commits(self, messy_repo: Path):
        inputs, _extras, _ctx = _inputs(messy_repo)
        assert inputs.frs_total == 1
        assert inputs.events_total == 3
        assert inputs.events_fr_tagged == 0
        assert inputs.events_with_provenance == 0

    def test_grades_f(self, messy_repo: Path):
        model = grade_context(_context(messy_repo))
        assert model.grade == "F"


class TestOrderingAndDeterminism:
    def test_relative_ordering_is_sensible(
        self, well_run_repo: Path, no_tests_repo: Path, messy_repo: Path
    ):
        well = grade_context(_context(well_run_repo)).score
        mid = grade_context(_context(no_tests_repo)).score
        low = grade_context(_context(messy_repo)).score
        assert well > mid > low

    def test_same_repo_state_same_grade(self, well_run_repo: Path):
        first = grade_context(_context(well_run_repo))
        second = grade_context(_context(well_run_repo))
        assert first == second  # frozen dataclasses → structural equality
