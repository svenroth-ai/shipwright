"""Integration: the vendored ensure_shared_cache bootstrap heals a real layout.

This is the cross-component composition proof (the ``cross_component`` risk flag's
non-dodgeable integration coverage): it stands up a faithful plugin-cache +
marketplace-clone directory tree, runs the ACTUAL bootstrap script as a
subprocess exactly where a hook would (so its ``Path(__file__)`` walk resolves
against the fake tree), and asserts the compose:

    marketplace install (cache has the plugin but NOT shared/)  +  marketplace
    full-clone (has shared/)   ->   bootstrap   ->   cache/shipwright/shared present

Run with the interpreter itself (``sys.executable``), never a probed binary, so
there is no silent-skip path to hard-fail in CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_SENTINEL_REL = Path("scripts") / "lib" / "project_root.py"


def _make_shared(root: Path) -> Path:
    """Create a minimal-but-healthy shared/ tree at ``root`` (returns it)."""
    (root / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / _SENTINEL_REL).write_text("# sentinel\n", encoding="utf-8")
    (root / "scripts" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "hooks" / "track_tool_calls.py").write_text("# hook\n", encoding="utf-8")
    junk = root / "__pycache__"
    junk.mkdir(exist_ok=True)
    (junk / "x.pyc").write_text("junk", encoding="utf-8")
    return root


def _place_hook(plugin_root: Path) -> Path:
    """Vendor the real canonical bootstrap into ``plugin_root/scripts/hooks/``."""
    dst = plugin_root / "scripts" / "hooks" / "ensure_shared_cache.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(_CANONICAL.read_bytes())
    return dst


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)], input="{}",
        capture_output=True, text=True, timeout=60,
    )


def _marketplace_cache(tmp_path: Path):
    """Return (plugin_version_dir, cache_shared, marketplace_shared_root)."""
    plugins = tmp_path / ".claude" / "plugins"
    version_dir = plugins / "cache" / "shipwright" / "shipwright-build" / "0.2.2"
    version_dir.mkdir(parents=True)
    cache_shared = plugins / "cache" / "shipwright" / "shared"
    mp_shared = plugins / "marketplaces" / "shipwright" / "shared"
    return version_dir, cache_shared, mp_shared


def test_heals_missing_shared_from_marketplace_clone(tmp_path: Path):
    version_dir, cache_shared, mp_shared = _marketplace_cache(tmp_path)
    _make_shared(mp_shared)
    script = _place_hook(version_dir)
    assert not cache_shared.exists()  # precondition: fresh install, no shared/

    result = _run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_shared / _SENTINEL_REL).is_file(), "shared/ was not healed"
    assert (cache_shared / "scripts" / "hooks" / "track_tool_calls.py").is_file()
    assert not (cache_shared / "__pycache__").exists(), "__pycache__ should be ignored"
    assert "self-healed" in result.stderr


def test_idempotent_noop_when_shared_already_present(tmp_path: Path):
    version_dir, cache_shared, mp_shared = _marketplace_cache(tmp_path)
    _make_shared(mp_shared)
    _make_shared(cache_shared)  # already healed
    script = _place_hook(version_dir)

    result = _run(script)

    assert result.returncode == 0
    assert "self-healed" not in result.stderr  # fast-path no-op, no copy performed


def test_fail_open_when_no_marketplace_clone(tmp_path: Path):
    version_dir, cache_shared, _mp = _marketplace_cache(tmp_path)  # no marketplace shared made
    script = _place_hook(version_dir)

    result = _run(script)

    assert result.returncode == 0, "must never block a session (fail-open)"
    assert not cache_shared.exists()  # nothing to heal from
    assert "update-marketplace.sh" in result.stderr  # actionable guidance


def test_dev_plugin_dir_model_is_noop(tmp_path: Path):
    # --plugin-dir dev model: PLUGIN_ROOT = repo/plugins/<plugin> (no version dir),
    # and repo/shared is the real dir -> healthy -> no-op, never touches anything.
    repo = tmp_path / "repo"
    plugin_root = repo / "plugins" / "shipwright-build"
    plugin_root.mkdir(parents=True)
    _make_shared(repo / "shared")
    script = _place_hook(plugin_root)

    result = _run(script)

    assert result.returncode == 0
    assert "self-healed" not in result.stderr
