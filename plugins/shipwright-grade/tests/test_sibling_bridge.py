"""sibling_bridge finds the compliance and adopt plugins in the repo AND the plugin cache."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BRIDGE = PLUGIN_ROOT / "scripts" / "lib" / "sibling_bridge.py"
SHARED_LIB = PLUGIN_ROOT.parent.parent / "shared" / "scripts" / "lib" / "sibling_plugin.py"


def _plugin(root: Path) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": root.name}))


def _load(path: Path):
    sentinel = "_test_sibling_bridge_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(sentinel, None)
    return mod


@pytest.mark.covers("FR-01.18")
def test_find_plugin_resolves_the_compliance_plugin_in_the_plugin_cache(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    (cache / "shared" / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(SHARED_LIB, cache / "shared" / "scripts" / "lib" / "sibling_plugin.py")
    grade = cache / "shipwright-grade" / "0.1.0"
    _plugin(grade)
    (grade / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(BRIDGE, grade / "scripts" / "lib" / "sibling_bridge.py")
    _plugin(cache / "shipwright-compliance" / "0.2.2")
    _plugin(cache / "shipwright-adopt" / "0.2.1")

    bridge = _load(grade / "scripts" / "lib" / "sibling_bridge.py")
    assert bridge.find_plugin("shipwright-compliance") == cache / "shipwright-compliance" / "0.2.2"
    assert bridge.find_plugin("shipwright-adopt") == cache / "shipwright-adopt" / "0.2.1"
    assert bridge.find_plugin("shipwright-missing") is None


@pytest.mark.covers("FR-01.18")
def test_find_plugin_resolves_the_compliance_plugin_in_the_repo():
    bridge = _load(BRIDGE)
    assert bridge.find_plugin("shipwright-compliance") == PLUGIN_ROOT.parent / "shipwright-compliance"


@pytest.mark.covers("FR-01.18")
def test_find_plugin_degrades_without_the_shared_resolver(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"  # no shared/ in this cache
    grade = cache / "shipwright-grade" / "0.1.0"
    _plugin(grade)
    (grade / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(BRIDGE, grade / "scripts" / "lib" / "sibling_bridge.py")
    _plugin(cache / "shipwright-compliance" / "0.2.2")
    bridge = _load(grade / "scripts" / "lib" / "sibling_bridge.py")
    assert bridge.find_plugin("shipwright-compliance") is None  # no raise
