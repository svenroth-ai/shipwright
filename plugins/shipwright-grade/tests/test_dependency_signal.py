"""Tests for dependency_signal — inspectable-only license hygiene (dim 7).

Injects the collector (so no installed venv is needed) but uses the REAL
compliance license classifier, so the NOT_INSTALLED-exclusion + copyleft
detection are integration-tested against the shipped SBOM logic.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dependency_signal import compute_dependency_signal


def _dep(license_: str, dep_type: str = "runtime"):
    return SimpleNamespace(name="pkg", version="1.0", dep_type=dep_type, license=license_)


def _sig(deps):
    return compute_dependency_signal(Path("."), collect=lambda _root: deps)


def test_no_manifest_is_na():
    sig = _sig([])
    assert sig.measurable is False
    assert sig.detail == "no dependency manifest"


def test_all_not_installed_is_na_and_honest():
    sig = _sig([_dep("not-installed"), _dep("not-installed")])
    assert sig.measurable is False
    assert sig.excluded_not_installed == 2
    assert "not resolved without install" in sig.detail


def test_resolved_licenses_are_graded():
    sig = _sig([_dep("MIT"), _dep("Apache-2.0"), _dep("BSD-3-Clause")])
    assert sig.measurable is True
    assert sig.deps_total == 3
    assert sig.deps_unknown_license == 0
    assert sig.deps_copyleft == 0


def test_undeclared_license_counts_as_unknown_but_inspectable():
    sig = _sig([_dep("MIT"), _dep("unknown")])
    assert sig.measurable is True
    assert sig.deps_total == 2          # both inspectable (installed)
    assert sig.deps_unknown_license == 1


def test_copyleft_detected():
    sig = _sig([_dep("MIT"), _dep("GPL-3.0"), _dep("LGPL-2.1")])
    assert sig.deps_copyleft == 2
    assert sig.deps_total == 3


def test_not_installed_excluded_from_graded_set():
    # 2 inspectable (MIT + unknown) + 3 not-installed → graded over 2, not 5.
    sig = _sig([_dep("MIT"), _dep("unknown"),
                _dep("not-installed"), _dep("not-installed"), _dep("not-installed")])
    assert sig.deps_total == 2
    assert sig.deps_unknown_license == 1
    assert sig.excluded_not_installed == 3
    assert "3 not resolved without install" in sig.detail


def test_collector_error_is_graceful_na():
    def _boom(_root):
        raise RuntimeError("hostile manifest")
    sig = compute_dependency_signal(Path("."), collect=_boom)
    assert sig.measurable is False
    assert "could not be parsed" in sig.detail
