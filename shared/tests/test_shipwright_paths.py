"""The path resolver (campaign root-files-into-config, R0b): zero behaviour change.

Every value below is the literal the repo used before the resolver existed. R0b may centralise
these names; it may not change a single one - that is R3's flip, behind its own gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import shipwright_paths as sp  # noqa: E402
from lib.config import CONFIG_FILES  # noqa: E402
from lib.derived_snapshots import DERIVED_SNAPSHOTS, RESTORABLE_SNAPSHOTS  # noqa: E402
from lib.project_root import CONFIG_MARKERS  # noqa: E402

#: key -> the root name it had before R0b (frozen: a drift here is a behaviour change).
FROZEN = {
    "run_config": "shipwright_run_config.json", "project_config": "shipwright_project_config.json",
    "plan_config": "shipwright_plan_config.json", "build_config": "shipwright_build_config.json",
    "events": "shipwright_events.jsonl", "sync_config": "shipwright_sync_config.json",
    "test_config": "shipwright_test_config.json", "iterate_config": "shipwright_iterate_config.json",
    "changelog_config": "shipwright_changelog_config.json",
    "compliance_config": "shipwright_compliance_config.json",
    "security_config": "shipwright_security_config.json", "model_config": "shipwright_model_config.json",
    "design_config": "shipwright_design_config.json", "deploy_config": "shipwright_deploy_config.json",
    "audit_config": "audit_config.json", "bloat_baseline": "shipwright_bloat_baseline.json",
    "ac_coverage_baseline": "shipwright_ac_coverage_baseline.json",
    "adr_collision_baseline": "shipwright_adr_collision_baseline.json",
    "inline_suppressions": "shipwright_inline_suppressions.json",
    "known_failures": "shipwright_known_failures.json", "ac_registry": "shipwright_ac_registry.json",
    "accepted_risks": "shipwright_accepted_risks.yaml", "test_results": "shipwright_test_results.json",
    "audit_report": "shipwright_audit_report.json", "plan_snapshot": "shipwright_plan_snapshot.json",
    "dev_server": "shipwright_dev_server.json",
}


def test_every_name_is_the_pre_resolver_root_name():
    assert {k: sp.rel(k) for k in sp.SPECS} == FROZEN
    assert sp.name("run_config") == sp.legacy_rel("run_config") == sp.rel_at("run_config", "deadbeef")


def test_kinds_are_the_documented_set_and_every_file_has_one():
    assert set(sp.KINDS) == {"config", "baseline", "register", "derived", "marker", "state", "pointer"}
    assert all(s.kind in sp.KINDS for s in sp.SPECS.values())
    # the pointer kind is reserved: R3 decides its format, nothing carries it yet
    assert sp.names_of([sp.POINTER]) == ()
    assert sp.names_of([sp.BASELINE]) == tuple(FROZEN[k] for k in (
        "bloat_baseline", "ac_coverage_baseline", "adr_collision_baseline", "inline_suppressions", "known_failures"))


def test_path_main_path_and_unknown_keys(tmp_path):
    assert sp.path("run_config", tmp_path) == tmp_path / "shipwright_run_config.json"
    main = tmp_path / "main"
    assert sp.main_path("model_config", tmp_path, main) == main / "shipwright_model_config.json"
    assert sp.main_path("model_config", tmp_path, None) == tmp_path / "shipwright_model_config.json"
    with pytest.raises(KeyError, match="unknown Shipwright file key"):
        sp.rel("nope")
    assert sp.key_for_basename("shipwright_run_config.json") == "run_config"
    assert sp.key_for_basename("README.md") is None


def test_json_path_or_none_only_accepts_exact_shipwright_json_names(tmp_path):
    assert sp.json_path_or_none("run_config", tmp_path) == tmp_path / "shipwright_run_config.json"
    assert sp.json_path_or_none("events", tmp_path) is None        # .jsonl, not shipwright_events.json
    assert sp.json_path_or_none("zzz", tmp_path) == tmp_path / "shipwright_zzz.json"  # unknown: old construction
    assert sp.json_path_or_none("accepted_risks", tmp_path) is None  # .yaml


def test_locks_only_where_a_data_file_lock_exists(tmp_path):
    assert sp.lock_for("run_config", tmp_path) == tmp_path / "shipwright_run_config.json.lock"
    assert sp.lock_for("ac_registry", tmp_path) == tmp_path / "shipwright_ac_registry.json.lock"
    # sync_config is serialised by the EVENTS lock (BRIEF 11.9 item 4)
    assert sp.lock_for("sync_config", tmp_path) == tmp_path / "shipwright_events.jsonl.lock"
    with_lock = {k for k, s in sp.SPECS.items() if s.lock}
    assert with_lock == {"run_config", "ac_registry", "sync_config"}
    assert sp.lock_for("bloat_baseline", tmp_path) is None
    assert sp.lock_beside(tmp_path / "x.json") == tmp_path / "x.json.lock"
    from lib.events_layout import events_lock_path
    assert sp.lock_for("sync_config", tmp_path) == events_lock_path(tmp_path)  # one events lock, two routes


def test_generated_lists_equal_the_hand_written_lists_they_replaced():
    assert CONFIG_MARKERS == (
        "shipwright_run_config.json", "shipwright_project_config.json", "shipwright_plan_config.json",
        "shipwright_build_config.json", "shipwright_events.jsonl", ".shipwright/events/drops",
        ".shipwright/events/archive", ".shipwright/events/quarantine")
    assert CONFIG_FILES["run"] == "shipwright_run_config.json" and CONFIG_FILES["compliance"].endswith("compliance_config.json")
    assert sp.family_globs() == ("shipwright_*.json", "shipwright_*.yaml")


def test_derived_and_restorable_snapshots_come_from_the_kind_list():
    assert sp.snapshot_paths() == frozenset({"shipwright_test_results.json"})   # retired names are not snapshots
    assert sp.run_written_paths() == sp.snapshot_paths()   # restore exclusion comes from the run_written flag
    assert "shipwright_test_results.json" in DERIVED_SNAPSHOTS and len(DERIVED_SNAPSHOTS) == 12
    assert "shipwright_test_results.json" not in RESTORABLE_SNAPSHOTS and len(RESTORABLE_SNAPSHOTS) == 10


def test_imports_under_a_unique_top_level_name_without_the_lib_package():
    """Plugins append shared/scripts/lib to sys.path and ``import shipwright_paths`` (ADR-045: their
    own ``lib`` package must not be shadowed). The module must load with no intra-package import."""
    spec = importlib.util.spec_from_file_location("shipwright_paths_probe", Path(sp.__file__))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert mod.rel("test_results") == sp.rel("test_results")
