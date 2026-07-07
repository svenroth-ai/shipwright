"""Integration: the vendored ensure_shared_cache bootstrap heals a real layout.

The cross-component composition proof (the ``cross_component`` risk flag's
non-dodgeable integration coverage): stand up a faithful plugin-cache +
marketplace-clone tree, run the ACTUAL bootstrap as a subprocess exactly where a
hook would (so its ``Path(__file__)`` walk resolves against the fake tree), and
assert the compose for BOTH delivery gaps:

- ``shared/``  ← mirrored from the marketplace full-clone;
- ``plugins/`` ← mirrored from the installed versioned plugin dirs (no clone),
  so cross-plugin ``../../plugins/shipwright-X`` imports resolve.

Run with ``sys.executable`` (never a probed binary) so there is no silent-skip
path to hard-fail in CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_SHARED_SENTINEL = Path("scripts") / "lib" / "project_root.py"
_PLUGINS_SENTINEL = Path("shipwright-run") / "scripts" / "lib" / "phase_task_lifecycle.py"


def _make_shared(root: Path) -> Path:
    """A minimal-but-healthy shared/ tree at ``root`` (with an ignorable junk dir)."""
    (root / _SHARED_SENTINEL).parent.mkdir(parents=True, exist_ok=True)
    (root / _SHARED_SENTINEL).write_text("# sentinel\n", encoding="utf-8")
    (root / "scripts" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "hooks" / "track_tool_calls.py").write_text("# hook\n", encoding="utf-8")
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    return root


def _cache_and_marketplace(tmp_path: Path):
    """Return (cache/shipwright root, marketplaces/shipwright/shared root)."""
    plugins = tmp_path / ".claude" / "plugins"
    cache_sw = plugins / "cache" / "shipwright"
    mp_shared = plugins / "marketplaces" / "shipwright" / "shared"
    return cache_sw, mp_shared


def _install(cache_sw: Path, name: str, version: str, files: dict[str, str]) -> Path:
    """Create an installed plugin dir cache/shipwright/<name>/<version>/ with files."""
    vdir = cache_sw / name / version
    vdir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = vdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vdir


def _install_run(cache_sw: Path) -> Path:
    """An installed shipwright-run carrying the cross-plugin (plugins/) sentinel."""
    return _install(cache_sw, "shipwright-run", "1.0.0", {
        "scripts/lib/phase_task_lifecycle.py":
            "def find_phase_task_by_session_uuid(*a):\n    return None\n",
    })


def _place_hook(cache_sw: Path) -> Path:
    """Install shipwright-build carrying the REAL vendored bootstrap; return its path."""
    vdir = _install(cache_sw, "shipwright-build", "0.2.2", {})
    script = vdir / "scripts" / "hooks" / "ensure_shared_cache.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(_CANONICAL.read_bytes())
    return script


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)], input="{}",
        capture_output=True, text=True, timeout=60,
    )


def test_heals_shared_and_plugins_on_fresh_install(tmp_path: Path):
    cache_sw, mp_shared = _cache_and_marketplace(tmp_path)
    _make_shared(mp_shared)          # marketplace clone carries shared/
    _install_run(cache_sw)           # installed run = source for the plugins/ heal
    script = _place_hook(cache_sw)
    assert not (cache_sw / "shared").exists() and not (cache_sw / "plugins").exists()

    result = _run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "shared" / _SHARED_SENTINEL).is_file(), "shared/ not healed"
    assert (cache_sw / "plugins" / _PLUGINS_SENTINEL).is_file(), "plugins/ not healed"
    assert not (cache_sw / "shared" / "__pycache__").exists(), "__pycache__ should be ignored"
    assert "shared" in result.stderr and "plugins" in result.stderr


def test_heals_plugins_without_marketplace_clone(tmp_path: Path):
    # No clone made -> shared cannot heal, but plugins/ heals from the installed dirs.
    cache_sw, _mp = _cache_and_marketplace(tmp_path)
    _install_run(cache_sw)
    script = _place_hook(cache_sw)

    result = _run(script)

    assert result.returncode == 0
    assert (cache_sw / "plugins" / _PLUGINS_SENTINEL).is_file(), "plugins/ heals without a clone"
    assert not (cache_sw / "shared").exists(), "shared/ can't heal without a clone"
    assert "update-marketplace.sh" in result.stderr, "still guides about the missing shared/"


def test_idempotent_noop_when_both_present(tmp_path: Path):
    cache_sw, mp_shared = _cache_and_marketplace(tmp_path)
    _make_shared(mp_shared)
    _make_shared(cache_sw / "shared")                       # shared already healed
    sentinel = cache_sw / "plugins" / _PLUGINS_SENTINEL     # plugins already healed
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("x\n", encoding="utf-8")
    _install_run(cache_sw)
    script = _place_hook(cache_sw)

    result = _run(script)

    assert result.returncode == 0
    assert "self-healed" not in result.stderr  # fast-path no-op


def test_fail_open_when_no_clone_and_no_run(tmp_path: Path):
    cache_sw, _mp = _cache_and_marketplace(tmp_path)  # no clone, no run installed
    script = _place_hook(cache_sw)

    result = _run(script)

    assert result.returncode == 0, "must never block a session (fail-open)"
    assert not (cache_sw / "shared").exists(), "shared/ cannot heal without a clone"
    assert "update-marketplace.sh" in result.stderr


def test_dev_plugin_dir_model_is_noop(tmp_path: Path):
    # --plugin-dir dev model: PLUGIN_ROOT = repo/plugins/<plugin>; repo/{shared,plugins}
    # are the real dirs -> both healthy -> no-op, never touches anything.
    repo = tmp_path / "repo"
    _make_shared(repo / "shared")
    sentinel = repo / "plugins" / _PLUGINS_SENTINEL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("x\n", encoding="utf-8")
    script = repo / "plugins" / "shipwright-build" / "scripts" / "hooks" / "ensure_shared_cache.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(_CANONICAL.read_bytes())

    result = _run(script)

    assert result.returncode == 0
    assert "self-healed" not in result.stderr
