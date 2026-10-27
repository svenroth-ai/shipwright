"""The compliance plugin must be found in the installed plugin cache too.

GitHub issue #932: the cache lays plugins out as
``<cache>/shipwright/<plugin>/<version>/``, so ``this_plugin.parent`` is the
plugin's own name directory, not a directory of siblings, and
``update_compliance.py`` was reported ``missing`` — silently skipping the
compliance refresh after every security scan.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SHARED_LIB = PLUGIN_ROOT.parent.parent / "shared" / "scripts" / "lib" / "sibling_plugin.py"
SCRIPT = PLUGIN_ROOT / "scripts" / "tools" / "finalize_security_compliance.py"


def _plugin(root: Path) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": root.name}))


def _fake_cache(tmp_path: Path, compliance_versions: tuple[str, ...]) -> Path:
    """Build ``<cache>/shipwright/…`` with a copy of the script under test."""
    cache = tmp_path / "cache" / "shipwright"
    (cache / "shared" / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(SHARED_LIB, cache / "shared" / "scripts" / "lib" / "sibling_plugin.py")
    security = cache / "shipwright-security" / "0.2.1"
    _plugin(security)
    (security / "scripts" / "tools").mkdir(parents=True)
    shutil.copy(SCRIPT, security / "scripts" / "tools" / SCRIPT.name)
    for version in compliance_versions:
        plugin = cache / "shipwright-compliance" / version
        _plugin(plugin)
        (plugin / "scripts" / "tools").mkdir(parents=True)
        (plugin / "scripts" / "tools" / "update_compliance.py").write_text("")
    return security / "scripts" / "tools" / SCRIPT.name


def _load(path: Path):
    sentinel = "_test_security_finalize_cache_layout_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(sentinel, None)
    return mod


@pytest.mark.covers("FR-01.07")
def test_finds_the_newest_compliance_plugin_in_the_plugin_cache(tmp_path: Path):
    script = _fake_cache(tmp_path, ("0.2.2", "0.3.0"))
    mod = _load(script)
    found = mod._find_compliance_plugin(script)
    assert found == script.parents[4] / "shipwright-compliance" / "0.3.0"
    assert (found / "scripts" / "tools" / "update_compliance.py").is_file()


@pytest.mark.covers("FR-01.07")
def test_run_update_compliance_launches_the_cached_compliance_plugin(
    tmp_path: Path, monkeypatch,
):
    script = _fake_cache(tmp_path, ("0.2.2",))
    mod = _load(script)
    seen: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = '{"updated_reports": []}'
        stderr = ""

    def _fake_run(argv, **_kwargs):
        seen.append(list(argv))
        return _Done()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    result = mod._run_update_compliance(tmp_path)
    assert "error" not in result, result
    compliance = script.parents[4] / "shipwright-compliance" / "0.2.2"
    assert str(compliance) in seen[0]
    assert str(compliance / "scripts" / "tools" / "update_compliance.py") in seen[0]


@pytest.mark.covers("FR-01.07")
def test_falls_back_to_the_repo_guess_when_the_shared_resolver_is_absent(tmp_path: Path):
    script = _fake_cache(tmp_path, ("0.2.2",))
    (script.parents[4] / "shared" / "scripts" / "lib" / "sibling_plugin.py").unlink()
    mod = _load(script)
    found = mod._find_compliance_plugin(script)  # must not raise
    assert found == script.parents[3] / "shipwright-compliance"
    result = mod._run_update_compliance(tmp_path)
    assert result["error"].startswith("missing:")


@pytest.mark.covers("FR-01.07")
def test_repo_layout_still_resolves_the_sibling_plugin():
    mod = _load(SCRIPT)
    found = mod._find_compliance_plugin(SCRIPT)
    assert found == PLUGIN_ROOT.parent / "shipwright-compliance"
