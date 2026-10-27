"""The orchestrator must locate ``update_compliance.py`` in the plugin cache too.

Same class as GitHub issue #932: ``_THIS_PLUGIN.parent / "shipwright-compliance"``
is only a sibling in the repo layout.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONSTANTS = PLUGIN_ROOT / "scripts" / "lib" / "orchestrator_pkg" / "constants.py"
SHARED_LIB = PLUGIN_ROOT.parent.parent / "shared" / "scripts" / "lib" / "sibling_plugin.py"


def _plugin(root: Path) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": root.name}))


@pytest.mark.covers("FR-01.01")
def test_compliance_script_is_found_in_the_plugin_cache(tmp_path: Path):
    mod, compliance = _cache_constants(tmp_path, with_resolver=True)
    assert mod._COMPLIANCE_SCRIPT == compliance / "scripts" / "tools" / "update_compliance.py"
    assert mod._COMPLIANCE_SCRIPT.is_file()


@pytest.mark.covers("FR-01.01")
def test_import_survives_an_absent_shared_resolver(tmp_path: Path):
    mod, compliance = _cache_constants(tmp_path, with_resolver=False)  # must not raise
    # Degrades to the old repo-layout guess, which names a concrete path.
    assert mod._COMPLIANCE_SCRIPT.name == "update_compliance.py"
    assert mod._COMPLIANCE_SCRIPT.parent.parent.parent != compliance


def _cache_constants(tmp_path: Path, *, with_resolver: bool):
    cache = tmp_path / "cache" / "shipwright"
    if with_resolver:
        (cache / "shared" / "scripts" / "lib").mkdir(parents=True)
        shutil.copy(SHARED_LIB, cache / "shared" / "scripts" / "lib" / "sibling_plugin.py")
    run = cache / "shipwright-run" / "0.2.1"
    _plugin(run)
    target_dir = run / "scripts" / "lib" / "orchestrator_pkg"
    target_dir.mkdir(parents=True)
    shutil.copy(CONSTANTS, target_dir / "constants.py")
    compliance = cache / "shipwright-compliance" / "0.2.2"
    _plugin(compliance)
    (compliance / "scripts" / "tools").mkdir(parents=True)
    (compliance / "scripts" / "tools" / "update_compliance.py").write_text("")
    return _load_constants(target_dir / "constants.py"), compliance


def _load_constants(path: Path):
    sentinel = "_test_run_constants_cache_layout_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(sentinel, None)
    return mod
