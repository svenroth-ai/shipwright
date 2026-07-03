"""Tests for the coverage heuristic — route-specific, no over-counting."""

from __future__ import annotations

from grade_inputs_projector import _feature_covered


def _feat(route: str, source: str = "app/api.py") -> dict:
    return {"route": route, "source_file": source}


class TestFeatureCovered:
    def test_route_referenced_is_covered(self):
        assert _feature_covered(_feat("/users"), ['assert "/users" in routes']) is True

    def test_module_import_alone_does_not_cover(self):
        # The over-counting failure mode: a bare module import must NOT mark a
        # route covered (many routes share one source file).
        assert _feature_covered(_feat("/users"), ["from app.api import app"]) is False

    def test_only_the_referenced_route_of_a_shared_file_is_covered(self):
        tests = ['def test_orders(): assert "/orders"']
        assert _feature_covered(_feat("/orders"), tests) is True
        assert _feature_covered(_feat("/users"), tests) is False

    def test_param_only_route_is_not_covered(self):
        assert _feature_covered(_feat("/{id}"), ["anything"]) is False

    def test_no_tests_no_coverage(self):
        assert _feature_covered(_feat("/users"), []) is False
