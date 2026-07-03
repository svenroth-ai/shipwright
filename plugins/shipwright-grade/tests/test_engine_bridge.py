"""Tests for engine_bridge — cross-plugin load of the shared Control Grade engine.

Also the ADR-045 coexistence proof: grade's own bare modules and the compliance
engine's ``scripts.lib.*`` modules must live in the same process without
shadowing each other.
"""

from __future__ import annotations

import sys

from engine_bridge import load_engine


class TestLoadEngine:
    def test_returns_working_compute_grade(self):
        engine = load_engine()
        inputs = engine.GradeInputs(
            frs_total=2, frs_covered=2, events_total=4,
            events_fr_tagged=4, events_with_provenance=4,
        )
        report = engine.compute_grade(inputs)
        assert report.gradeable is True
        assert report.grade in {"A", "B", "C", "D", "F"}

    def test_all_green_input_grades_a(self):
        engine = load_engine()
        inputs = engine.GradeInputs(
            frs_total=10, frs_covered=10, events_total=50,
            events_fr_tagged=50, events_with_provenance=50,
        )
        report = engine.compute_grade(inputs)
        assert report.grade == "A"

    def test_all_na_is_not_gradeable_never_f(self):
        engine = load_engine()
        report = engine.compute_grade(engine.GradeInputs())
        assert report.gradeable is False
        assert report.grade == "?"

    def test_cached_handle_is_stable(self):
        assert load_engine() is load_engine()

    def test_grade_modules_and_engine_coexist_without_collision(self):
        # grade's own modules are imported BARE; the engine binds scripts.lib.*.
        import grade_inputs_projector  # noqa: F401
        import repo_context  # noqa: F401
        load_engine()
        assert "repo_context" in sys.modules
        # The compliance engine claimed the dotted namespace, not grade's lib.
        assert "scripts.lib.control_grade" in sys.modules
        assert sys.modules["repo_context"].__file__.endswith("repo_context.py")
