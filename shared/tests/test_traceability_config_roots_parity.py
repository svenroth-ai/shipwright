"""FR-01.11 t1 follow-up (external code review, glm, medium): the AC-coverage
manifest regenerator (``test_links`` collector) only walks the directories
named in ``shipwright_compliance_config.json``'s ``traceability.test_roots``
— NOT a live scan of every ADR-044 pytest root. t1 found this the hard way:
tags in ``shared/scripts/tools/tests`` were invisible to
``check_ac_coverage_ratchet.py`` until that config was widened to match.

This pins the parity so a future config edit that drops a root cannot
silently reopen the same gap: every REAL, discovered ADR-044 pytest root
under ``shared/`` must resolve inside the configured
``traceability.test_roots`` globs (``plugins/*/tests`` is asserted
separately, by pattern, since ``discover_test_roots`` also returns
per-plugin roots that already match that one glob).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "conftest.py"


def _load_root_conftest():
    """Path-load the repo-root ``conftest.py`` under a sentinel name.

    Same loader idiom as ``test_pytest_root_discovery.py`` — path-loaded,
    not imported, so this module adds no top-level-name ambiguity of its
    own to the exact thing it is testing.
    """
    spec = importlib.util.spec_from_file_location(
        "_sw_root_conftest_for_traceability_parity", ROOT_CONFTEST
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_sw_root_conftest_for_traceability_parity"] = module
    spec.loader.exec_module(module)
    return module


def _configured_test_root_dirs() -> set[Path]:
    """Mirror ``configured_test_roots``'s (``_test_links_io.py``) entry-skip rules —
    a ``**`` entry or a non-string/empty entry is skipped there too — so this parity
    guard can't pass by being more permissive than the collector it is pinning."""
    config = json.loads(
        (REPO_ROOT / "shipwright_compliance_config.json").read_text(encoding="utf-8")
    )
    entries = config["traceability"]["test_roots"]
    resolved: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry or "**" in entry:
            continue
        resolved.update(p.resolve() for p in REPO_ROOT.glob(entry) if p.is_dir())
    return resolved


def test_every_discovered_shared_root_is_in_the_traceability_scan():
    conftest = _load_root_conftest()
    discovered = conftest.discover_test_roots(REPO_ROOT)
    configured = _configured_test_root_dirs()

    shared_roots = {r for r in discovered if r.is_relative_to(REPO_ROOT / "shared")}
    assert shared_roots, (
        "expected at least one ADR-044 pytest root under shared/ — if "
        "discover_test_roots regressed to finding none, this guard must fail "
        "loudly instead of vacuously passing"
    )
    missing = sorted(
        r.relative_to(REPO_ROOT).as_posix()
        for r in shared_roots
        if r not in configured
    )
    assert not missing, (
        "these ADR-044 pytest roots under shared/ are invisible to the "
        "test_links coverage collector (shipwright_compliance_config.json's "
        "traceability.test_roots does not resolve to them): "
        f"{missing} — a @pytest.mark.covers tag there will never clear the "
        "ac_coverage_ratchet baseline (t1's original gap)."
    )


def test_every_discovered_plugin_root_is_covered_by_the_glob():
    conftest = _load_root_conftest()
    discovered = conftest.discover_test_roots(REPO_ROOT)
    plugin_roots = {
        r for r in discovered if r.is_relative_to(REPO_ROOT / "plugins")
    }
    assert plugin_roots, "expected at least one plugins/*/tests root to exist"

    config = json.loads(
        (REPO_ROOT / "shipwright_compliance_config.json").read_text(encoding="utf-8")
    )
    assert "plugins/*/tests" in config["traceability"]["test_roots"], (
        "the plugins/*/tests glob entry was removed from "
        "traceability.test_roots — every plugin's tests would silently drop "
        "out of the AC-coverage scan"
    )
