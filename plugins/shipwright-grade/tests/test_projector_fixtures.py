"""Layer-A fixtures — the projector grades synthetic repos correctly & stably.

well-run (CI + tests + linked commits) > no-tests (linked, but 0 coverage) >
messy (unlinked, plain commits). Asserts the projected GradeInputs, the grade
letter per fixture, the relative ordering, and determinism.
"""

from __future__ import annotations

from pathlib import Path

from engine_bridge import load_engine
from grade_inputs_projector import grade_context, project_inputs
from network_policy import NetworkPolicy
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

    def test_grades_a(self, well_run_repo: Path):
        model = grade_context(_context(well_run_repo))
        assert model.grade == "A"
        assert model.score == 100.0
        assert model.mode == "heuristic"

    def test_test_health_is_na_but_inventory_surfaced(self, well_run_repo: Path):
        model = grade_context(_context(well_run_repo))
        th = [d for d in model.dimensions if d.key == "test_health"][0]
        assert th.status == "n/a"          # not fabricated from static presence
        assert "present, not executed" in th.detail
        assert "Test health" in model.controls_shipwright_would_light


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
