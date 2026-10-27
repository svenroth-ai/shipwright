"""``find_sibling_plugin`` resolves in the repo layout AND in the plugin cache.

GitHub issue #932: ``finalize_security_compliance.py`` looked for the compliance
plugin at ``<security plugin>.parent / "shipwright-compliance"``, which is only
right in the repo; in the cache the parent of a plugin root is the plugin's
own name directory, so the lookup landed in the wrong place.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "sibling_plugin.py"
_spec = importlib.util.spec_from_file_location("_sibling_plugin_under_test", _MODULE)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)


def _plugin(root: Path) -> Path:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": root.name}))
    (root / "scripts" / "tools").mkdir(parents=True)
    anchor = root / "scripts" / "tools" / "tool.py"
    anchor.write_text("")
    return anchor


@pytest.mark.covers("FR-01.07")
def test_repo_layout_finds_the_sibling(tmp_path: Path):
    anchor = _plugin(tmp_path / "plugins" / "shipwright-security")
    _plugin(tmp_path / "plugins" / "shipwright-compliance")
    assert sp.find_sibling_plugin(anchor, "shipwright-compliance") == (
        tmp_path / "plugins" / "shipwright-compliance"
    )


@pytest.mark.covers("FR-01.07")
def test_cache_layout_finds_the_sibling(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    _plugin(cache / "shipwright-compliance" / "0.2.2")
    assert sp.find_sibling_plugin(anchor, "shipwright-compliance") == (
        cache / "shipwright-compliance" / "0.2.2"
    )


@pytest.mark.covers("FR-01.07")
def test_cache_layout_picks_the_newest_installed_version(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    for version in ("0.2.2", "0.10.0", "0.9.5"):
        _plugin(cache / "shipwright-compliance" / version)
    found = sp.find_sibling_plugin(anchor, "shipwright-compliance")
    assert found == cache / "shipwright-compliance" / "0.10.0"


@pytest.mark.covers("FR-01.07")
def test_cache_layout_ignores_directories_that_are_not_plugins(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    _plugin(cache / "shipwright-compliance" / "0.2.2")
    (cache / "shipwright-compliance" / "9.9.9").mkdir()  # half-removed install
    found = sp.find_sibling_plugin(anchor, "shipwright-compliance")
    assert found == cache / "shipwright-compliance" / "0.2.2"


@pytest.mark.covers("FR-01.07")
def test_missing_sibling_returns_none(tmp_path: Path):
    anchor = _plugin(tmp_path / "cache" / "shipwright" / "shipwright-security" / "0.2.1")
    assert sp.find_sibling_plugin(anchor, "shipwright-compliance") is None


@pytest.mark.covers("FR-01.07")
def test_anchor_outside_any_plugin_returns_none(tmp_path: Path):
    stray = tmp_path / "x" / "y.py"
    stray.parent.mkdir()
    stray.write_text("")
    assert sp.find_sibling_plugin(stray, "shipwright-compliance") is None


@pytest.mark.covers("FR-01.07")
def test_a_release_outranks_its_prerelease_and_non_semver_names_rank_last(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    for version in ("1.0.0", "1.0.0-rc1", "39bce37b9a1c"):
        _plugin(cache / "shipwright-compliance" / version)
    assert sp.find_sibling_plugin(anchor, "shipwright-compliance") == (
        cache / "shipwright-compliance" / "1.0.0"
    )


@pytest.mark.covers("FR-01.07")
def test_orphaned_versions_are_skipped(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    _plugin(cache / "shipwright-compliance" / "0.2.2")
    newer = cache / "shipwright-compliance" / "0.3.0"
    _plugin(newer)
    (newer / ".orphaned_at").write_text("1")
    assert sp.find_sibling_plugin(anchor, "shipwright-compliance") == (
        cache / "shipwright-compliance" / "0.2.2"
    )


@pytest.mark.covers("FR-01.07")
def test_require_skips_a_partly_reaped_newer_version(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    anchor = _plugin(cache / "shipwright-security" / "0.2.1")
    good = cache / "shipwright-compliance" / "0.2.2"
    _plugin(good)
    (good / "scripts" / "tools" / "update_compliance.py").write_text("")
    _plugin(cache / "shipwright-compliance" / "0.3.0")  # plugin.json only, scripts/ reaped
    found = sp.find_sibling_plugin(
        anchor, "shipwright-compliance", require="scripts/tools/update_compliance.py",
    )
    assert found == good
